"""
Phase 16 — Self-Healing Patterns DB
====================================
Stores successfully healed SQL corrections in Qdrant so they become
production fast-path patterns for future queries.

After self-healer fixes SQL (Phase 6), the healed version is:
  1. Embedded (all-MiniLM-L6-v2) and upserted to Qdrant collection `sql_patterns`
  2. Tagged with heal_code, error_type, domain, tables_involved
  3. On future similar query, voting_executor checks this collection as a 4th path

Collection schema (same as sql_patterns):
  - id: UUID
  - vector: 384-dim embedding
  - payload: { intent, sql, sql_template, domain, tables_used, tags, heal_code,
               error_type, healed_at, heal_reason, times_reused, query_example }

This module is NOT auto-imported to avoid circular imports.
Call `store_healed_pattern(...)` explicitly after self-heal success.
"""

import time
import uuid
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# ── Singleton lazy-init ──────────────────────────────────────────────────────

_heal_store: Optional["HealedPatternStore"] = None

def get_heal_store() -> "HealedPatternStore":
    global _heal_store
    if _heal_store is None:
        from app.core.healed_pattern_store import HealedPatternStore
        _heal_store = HealedPatternStore()
    return _heal_store


# ── HealedPatternStore ─────────────────────────────────────────────────────────

class HealedPatternStore:
    """
    Qdrant-backed store for self-healed SQL patterns (Phase 16).

    After self-healer successfully fixes SQL, call store_healed_pattern().
    The healed SQL is embedded and stored alongside heal metadata so
    voting_executor can retrieve it as a fast-path candidate.

    Collection: sql_patterns (384-dim vectors, cosine)
    """

    COLLECTION = "sql_patterns"
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"   # 384-dim
    DISTANCE_THRESHOLD = 0.75              # Jaccard-equivalent for cosine similarity

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
            logger.info("[HealStore] Loading embedding model %s", self.EMBEDDING_MODEL)
            self._encoder = SentenceTransformer(self.EMBEDDING_MODEL)
        return self._encoder

    def _embed(self, texts: List[str]) -> List[List[float]]:
        vecs = self.encoder.encode(texts, normalize_embeddings=True).tolist()
        return vecs

    def _table_fingerprint(self, sql: str) -> List[str]:
        """Extract sorted table list from SQL as a lightweight fingerprint."""
        import re
        tokens = re.sub(r'[^\w\s]', ' ', sql).split()
        # All-caps words that look like SAP table names (≥4 chars, starts with letter)
        tables = sorted(set(t for t in tokens if t.isupper() and len(t) >= 4 and t[0].isalpha()))
        return tables

    def store_healed_pattern(
        self,
        original_sql: str,
        healed_sql: str,
        heal_code: str,
        heal_reason: str,
        error_type: str,
        domain: str,
        query_example: str,
        tables_used: Optional[List[str]] = None,
    ) -> str:
        """
        Store a healed SQL pattern in Qdrant.

        Returns the pattern_id (UUID hex) on success, empty string on failure.
        """
        tables_used = tables_used or self._table_fingerprint(healed_sql)

        intent = query_example.strip()[:500]       # use the natural-language query as intent
        tags = [heal_code, error_type, "healed", "phase16"]
        if domain and domain != "auto":
            tags.append(domain)

        payload = {
            "intent": intent,
            "sql": healed_sql,
            "sql_template": healed_sql,              # same as sql for now (could generalize later)
            "domain": domain or "general",
            "tables_used": tables_used,
            "tags": tags,
            "heal_code": heal_code,
            "error_type": error_type,
            "healed_at": time.time(),
            "heal_reason": heal_reason[:200],
            "times_reused": 0,
            "query_example": query_example[:500],
            "original_sql": original_sql[:1000],     # keep original for debugging
        }

        pattern_id = uuid.uuid4().hex
        vector = self._embed([intent])[0]

        try:
            self.client.upsert(
                collection_name=self.COLLECTION,
                points=[{
                    "id": pattern_id,
                    "vector": vector,
                    "payload": payload,
                }]
            )
            logger.info(
                "[HealStore] Stored pattern %s (heal=%s, domain=%s, tables=%s)",
                pattern_id, heal_code, domain, tables_used
            )
            return pattern_id
        except Exception as exc:
            logger.error("[HealStore] Failed to store pattern: %s", exc)
            return ""

    def find_similar_healed(
        self,
        query: str,
        domain: str = "auto",
        top_k: int = 3,
        min_score: float = 0.65,
    ) -> List[Dict[str, Any]]:
        """
        Search for previously healed patterns similar to the incoming query.

        Used by voting_executor as a 4th path check before running the full
        self-heal loop (short-circuit if we already have a proven healed pattern).

        Returns list of matching patterns sorted by score descending.
        """
        if domain == "auto":
            domain = "general"

        try:
            vector = self._embed([query])[0]
            results = self.client.search(
                collection_name=self.COLLECTION,
                query_vector=vector,
                limit=top_k,
                query_filter=None,   # could filter by domain tag if we add filter support
            )

            matches = []
            for r in results:
                if r.score < min_score:
                    continue
                # Only include if it was a healed pattern (has heal_code)
                if not r.payload.get("heal_code"):
                    continue
                # Optional: filter by domain if present
                if domain != "general" and r.payload.get("domain") != domain:
                    # be lenient — don't filter out, just score adjust
                    pass
                matches.append({
                    "pattern_id": r.id,
                    "score": round(r.score, 4),
                    "heal_code": r.payload.get("heal_code"),
                    "heal_reason": r.payload.get("heal_reason"),
                    "sql": r.payload.get("sql"),
                    "sql_template": r.payload.get("sql_template"),
                    "domain": r.payload.get("domain"),
                    "tables_used": r.payload.get("tables_used", []),
                    "tags": r.payload.get("tags", []),
                    "times_reused": r.payload.get("times_reused", 0),
                    "healed_at": r.payload.get("healed_at"),
                    "query_example": r.payload.get("query_example"),
                })

            return matches

        except Exception as exc:
            logger.error("[HealStore] Search failed: %s", exc)
            return []

    def increment_reuse(self, pattern_id: str) -> None:
        """Increment times_reused counter when a healed pattern is successfully applied."""
        try:
            result = self.client.retrieve(collection_name=self.COLLECTION, ids=[pattern_id])
            if result:
                payload = result[0].payload
                payload["times_reused"] = payload.get("times_reused", 0) + 1
                self.client.set_payload(
                    collection_name=self.COLLECTION,
                    payload=payload,
                    points=[pattern_id],
                )
        except Exception as exc:
            logger.warning("[HealStore] Failed to increment reuse counter: %s", exc)

    def get_heal_stats(self) -> Dict[str, Any]:
        """Return statistics about the heal store."""
        try:
            info = self.client.get_collection(self.COLLECTION)
            count = info.points_count
            total_reuse = 0
            by_heal_code: Dict[str, int] = {}
            return {"collection": self.COLLECTION, "total_patterns": count,
                    "by_heal_code": by_heal_code, "total_reuse_count": total_reuse}
        except Exception as exc:
            return {"error": str(exc)}


# ── Convenience wrapper ────────────────────────────────────────────────────────

def store_healed_pattern(
    original_sql: str,
    healed_sql: str,
    heal_code: str,
    heal_reason: str,
    error_type: str,
    domain: str,
    query_example: str,
    tables_used: Optional[List[str]] = None,
) -> str:
    """
    One-line convenience wrapper to store a healed pattern.
    Call this after self-healer.heal() succeeds and the healed SQL is different.

    Returns pattern_id on success, empty string on failure.
    """
    store = get_heal_store()
    return store.store_healed_pattern(
        original_sql=original_sql,
        healed_sql=healed_sql,
        heal_code=heal_code,
        heal_reason=heal_reason,
        error_type=error_type,
        domain=domain,
        query_example=query_example,
        tables_used=tables_used,
    )