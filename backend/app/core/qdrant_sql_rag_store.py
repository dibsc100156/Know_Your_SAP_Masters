"""
qdrant_sql_rag_store.py — Qdrant-backed SQL Pattern RAG Store
==========================================================
Drop-in replacement for SQLRAGStore (ChromaDB).
Stores proven SQL patterns as vectors in Qdrant for semantic retrieval.

Collection: sql_patterns_rag (384d, cosine)

Usage:
  from app.core.qdrant_sql_rag_store import QdrantSQLRAGStore
  store = QdrantSQLRAGStore(url="http://qdrant:6333")
  store.initialize_library()
  results = store.search("vendor payment terms", top_k=3)
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, Any, List, Optional


def _str_to_uuid(s: str) -> str:
    """Convert a string ID to a deterministic UUID5 (name-based)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, s))

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
COLLECTION_NAME = "sql_patterns_rag"


class QdrantSQLRAGStore:
    """
    Drop-in replacement for SQLRAGStore backed by Qdrant.
    API identical to SQLRAGStore: initialize_library(), search(), upsert_pattern()
    """

    def __init__(
        self,
        url: str = "http://qdrant:6333",
        collection_name: str = COLLECTION_NAME,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError("sentence-transformers not installed.")

        try:
            from qdrant_client import QdrantClient
        except ImportError:
            raise ImportError("qdrant-client not installed. Run: pip install qdrant-client>=1.7.0")

        self.url = url
        self.collection_name = collection_name
        self._client = QdrantClient(url=url, timeout=30.0, prefer_grpc=True)
        self._encoder = SentenceTransformer(EMBEDDING_MODEL)
        logger.info(f"[QdrantSQLRAGStore] Connected to {url}")

        self._ensure_collection()

    def _ensure_collection(self):
        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in self._client.get_collections().collections}
        if self.collection_name not in existing:
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=EMBEDDING_DIM,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"[Qdrant] Created collection: {self.collection_name}")
        else:
            logger.info(f"[Qdrant] Collection exists: {self.collection_name}")

    def initialize_library(self):
        """Seed all patterns from sql_library into Qdrant."""
        from app.core.sql_library import get_sql_library
        from qdrant_client.models import PointStruct

        library = get_sql_library()
        logger.info(f"[QdrantSQLRAGStore] Seeding {len(library)} SQL patterns...")

        ids, vectors, payloads = [], [], []
        for entry in library:
            text_to_embed = (
                f"Business Question: {entry['intent_description']} | "
                f"Variants: {' '.join(entry.get('natural_language_variants', []))}"
            )
            vector = self._encoder.encode(text_to_embed).tolist()
            ids.append(_str_to_uuid(entry["query_id"]))
            vectors.append(vector)
            payloads.append({
                "module": entry["module"],
                "tables_used": ",".join(entry["tables_used"]),
                "intent": entry["intent_description"],
                "document": entry["sql_template"],
                "variants": " | ".join(entry.get("natural_language_variants", [])),
                "_original_id": entry["query_id"],
            })

        if ids:
            # Use plain list for gRPC compatibility (PointsList doesn't auto-convert)
            self._client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(id=pid, vector=vec, payload=payload)
                    for pid, vec, payload in zip(ids, vectors, payloads)
                ],
            )
            logger.info(f"[QdrantSQLRAGStore] Seeded {len(ids)} patterns.")

    def search(
        self,
        query: str,
        top_k: int = 2,
        domain_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search over proven SQL patterns."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        query_vector = self._encoder.encode(query).tolist()

        qdrant_filter = None
        if domain_filter and domain_filter not in ("auto", "cross_module"):
            qdrant_filter = Filter(
                must=[
                    FieldCondition(
                        key="module",
                        match=MatchValue(value=domain_filter),
                    )
                ]
            )

        results = self._client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
            score_threshold=0.0,
        )

        retrieved = []
        for hit in results:
            payload = hit.payload or {}
            tables_raw = payload.get("tables_used", "")
            retrieved.append({
                "query_id": payload.get("_original_id", str(hit.id)),
                "intent": payload.get("intent", ""),
                "sql_template": payload.get("document", payload.get("sql_template", "")),
                "tables_used": tables_raw.split(",") if tables_raw else [],
                "score": hit.score,  # cosine similarity (1.0 = identical)
            })
        return retrieved

    def upsert_pattern(self, entry: Dict[str, Any]) -> bool:
        """Add or update a single SQL pattern at runtime."""
        from qdrant_client.models import PointStruct

        text_to_embed = (
            f"Business Question: {entry.get('intent_description', '')} | "
            f"Variants: {' '.join(entry.get('natural_language_variants', []))}"
        )
        vector = self._encoder.encode(text_to_embed).tolist()

        try:
            # Use plain list for gRPC compatibility
            self._client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=_str_to_uuid(entry["query_id"]),
                        vector=vector,
                        payload={
                            "module": entry.get("module", ""),
                            "tables_used": ",".join(entry.get("tables_used", [])),
                            "intent": entry.get("intent_description", ""),
                            "document": entry.get("sql_template", ""),
                            "variants": " | ".join(entry.get("natural_language_variants", [])),
                            "_original_id": entry["query_id"],
                        },
                    )
                ],
            )
            logger.info(f"[QdrantSQLRAGStore] Upserted: {entry['query_id']}")
            return True
        except Exception as e:
            logger.error(f"[QdrantSQLRAGStore] Upsert failed: {e}")
            return False

    def stats(self) -> Dict[str, Any]:
        """Return collection stats."""
        try:
            info = self._client.get_collection(self.collection_name)
            return {
                "backend": "qdrant",
                "url": self.url,
                "collection": self.collection_name,
                "points": info.vectors_count,
                "indexed_vectors": info.indexed_vectors_count,
            }
        except Exception as e:
            return {"backend": "qdrant", "error": str(e)}
