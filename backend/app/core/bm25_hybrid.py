"""
bm25_hybrid.py — BM25 Keyword + Vector Hybrid Search for Schema RAG
===================================================================
Implements Priority 2 from docs/AI_ENGINEER_TALKS_IMPROVEMENTS.md
(David Karam's RAG quality engineering: "Layered every technique in RAG")

Architecture:
  Query → [is_keyword?] → YES → BM25 primary, Vector fallback
                        → NO  → Vector primary, BM25 secondary
        ↓
  Reciprocal Rank Fusion (RRF) of both result sets
        ↓
  Return ranked table list with per-signal scores

Why BM25 first:
  - David Karam (ex-Google Search): "BM25 is pretty easy. You should absolutely try it.
    Does it show up your quality quite a bit? Yes."
  - Keyword queries ("LFA1 vendor", "company code 1000") are faster and more precise
    via exact term matching than via vector cosine similarity
  - SAP table names are strong keyword signals — "LFA1" should rank vendor tables first
    even if the vector embedding of "LFA1" is not semantically close to "vendor"

Fusion:
  - Reciprocal Rank Fusion (RRF) = 1/(k+rank) — language-agnostic, parameter-free
  - Weights: BM25=0.4, Vector=0.6 (vector slightly favored for natural language)
  - k=60 in RRF formula (standard, reduces position noise)
"""

from __future__ import annotations

import logging
import re
import time
from typing import List, Dict, Any, Optional

from rank_bm25 import BM25Plus

logger = logging.getLogger(__name__)

# ── SAP Keyword Detector ────────────────────────────────────────────────────────
# Table names are strong keyword signals. Detect them to route to BM25.
# Covers all major domain tables in our schema.
_SAP_TABLE_PATTERN = re.compile(
    r"\b(LFA\d|KNA\d|BUKRS|T001|EKKO|EKPO|MARA|MARC|MARD|MBEW|MSEG|KNVL|KNA1|"
    r"LFB1|BSEG|QALS|AFKO|PRPS|ANLA|COEP|COSS|MKPF|VBAK|LIKP|VBRP|VBRK|VTTK|"
    r"TVRO|CDHDR|CDPOS|T001L|T001T|TKA01|TKA02)\b",
    re.IGNORECASE,
)

# Field-level keywords: domain-specific terms that map to exact table fields
_SAP_FIELD_KEYWORDS = re.compile(
    r"\b(vendor|customer|material|plant|company.code|storage.location|purchasing.org|"
    r"sales.org|inspection.lot|project|wbs.element|asset|vendor.record|"
    r"customer.record|bank.detail|partner.function|contact.person|address|"
    r"tax.india|gst|pan|tan)\b",
    re.IGNORECASE,
)

# SAP system/code patterns
_SAP_CODE_PATTERN = re.compile(
    r"\b(T001|LFA\d{3}|KNA\d{3}|EKKO|EKPO|MARA|MARC|MARD|MBEW|MSEG|KNVL|MKPF|"
    r"VBAK|LIKP|VBRK|VTTK|CDHDR|CDPOS|ANLA|AFKO|PRPS|COEP|COSS|TKA01|TKA02)\b",
    re.IGNORECASE,
)


def is_keyword_heavy_query(query: str) -> bool:
    """
    Detect whether a query should be routed primarily through BM25.

    True (BM25 first) when:
      - Contains ≥1 SAP table name (LFA1, EKKO, MARA, etc.)
      - Contains field/keyword pattern (vendor, customer, material + plant)
      - Is a pure code lookup (numeric ID, company code, etc.)
      - Short query (≤4 words) with a field keyword

    False (vector first) when:
      - Natural language question ("how many", "what is the", "analyze...")
      - Complex multi-sentence query
      - Paraphrased or abstract description
    """
    q = query.strip()
    table_hits = len(_SAP_TABLE_PATTERN.findall(q))
    field_hits = len(_SAP_FIELD_KEYWORDS.findall(q))
    code_hits = len(_SAP_CODE_PATTERN.findall(q))
    is_short = len(q.split()) <= 4
    is_code_lookup = bool(re.match(r"^\d{3,10}[A-Z]?$", q, re.IGNORECASE))

    keyword_dominant = (
        table_hits >= 1
        or (field_hits >= 2)
        or (field_hits >= 1 and is_code_lookup)
        or (field_hits >= 1 and is_short)
        or (code_hits >= 1)
    )

    if keyword_dominant:
        logger.debug(
            f"[BM25] keyword_heavy: table_hits={table_hits}, field_hits={field_hits}, "
            f"code_hits={code_hits}, is_short={is_short}, is_code_lookup={is_code_lookup}"
        )

    return keyword_dominant


