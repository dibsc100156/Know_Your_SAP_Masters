"""
qdrant_vector_store.py — Qdrant-backed Schema RAG Store
=====================================================
Drop-in replacement for VectorStoreManager (ChromaDB).
Migrates from file-based ChromaDB to distributed Qdrant cluster.

IMPORTANT: Qdrant 1.7.x requires point IDs to be unsigned integers or UUIDs.
String IDs like 'LFA1' are NOT valid — they must be converted to UUIDs.

Why Qdrant over ChromaDB:
  ✓ Distributed cluster — multiple replicas, horizontal read scale
  ✓ gRPC API (port 6334) — much faster for high-throughput embedding search
  ✓ Named vectors — can store both text and structural embeddings in same collection
  ✓ Production-grade — WAL, snapshots, consistent hashing
  ✓ Payload filtering — rich metadata filtering at query time
  ✓ No local filesystem dependency — works with Docker/K8s volumes

Collection layout:
  sap_schema      (384d, cosine) — DDIC table metadata, domain-filterable
  sap_sql_patterns (384d, cosine) — proven SQL patterns, domain-filterable

Usage:
  from app.core.qdrant_vector_store import QdrantVectorStoreManager

  vm = QdrantVectorStoreManager(url="http://qdrant:6333")
  vm.load_all_domains()          # seed all 18 domains
  results = vm.search_schema("vendor master data", domain="business_partner")
"""

from __future__ import annotations

import os
import logging
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import dataclass


