"""
Semantic Answer Validation — Phase 17
=======================================
Post-execution validation that cross-checks the generated answer against
the user's original intent to catch hallucinations, wrong-table results,
or implausible data.

How it works:
  1. Embed (query + answer_summary + key_field_values) using all-MiniLM-L6-v2
  2. Retrieve top-k similar validated Q&A pairs from Qdrant "sap_answers" collection
  3. Compute semantic similarity score between current answer and validated references
  4. If score < threshold → flag answer as "unvalidated" + surface warnings

Confidence signal added to API response:
  - "semantic_score" (0.0–1.0)
  - "semantic_trust"  ("high" | "medium" | "low")
  - "validation_warnings" (list of specific concerns)
  - "reference_count" (how many similar validated answers were found)

This is NOT a re-generation step — it validates, it does not rewrite.
If validation fails the answer is flagged but still returned (no hard block).

Collection: "sap_answers" (384-dim, cosine)
  payload: {
    query: str,           # natural-language query
    answer_summary: str,  # short summary of the correct answer (e.g. "Vendor NAME1 for LIFNR V001, payment terms 30 days")
    domain: str,          # business_partner, mm, sd, etc.
    tables_used: List[str],
    row_count: int,        # expected row count
    key_fields: List[str], # which fields carry semantic intent
    intent_tags: List[str],# [vendor_search, payment_terms, company_code_1000]
    validated_by: str,     # "human_expert" | "benchmark_pass" | "ciba_approved"
    created_at: float,
    times_validated: int,
  }
"""

import logging
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SemanticValidationResult:
    score: float          # 0.0–1.0, cosine similarity to nearest validated answer
    trust: str            # "high" (≥0.80) | "medium" (≥0.60) | "low" (<0.60)
    warnings: List[str]   # specific concerns if trust != "high"
    reference_count: int  # how many validated answers were similar enough (top_k)
    validated_answer: Optional[str]  # nearest validated answer summary (for debugging)
    intent_tags_found: List[str]    # intent tags that matched in validated answers
    score_components: Dict[str, float]  # breakdown: intent_match, row_plausibility, table_match