# ── Reciprocal Rank Fusion ────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    bm25_results: List[Dict[str, Any]],
    vec_results: List[Dict[str, Any]],
    bm25_weight: float = 0.4,
    vec_weight: float = 0.6,
    k: int = 60,
) -> List[Dict[str, Any]]:
    """
    Fuse BM25 and vector search results using Reciprocal Rank Fusion.

    RRF score for a result = weight × 1/(k + rank_position)
    All results from both lists are included, with RRF determining final order.
    """
    bm25_rank = {r["table"]: rank for rank, r in enumerate(bm25_results)}
    vec_rank = {r["table"]: rank for rank, r in enumerate(vec_results)}

    all_tables: Dict[str, Dict] = {}
    for r in bm25_results:
        all_tables[r["table"]] = {
            "table": r["table"],
            "document": r["document"],
            "bm25_score": r["score"],
            "bm25_rank": bm25_rank.get(r["table"], -1),
            "vec_score": 0.0,
            "vec_rank": -1,
        }
    for r in vec_results:
        table = r["table"]
        if table in all_tables:
            all_tables[table]["vec_score"] = r["score"]
            all_tables[table]["vec_rank"] = vec_rank.get(table, -1)
        else:
            all_tables[table] = {
                "table": table,
                "document": r["document"],
                "bm25_score": 0.0,
                "bm25_rank": -1,
                "vec_score": r["score"],
                "vec_rank": vec_rank.get(table, -1),
            }

    for info in all_tables.values():
        rrf = 0.0
        if info["bm25_rank"] >= 0:
            rrf += bm25_weight * (1.0 / (k + info["bm25_rank"]))
        if info["vec_rank"] >= 0:
            rrf += vec_weight * (1.0 / (k + info["vec_rank"]))
        info["fused_score"] = round(rrf, 6)

    sorted_results = sorted(all_tables.values(), key=lambda x: -x["fused_score"])

    for rank, info in enumerate(sorted_results):
        info["final_rank"] = rank

    return list(sorted_results)


# ── Hybrid Search Class ────────────────────────────────────────────────────────