def _str_to_uuid(s: str) -> str:
    """Convert a string ID to a deterministic UUID5 (name-based)."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, s))

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
SCHEMA_COLLECTION = "sap_schema"
SQL_COLLECTION = "sap_sql_patterns"

_STUB_SCHEMAS = {
    "sales_distribution":    ("sales_distribution_schema",    "SALES_DISTRIBUTION_TABLES",    "SALES_DISTRIBUTION_SQL_PATTERNS"),
    "warehouse_management":   ("warehouse_management_schema",   "WAREHOUSE_MANAGEMENT_TABLES",   "WAREHOUSE_MANAGEMENT_SQL_PATTERNS"),
    "quality_management":     ("quality_management_schema",     "QUALITY_MANAGEMENT_TABLES",     "QUALITY_MANAGEMENT_SQL_PATTERNS"),
    "project_system":        ("project_system_schema",        "PROJECT_SYSTEM_TABLES",        "PROJECT_SYSTEM_SQL_PATTERNS"),
    "transportation":        ("transportation_schema",        "TRANSPORTATION_TABLES",        "TRANSPORTATION_SQL_PATTERNS"),
    "customer_service":      ("customer_service_schema",      "CUSTOMER_SERVICE_TABLES",      "CUSTOMER_SERVICE_SQL_PATTERNS"),
    "ehs":                   ("ehs_schema",                   "EHS_TABLES",                   "EHS_SQL_PATTERNS"),
    "variant_configuration":  ("variant_configuration_schema", "VARIANT_CONFIGURATION_TABLES", "VARIANT_CONFIGURATION_SQL_PATTERNS"),
    "real_estate":           ("real_estate_schema",           "REAL_ESTATE_TABLES",           "REAL_ESTATE_SQL_PATTERNS"),
    "gts":                   ("gts_schema",                   "GTS_TABLES",                   "GTS_SQL_PATTERNS"),
    "is_oil":                ("is_oil_schema",                "IS_OIL_TABLES",                "IS_OIL_TABLES"),
    "is_retail":             ("is_retail_schema",             "IS_RETAIL_TABLES",             "IS_RETAIL_SQL_PATTERNS"),
    "is_utilities":          ("is_utilities_schema",          "IS_UTILITIES_TABLES",          "IS_UTILITIES_SQL_PATTERNS"),
    "is_health":             ("is_health_schema",             "IS_HEALTH_TABLES",             "IS_HEALTH_SQL_PATTERNS"),
    "taxation_india":         ("taxation_india_schema",        "TAXATION_INDIA_TABLES",        "TAXATION_INDIA_SQL_PATTERNS"),
}

logger = logging.getLogger(__name__)


def _load_stub_domain(domain_name: str):
    module_name, tables_var, patterns_var = _STUB_SCHEMAS[domain_name]
    module = __import__(f"app.domain.{module_name}", fromlist=[tables_var, patterns_var])
    tables = getattr(module, tables_var, {})
    patterns = getattr(module, patterns_var, [])
    return tables, patterns


def _get_qdrant_client(url, grpc_port, prefer_grpc, vector_cache_size):
    from qdrant_client import QdrantClient
    return QdrantClient(
        url=url,
        port=grpc_port,
        timeout=30.0,
        prefer_grpc=prefer_grpc,
        vector_cache_size=vector_cache_size,
    )


class QdrantVectorStoreManager:
    """
    Drop-in replacement for VectorStoreManager backed by Qdrant.

    Two collections:
      - sap_schema       : DDIC table metadata (18 domains, ~500+ tables)
      - sap_sql_patterns: Proven SQL patterns (~68 patterns)

    API compatibility: same search_schema(), search_sql_patterns(),
                       load_domain(), load_all_domains()
    """

    def __init__(
        self,
        url: str = "http://qdrant:6333",
        grpc_port: int = 6334,
        prefer_grpc: bool = True,
    ):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. Run: pip install sentence-transformers"
            )

        try:
            from qdrant_client import QdrantClient
        except ImportError:
            raise ImportError(
                "qdrant-client not installed. Run: pip install qdrant-client>=1.7.0"
            )

        self.url = url
        self.grpc_port = grpc_port
        self.prefer_grpc = prefer_grpc

        self._client = QdrantClient(
            url=url,
            port=grpc_port,
            timeout=30.0,
            prefer_grpc=prefer_grpc,
        )
        self._encoder = SentenceTransformer(EMBEDDING_MODEL)
        logger.info(f"[QdrantVectorStoreManager] Connected to {url} (gRPC={prefer_grpc})")

        self._ensure_collections()

    # ── Collection setup ──────────────────────────────────────────────────────

    def _ensure_collections(self):
        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in self._client.get_collections().collections}

        for coll_name, coll_desc in [
            (SCHEMA_COLLECTION, "DDIC schema"),
            (SQL_COLLECTION, "SQL patterns"),
        ]:
            if coll_name not in existing:
                self._client.create_collection(
                    collection_name=coll_name,
                    vectors_config=VectorParams(
                        size=EMBEDDING_DIM,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"[Qdrant] Created collection: {coll_name} ({coll_desc})")
            else:
                logger.info(f"[Qdrant] Collection exists: {coll_name}")

    # ── Schema RAG ────────────────────────────────────────────────────────────

    def load_domain(self, domain_name: str, tables: Dict[str, Any], patterns: List[Dict[str, Any]]):
        """Load a domain's tables + patterns into Qdrant."""
        logger.info(
            f"[Qdrant] Loading domain: {domain_name} "
            f"({len(tables)} tables, {len(patterns)} patterns)"
        )

        from qdrant_client.models import PointStruct, Distance, VectorParams

        # 1. Embed tables
        if tables:
            ids, vectors, payloads = [], [], []
            for table_name, table_def in tables.items():
                col_desc = ", ".join([
                    f"{col['name']} ({col.get('type', '')}) : {col.get('desc', '')}"
                    for col in table_def.get("columns", [])
                ])
                doc_content = (
                    f"Table {table_name} — {table_def.get('description', '')}. "
                    f"Columns: {col_desc}"
                )
                vector = self._encoder.encode(doc_content).tolist()
                ids.append(_str_to_uuid(f"schema_{domain_name}_{table_name}"))
                vectors.append(vector)
                payloads.append({
                    "table": table_name,
                    "module": table_def.get("module", ""),
                    "domain": domain_name,
                    "document": doc_content,
                    "_original_id": f"schema_{domain_name}_{table_name}",  # preserve original for debug
                })

            if ids:
                self._client.upsert(
                    collection_name=SCHEMA_COLLECTION,
                    points=[
                        PointStruct(id=pid, vector=vec, payload=payload)
                        for pid, vec, payload in zip(ids, vectors, payloads)
                    ],
                )
                logger.info(f"[Qdrant] Upserted {len(ids)} table records for {domain_name}")

        # 2. Embed SQL patterns
        if patterns:
            ids, vectors, payloads = [], [], []
            for i, pattern in enumerate(patterns):
                doc_content = pattern.get("intent", "") + " | " + pattern.get("sql", "")
                vector = self._encoder.encode(doc_content).tolist()
                ids.append(_str_to_uuid(f"sql_{domain_name}_{i}"))
                vectors.append(vector)
                payloads.append({
                    "intent": pattern.get("intent", ""),
                    "domain": domain_name,
                    "document": doc_content,
                    "sql": pattern.get("sql", ""),
                    "_original_id": f"sql_{domain_name}_{i}",
                })

            if ids:
                self._client.upsert(
                    collection_name=SQL_COLLECTION,
                    points=[
                        PointStruct(id=pid, vector=vec, payload=payload)
                        for pid, vec, payload in zip(ids, vectors, payloads)
                    ],
                )
                logger.info(f"[Qdrant] Upserted {len(ids)} SQL patterns for {domain_name}")

    def load_all_domains(self):
        """Seed all 18+ SAP domains into Qdrant."""
        logger.info("[Qdrant] Seeding all domains...")

        from app.domain.business_partner_schema import BUSINESS_PARTNER_TABLES, BUSINESS_PARTNER_SQL_PATTERNS
        from app.domain.material_master_schema import MATERIAL_MASTER_TABLES, MATERIAL_MASTER_SQL_PATTERNS
        from app.domain.purchasing_schema import PURCHASING_TABLES, PURCHASING_SQL_PATTERNS

        self.load_domain("business_partner", BUSINESS_PARTNER_TABLES, BUSINESS_PARTNER_SQL_PATTERNS)
        self.load_domain("material_master", MATERIAL_MASTER_TABLES, MATERIAL_MASTER_SQL_PATTERNS)
        self.load_domain("purchasing", PURCHASING_TABLES, PURCHASING_SQL_PATTERNS)

        for domain_name in sorted(_STUB_SCHEMAS.keys()):
            tables, patterns = _load_stub_domain(domain_name)
            real_tables = {t: v for t, v in tables.items() if len(v.get("columns", [])) > 1}
            if real_tables:
                self.load_domain(domain_name, real_tables, patterns)
            else:
                logger.info(f"[Qdrant] {domain_name}: SKIPPED (stub domain)")

        logger.info("[Qdrant] All domains seeded.")

    def search_schema(
        self,
        query: str,
        n_results: int = 4,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over DDIC table metadata.
        Identical signature to VectorStoreManager.search_schema().
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        query_vector = self._encoder.encode(query).tolist()

        qdrant_filter = None
        if domain and domain not in (
            "auto", "cross_module_purchasing", "transactional_purchasing",
            "cross_module", "transactional"
        ):
            qdrant_filter = Filter(
                must=[
                    FieldCondition(
                        key="domain",
                        match=MatchValue(value=domain),
                    )
                ]
            )

        results = self._client.search(
            collection_name=SCHEMA_COLLECTION,
            query_vector=query_vector,
            limit=n_results,
            query_filter=qdrant_filter,
            with_payload=True,
            score_threshold=0.0,
        )

        return [
            {
                "document": hit.payload.get("document", ""),
                "metadata": {
                    "table": hit.payload.get("table", ""),
                    "module": hit.payload.get("module", ""),
                    "domain": hit.payload.get("domain", ""),
                },
                "score": hit.score,
            }
            for hit in results
        ]

    def search_sql_patterns(
        self,
        query: str,
        n_results: int = 2,
        domain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search over proven SQL patterns (few-shot injection).
        Identical signature to VectorStoreManager.search_sql_patterns().
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        query_vector = self._encoder.encode(query).tolist()

        qdrant_filter = None
        if domain and domain not in (
            "auto", "cross_module_purchasing", "transactional_purchasing",
            "cross_module", "transactional"
        ):
            qdrant_filter = Filter(
                must=[
                    FieldCondition(
                        key="domain",
                        match=MatchValue(value=domain),
                    )
                ]
            )

        results = self._client.search(
            collection_name=SQL_COLLECTION,
            query_vector=query_vector,
            limit=n_results,
            query_filter=qdrant_filter,
            with_payload=True,
            score_threshold=0.0,
        )

        return [
            {
                "intent": hit.payload.get("intent", ""),
                "sql": hit.payload.get("sql", hit.payload.get("document", "")),
                "score": hit.score,
            }
            for hit in results
        ]

    # ── Stats / health ────────────────────────────────────────────────────────

    def count(self, collection: Optional[str] = None) -> Dict[str, int]:
        """Return point counts per collection."""
        sc = self._client.get_collection(SCHEMA_COLLECTION).vectors_count
        sqlc = self._client.get_collection(SQL_COLLECTION).vectors_count
        if collection is None:
            return {SCHEMA_COLLECTION: sc, SQL_COLLECTION: sqlc}
        return {collection: sc if collection == SCHEMA_COLLECTION else sqlc}

    def stats(self) -> Dict[str, Any]:
        """Return Qdrant cluster stats."""
        try:
            sc_info = self._client.get_collection(SCHEMA_COLLECTION)
            return {
                "backend": "qdrant",
                "url": self.url,
                "schema_points": sc_info.vectors_count,
                "sql_pattern_points": self._client.get_collection(SQL_COLLECTION).vectors_count,
                "indexed": sc_info.indexed_vectors_count,
            }
        except Exception as e:
            return {"backend": "qdrant", "error": str(e)}


# ── Alias + singleton for backward compatibility ───────────────────────────────

VectorStoreManager = QdrantVectorStoreManager

_store_manager_instance: Optional[QdrantVectorStoreManager] = None


def get_store_manager(url: str = "http://qdrant:6333") -> QdrantVectorStoreManager:
    """Get or create the singleton Qdrant store manager."""
    global _store_manager_instance
    if _store_manager_instance is None:
        _store_manager_instance = QdrantVectorStoreManager(url=url)
    return _store_manager_instance


def init_vector_store(url: str = "http://qdrant:6333"):
    """Seed Qdrant if collections are empty. Call on FastAPI startup."""
    vm = get_store_manager(url)
    counts = vm.count()
    total = sum(counts.values())
    if total == 0:
        logger.info("[Qdrant] Collections empty. Seeding all domains...")
        vm.load_all_domains()
    else:
        logger.info(f"[Qdrant] Already populated: {counts}")
    return vm