class SemanticAnswerValidator:
    """
    Validates that the orchestrator's generated answer is semantically
    consistent with the user's intent and known-good reference answers.

    Uses Qdrant "sap_answers" collection for validated reference pairs.
    """

    COLLECTION = "sap_answers"
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    DEFAULT_TOP_K = 5
    DEFAULT_THRESHOLD = 0.65

    # Thresholds
    HIGH_TRUST = 0.80
    MEDIUM_TRUST = 0.60

    # Intent keywords that map to expected table characteristics
    INTENT_TABLE_HINTS: Dict[str, List[str]] = {
        "vendor_payment_terms": ["LFA1", "LFB1", "LFBK"],
        "vendor_master": ["LFA1", "BUT000", "ADRC"],
        "customer_credit": ["KNA1", "KNKK", "BSID"],
        "material_stock": ["MARA", "MARD", "MBEW", "MSKA"],
        "purchase_order": ["EKKO", "EKPO"],
        "sales_order": ["VBAK", "VBAP"],
        "quality_inspection": ["QALS", "QAMV", "MAPL"],
        "project_costs": ["PRPS", "COSP", "COSS"],
    }

    def __init__(self, qdrant_url: str = "http://localhost:6333"):
        self._qdrant_url = qdrant_url
        self._client = None
        self._encoder = None

    @property
    def client(self):
        if self._client is None:
            from qdrant_client import QdrantClient
            self._client = QdrantClient(url=self._qdrant_url)
        return self._client

    @property
    def encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            logger.info("[SemanticValidator] Loading embedding model %s", self.EMBEDDING_MODEL)
            self._encoder = SentenceTransformer(self.EMBEDDING_MODEL)
        return self._encoder

    def _embed(self, texts: List[str]) -> List[List[float]]:
        vecs = self.encoder.encode(texts, normalize_embeddings=True).tolist()
        return vecs

    def _detect_intent_tags(self, query: str) -> List[str]:
        """Infer intent tags from the natural language query."""
        query_lower = query.lower()
        tags = []
        for tag, keywords in self.INTENT_TABLE_HINTS.items():
            if any(kw in query_lower for kw in tag.split("_")):
                tags.append(tag)
            # Also check individual keywords
            if "vendor" in query_lower and tag.startswith("vendor"):
                tags.append(tag)
            if "payment term" in query_lower and tag == "vendor_payment_terms":
                tags.append(tag)
            if "customer" in query_lower and "credit" in query_lower and tag == "customer_credit":
                tags.append(tag)
            if "material" in query_lower and ("stock" in query_lower or "inventory" in query_lower) and tag == "material_stock":
                tags.append(tag)
            if "quality" in query_lower and "inspect" in query_lower and tag == "quality_inspection":
                tags.append(tag)
        return list(set(tags))

    def _build_answer_summary(self, query: str, data_records: List[Dict],
                               tables_used: List[str], sql: str) -> str:
        """Build a compact summary of the answer for embedding comparison."""
        if not data_records:
            return f"No data found for query: {query[:100]}"

        # Extract key values from first row (representative)
        first_row = data_records[0] if data_records else {}
        key_sample = {}
        for field in list(first_row.keys())[:5]:
            val = first_row.get(field, "")
            if val and str(val).strip():
                key_sample[field] = str(val)[:40]

        row_count = len(data_records)
        table_str = ", ".join(sorted(set(tables_used))[:5])

        # Build summary string
        summary_parts = [f"{row_count} rows from [{table_str}]"]
        for field, value in list(key_sample.items())[:4]:
            summary_parts.append(f"{field}={value}")
        return " | ".join(summary_parts)

    def _score_row_plausibility(self, data_records: List[Dict],
                                 query: str) -> float:
        """
        Check if row counts and field values are plausible for the query type.
        Returns 0.0–1.0 plausibility score.
        """
        if not data_records:
            return 0.5  # neutral — no data is a valid outcome for some queries

        query_lower = query.lower()
        row_count = len(data_records)

        # Heuristic: certain query types should have certain row counts
        plausibility_checks = []

        # 1. "show all vendors" / "vendor master" → expect multiple rows
        if any(kw in query_lower for kw in ["vendor master", "all vendor", "list vendor"]):
            plausibility_checks.append(1.0 if row_count >= 1 else 0.3)

        # 2. "specific vendor by LIFNR" → expect exactly 1 row or very few
        if "lifnr" in query_lower or ("vendor" in query_lower and len(data_records) <= 3):
            plausibility_checks.append(1.0)

        # 3. Quality inspection → should have inspection date and result
        if "quality" in query_lower and "inspect" in query_lower:
            has_result_fields = any(
                any(f in str(r.keys()) for f in ["ERSTNAME", "OBJNR", "STAT", "INSPL"])
                for r in data_records[:3]
            )
            plausibility_checks.append(1.0 if has_result_fields else 0.6)

        # 4. Material stock → should have qty or unit fields
        if "material" in query_lower and ("stock" in query_lower or "qty" in query_lower):
            has_qty_fields = any(
                any(f in str(r.keys()) for f in ["LABST", "LGORT", "MEINS", "MENGE", "STOCK"])
                for r in data_records[:3]
            )
            plausibility_checks.append(1.0 if has_qty_fields else 0.7)

        # 5. Generic check — all rows should have at least some non-null values
        non_empty_ratio = sum(
            1 for r in data_records
            if any(str(v).strip() for v in list(r.values())[:5])
        ) / max(row_count, 1)
        plausibility_checks.append(non_empty_ratio)

        if not plausibility_checks:
            return 0.75  # neutral default

        return sum(plausibility_checks) / len(plausibility_checks)

    def validate(
        self,
        query: str,
        data_records: List[Dict],
        tables_used: List[str],
        generated_sql: str,
        domain: str = "auto",
        top_k: int = DEFAULT_TOP_K,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> SemanticValidationResult:
        """
        Main entry point — validate the orchestrator's answer for semantic consistency.

        Args:
            query: Original natural-language query
            data_records: Result rows from sql_execute
            tables_used: Tables the SQL targeted
            generated_sql: The SQL that was executed
            domain: Domain hint (auto, mm, sd, bp, etc.)
            top_k: Number of validated Q&A references to retrieve
            threshold: Minimum score to be considered "validated"

        Returns:
            SemanticValidationResult with score, trust, warnings
        """
        start = time.time()
        intent_tags = self._detect_intent_tags(query)

        if domain == "auto":
            domain = "general"

        # Step 1: Build answer summary embedding
        answer_summary = self._build_answer_summary(query, data_records, tables_used, generated_sql)

        # Step 2: Retrieve similar validated answers from Qdrant
        validated_matches = self._retrieve_validated_answers(
            query=query,
            answer_summary=answer_summary,
            domain=domain,
            top_k=top_k,
        )

        # Step 3: Compute semantic similarity score
        score, nearest_ref = self._compute_similarity_score(validated_matches, answer_summary)

        # Step 4: Score components breakdown
        row_plausibility = self._score_row_plausibility(data_records, query)
        intent_match = self._compute_intent_match(intent_tags, validated_matches)
        table_match = self._compute_table_match(tables_used, validated_matches)

        score_components = {
            "semantic_similarity": round(score, 4),
            "row_plausibility": round(row_plausibility, 4),
            "intent_match": round(intent_match, 4),
            "table_match": round(table_match, 4),
        }

        # Composite score: weighted average
        composite = (
            score * 0.40 +
            row_plausibility * 0.25 +
            intent_match * 0.20 +
            table_match * 0.15
        )

        # Step 5: Determine trust level
        if composite >= self.HIGH_TRUST:
            trust = "high"
            warnings = []
        elif composite >= self.MEDIUM_TRUST:
            trust = "medium"
            warnings = self._build_warnings(score, row_plausibility, intent_match,
                                            table_match, intent_tags, validated_matches)
        else:
            trust = "low"
            warnings = self._build_warnings(score, row_plausibility, intent_match,
                                            table_match, intent_tags, validated_matches)

        intent_tags_found = []
        for match in validated_matches:
            if match.get("intent_tags"):
                intent_tags_found.extend(match["intent_tags"])
        intent_tags_found = list(set(intent_tags_found))

        exec_time_ms = (time.time() - start) * 1000
        logger.info(
            "    [Phase 17] Semantic validation: score={:.3f} trust={} refs={} time={:.0f}ms",
            composite, trust, len(validated_matches), exec_time_ms
        )
        if warnings:
            for w in warnings[:3]:
                logger.warning("    [Phase 17 WARN] %s", w)

        return SemanticValidationResult(
            score=round(composite, 4),
            trust=trust,
            warnings=warnings,
            reference_count=len(validated_matches),
            validated_answer=nearest_ref,
            intent_tags_found=intent_tags_found,
            score_components=score_components,
        )

    def _retrieve_validated_answers(
        self,
        query: str,
        answer_summary: str,
        domain: str,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k validated Q&A pairs from Qdrant."""
        # Try "sap_answers" collection first; fall back to empty list if collection doesn't exist
        try:
            # Build search text: combine query and answer summary for richer context
            search_text = f"Query: {query} | Answer: {answer_summary}"
            vector = self._embed([search_text])[0]
            results = self.client.search(
                collection_name=self.COLLECTION,
                query_vector=vector,
                limit=top_k,
            )

            matches = []
            for r in results:
                if r.score < 0.40:  # minimum relevance threshold
                    continue
                matches.append({
                    "id": r.id,
                    "score": round(r.score, 4),
                    "query": r.payload.get("query", ""),
                    "answer_summary": r.payload.get("answer_summary", ""),
                    "domain": r.payload.get("domain", ""),
                    "tables_used": r.payload.get("tables_used", []),
                    "row_count": r.payload.get("row_count", 0),
                    "intent_tags": r.payload.get("intent_tags", []),
                    "validated_by": r.payload.get("validated_by", ""),
                    "times_validated": r.payload.get("times_validated", 0),
                })
            return matches

        except Exception as exc:
            # Collection doesn't exist yet — this is normal on first run
            logger.debug("[SemanticValidator] sap_answers collection not ready: %s", exc)
            return []

    def _compute_similarity_score(
        self,
        validated_matches: List[Dict[str, Any]],
        answer_summary: str,
    ) -> tuple[float, Optional[str]]:
        """Compute cosine similarity between current answer and nearest validated reference."""
        if not validated_matches:
            # No references — use moderate score rather than zero (we haven't proven it's wrong)
            return 0.65, None

        # The top result's score is our primary signal
        top_score = validated_matches[0]["score"]
        nearest_summary = validated_matches[0].get("answer_summary", "")

        return top_score, nearest_summary

    def _compute_intent_match(
        self,
        query_intent_tags: List[str],
        validated_matches: List[Dict[str, Any]],
    ) -> float:
        """Score how well the query's intent matches the validated answers' intent tags."""
        if not query_intent_tags:
            return 0.75  # neutral if we can't detect intent

        if not validated_matches:
            return 0.60  # moderate — no references to compare

        # Check how many of our intent tags appear in validated answers
        validated_tags: set = set()
        for m in validated_matches:
            validated_tags.update(m.get("intent_tags", []))

        if not validated_tags:
            return 0.60

        overlap = set(query_intent_tags) & validated_tags
        return len(overlap) / max(len(query_intent_tags), 1)

    def _compute_table_match(
        self,
        tables_used: List[str],
        validated_matches: List[Dict[str, Any]],
    ) -> float:
        """Score how well the used tables match validated answer tables."""
        if not tables_used or not validated_matches:
            return 0.70  # moderate default

        tables_set = set(t.upper() for t in tables_used)
        validated_tables_sets = [set(t.upper() for t in m.get("tables_used", [])) for m in validated_matches]

        # Check overlap with each validated answer
        scores = []
        for vt in validated_tables_sets:
            if vt:
                overlap = len(tables_set & vt)
                union = len(tables_set | vt)
                jaccard = overlap / union if union > 0 else 0
                scores.append(jaccard)
            else:
                scores.append(0.0)

        return max(scores) if scores else 0.65

    def _build_warnings(
        self,
        semantic_sim: float,
        row_plausibility: float,
        intent_match: float,
        table_match: float,
        query_intent_tags: List[str],
        validated_matches: List[Dict[str, Any]],
    ) -> List[str]:
        """Build specific warning messages for low-scoring components."""
        warnings = []

        if semantic_sim < 0.50:
            warnings.append(
                f"Low semantic similarity ({semantic_sim:.2f}) — answer differs significantly from validated references"
            )

        if row_plausibility < 0.50:
            warnings.append(
                f"Row count or field plausibility is low ({row_plausibility:.2f}) — verify result accuracy manually"
            )

        if intent_match < 0.40 and query_intent_tags:
            warnings.append(
                f"Intent mismatch: query tags {query_intent_tags} not found in validated answers — possible wrong-domain query"
            )

        if table_match < 0.40:
            warnings.append(
                f"Table match score low ({table_match:.2f}) — SQL may be querying unexpected tables"
            )

        # If we have validated matches but they disagree on row count
        if validated_matches:
            ref_row_counts = [m.get("row_count", 0) for m in validated_matches[:3]]
            if ref_row_counts and len(data_records := []) > 0:
                # Note: data_records not available here, so we check against reference
                pass  # Would need data_records passed in — handled at call site

        return warnings[:3]  # cap at 3 warnings

    def store_validated_answer(
        self,
        query: str,
        answer_summary: str,
        domain: str,
        tables_used: List[str],
        row_count: int,
        key_fields: List[str],
        intent_tags: List[str],
        validated_by: str = "benchmark_pass",
    ) -> str:
        """
        Store a newly validated (human-confirmed or benchmark-passed) Q&A pair.
        Called by admin/benchmark tools after positive validation.

        Returns pattern_id on success.
        """
        import uuid

        payload = {
            "query": query[:500],
            "answer_summary": answer_summary[:500],
            "domain": domain or "general",
            "tables_used": tables_used,
            "row_count": row_count,
            "key_fields": key_fields,
            "intent_tags": intent_tags,
            "validated_by": validated_by,
            "created_at": time.time(),
            "times_validated": 1,
        }

        pattern_id = uuid.uuid4().hex
        try:
            vector = self._embed([f"Query: {query} | Answer: {answer_summary}"])[0]
            self.client.upsert(
                collection_name=self.COLLECTION,
                points=[{
                    "id": pattern_id,
                    "vector": vector,
                    "payload": payload,
                }]
            )
            logger.info("[SemanticValidator] Stored validated answer %s (validated_by=%s)", pattern_id, validated_by)
            return pattern_id
        except Exception as exc:
            logger.error("[SemanticValidator] Failed to store validated answer: %s", exc)
            return ""

    def get_validation_stats(self) -> Dict[str, Any]:
        """Return statistics about the validation store."""
        try:
            info = self.client.get_collection(self.COLLECTION)
            return {
                "collection": self.COLLECTION,
                "total_validated_answers": info.points_count,
                "embedding_model": self.EMBEDDING_MODEL,
            }
        except Exception as exc:
            return {"collection": self.COLLECTION, "error": str(exc)}


# ── Singleton ─────────────────────────────────────────────────────────────────

_validator: Optional[SemanticAnswerValidator] = None

def get_semantic_validator() -> SemanticAnswerValidator:
    global _validator
    if _validator is None:
        _validator = SemanticAnswerValidator()
    return _validator


# ── Convenience wrapper ──────────────────────────────────────────────────────

def validate_answer(
    query: str,
    data_records: List[Dict],
    tables_used: List[str],
    generated_sql: str,
    domain: str = "auto",
) -> SemanticValidationResult:
    """
    One-line wrapper — validates the orchestrator's answer.
    Call this in the orchestrator's STEP 8 (Synthesis) block, after getting data_records.
    """
    validator = get_semantic_validator()
    return validator.validate(
        query=query,
        data_records=data_records,
        tables_used=tables_used,
        generated_sql=generated_sql,
        domain=domain,
    )