class BM25HybridSearch:
    """
    Hybrid BM25 + Vector search for the SAP Schema collection.

    Built lazily on first search. Stores BM25 index in memory.

    Architecture (mirrors David Karam's layered RAG quality engineering):
      1. Query classification: keyword-dominant vs natural-language
      2. BM25 search: fast, precise for table-name and field-keyword queries
      3. Vector search: semantic understanding for complex/nuanced queries
      4. RRF fusion: combines both rank signals into final ordering
      5. Return top-K with full scoring breakdown
    """

    def __init__(
        self,
        vector_store_manager,  # VectorStoreManager instance
        adapter,                # QdrantAdapter or ChromaDBAdapter (may be None)
        vector_encoder=None,    # Optional pre-loaded encoder
    ):
        self._vsm = vector_store_manager
        self._adapter = adapter
        self._encoder = vector_encoder

        # BM25 index — built lazily on first search
        self._bm25_index: Optional[BM25Plus] = None
        self._bm25_corpus: List[str] = []
        self._bm25_table_map: List[Dict] = []

        self._index_built = False
        self._indexed_count = 0

    # ── BM25 Index Builder ─────────────────────────────────────────────────────

    def _build_bm25_index(self) -> None:
        """Pull all schema documents from the vector store and build a BM25 index."""
        if self._index_built:
            return

        all_docs: List[str] = []
        all_meta: List[Dict] = []

        # ── Try Qdrant scroll ──
        if hasattr(self._adapter, "client"):
            try:
                offset = None
                while True:
                    records, next_offset = self._adapter.client.scroll(
                        collection_name=self._adapter.SCHEMA_COLLECTION,
                        limit=256,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                    )
                    if not records:
                        break
                    for pt in records:
                        payload = getattr(pt, "payload", {})
                        doc = payload.get("document", "")
                        if doc:
                            all_docs.append(doc)
                            all_meta.append({
                                "table": payload.get("table", ""),
                                "module": payload.get("module", ""),
                                "domain": payload.get("domain", ""),
                            })
                    offset = next_offset
                    if not offset:
                        break
            except Exception as e:
                logger.warning(f"[BM25] Qdrant scroll failed: {e} — using VSM fallback")

        # ── Try ChromaDB direct ──
        if not all_docs and hasattr(self._adapter, "schema_collection"):
            try:
                raw = self._adapter.schema_collection.get(limit=1000)
                if raw and raw.get("documents"):
                    for i, doc in enumerate(raw["documents"][0]):
                        all_docs.append(doc)
                        all_meta.append(raw.get("metadatas", [{}])[0][i] if raw.get("metadatas") else {})
            except Exception as e:
                logger.warning(f"[BM25] ChromaDB fallback failed: {e}")

        # ── VSM search fallback ──
        if not all_docs:
            try:
                vsm_results = self._vsm.search_schema(".", n_results=1000, domain=None)
                all_docs = [r["document"] for r in vsm_results]
                all_meta = [r.get("metadata", {}) for r in vsm_results]
            except Exception as e:
                logger.warning(f"[BM25] VSM fallback failed: {e}")

        if not all_docs:
            logger.warning("[BM25] No schema documents found for indexing")
            return

        tokenized_corpus = [doc.lower().split() for doc in all_docs]
        self._bm25_index = BM25Plus(tokenized_corpus)
        self._bm25_corpus = all_docs
        self._bm25_table_map = all_meta
        self._indexed_count = len(all_docs)
        self._index_built = True

        logger.info(f"[BM25] Index built: {self._indexed_count} documents")

    # ── BM25 Search ────────────────────────────────────────────────────────────

    def _bm25_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Execute BM25 search over the schema corpus."""
        if not self._index_built:
            self._build_bm25_index()

        if self._bm25_index is None:
            return []

        tokenized_query = query.lower().split()
        scores = self._bm25_index.get_scores(tokenized_query)

        scored = [(score, idx) for idx, score in enumerate(scores) if score > 0]
        scored.sort(key=lambda x: -x[0])

        results = []
        for score, idx in scored[:top_k]:
            meta = self._bm25_table_map[idx]
            results.append({
                "table": meta.get("table", f"doc_{idx}"),
                "document": self._bm25_corpus[idx],
                "score": round(score, 4),
                "metadata": meta,
            })

        logger.debug(f"[BM25] query='{query}' → {len(results)} results (top={top_k})")
        return results

    # ── Vector Search ─────────────────────────────────────────────────────────

    def _vector_search(
        self, query: str, top_k: int = 10, domain: str = None
    ) -> List[Dict[str, Any]]:
        """Execute vector similarity search via adapter or VSM fallback."""
        try:
            if self._adapter is not None:
                raw_results = self._adapter.search_schema(
                    query=query, n_results=top_k, domain=domain
                )
            elif hasattr(self._vsm, "search_schema"):
                raw_results = self._vsm.search_schema(
                    query=query, n_results=top_k, domain=domain
                )
            else:
                return []

            results = []
            for r in raw_results:
                results.append({
                    "table": r.get("metadata", {}).get("table", ""),
                    "document": r.get("document", ""),
                    "score": 1.0,
                    "metadata": r.get("metadata", {}),
                })
            return results
        except Exception as e:
            logger.warning(f"[BM25] Vector search failed: {e}")
            return []

    # ── Public API ─────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        domain: str = None,
        top_k: int = 6,
        keyword_weight: float = 0.4,
        vec_weight: float = 0.6,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search entry point.

        Args:
            query:          Natural language query
            domain:         Domain filter (or None for cross-domain)
            top_k:          Number of final results to return
            keyword_weight: RRF weight for BM25 (default 0.4)
            vec_weight:     RRF weight for vector (default 0.6)

        Returns:
            List of dicts with table, document, fused_score, bm25_score,
            vec_score, bm25_rank, vec_rank, final_rank, metadata, signals
        """
        t0 = time.time()

        keyword_heavy = is_keyword_heavy_query(query)

        bm25_results = self._bm25_search(query, top_k=top_k * 2)
        vec_results = self._vector_search(query, top_k=top_k * 2, domain=domain)

        if not bm25_results and not vec_results:
            logger.warning(f"[BM25] No results for query: {query}")
            return []

        fusion_used = True
        final_results: List[Dict[str, Any]]

        if keyword_heavy and len(bm25_results) >= 3:
            # High-precision keyword query: BM25 is authoritative
            fusion_used = False
            bm25_ranked = bm25_results[:top_k]

            for info in bm25_ranked:
                info["fused_score"] = info.get("score", 0.0)

            # Fill remaining with vec results not in BM25 top-K
            bm25_tables = {r["table"] for r in bm25_ranked}
            vec_fill = [
                r for r in vec_results if r["table"] not in bm25_tables
            ][:top_k - len(bm25_ranked)]

            for info in vec_fill:
                info["fused_score"] = info.get("score", 0.0)
                info["bm25_score"] = 0.0
                info["bm25_rank"] = -1

            final_results = bm25_ranked + vec_fill

            logger.debug(
                f"[BM25] keyword_heavy direct: {len(bm25_ranked)} BM25 + "
                f"{len(vec_fill)} vec_fill"
            )
        else:
            # Standard RRF fusion
            kw = 0.3 if not keyword_heavy else keyword_weight
            vw = 0.7 if not keyword_heavy else vec_weight
            final_results = reciprocal_rank_fusion(
                bm25_results, vec_results,
                bm25_weight=kw, vec_weight=vw, k=60
            )

        elapsed_ms = round((time.time() - t0) * 1000, 1)

        output = []
        for rank, info in enumerate(final_results[:top_k]):
            info["final_rank"] = rank
            info["signals"] = {
                "keyword_heavy": keyword_heavy,
                "fusion_used": fusion_used,
                "query_latency_ms": elapsed_ms,
            }
            output.append(info)

        logger.info(
            f"[BM25] query='{query[:40]}' kh={keyword_heavy} fu={fusion_used} "
            f"→ {len(output)} results in {elapsed_ms}ms"
        )
        return output
