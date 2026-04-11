"""
vector_store.py — Dual-Backend Vector Store (ChromaDB + Qdrant)
==============================================================
Unified vector store for Schema RAG (DDIC metadata) and SQL Pattern RAG.

Backends:
  ChromaDB (default) — file-based, no external service needed
  Qdrant  (opt-in)  — clustered, persistent, better for horizontal scale

Usage:
  # ChromaDB (default, no setup needed)
  store = VectorStoreManager(backend="chroma", db_path="./chroma_db")

  # Qdrant (set env vars first)
  store = VectorStoreManager(backend="qdrant")
  # Or:
  from qdrant_client import QdrantClient
  client = QdrantClient(url="http://localhost:6333")
  store = VectorStoreManager(backend="qdrant", qdrant_client=client)

Environment variables (Qdrant):
  QDRANT_HOST  — default: localhost
  QDRANT_PORT  — default: 6333
  QDRANT_HTTPS — default: false (set to "true" for HTTPS)
  QDRANT_GRPC_PORT — default: 6334

Collections:
  sap_schema        — DDIC table metadata (384-dim, cosine)
  sql_patterns      — proven SQL patterns (384-dim, cosine)

M6 Migration (April 7, 2026):
  - ChromaDB remains the default for backward compatibility
  - Qdrant is fully wired and verified (container running at localhost:6333)
  - set_vector_store_backend("qdrant") to switch at runtime
"""

from __future__ import annotations

import os
import logging
from typing import Dict, Any, List, Optional

import chromadb

from app.domain.business_partner_schema import BUSINESS_PARTNER_TABLES, BUSINESS_PARTNER_SQL_PATTERNS
from app.domain.material_master_schema import MATERIAL_MASTER_TABLES, MATERIAL_MASTER_SQL_PATTERNS
from app.domain.purchasing_schema import PURCHASING_TABLES, PURCHASING_SQL_PATTERNS

logger = logging.getLogger(__name__)

# ── Stub domain registry ───────────────────────────────────────────────────────

_STUB_SCHEMAS: Dict[str, tuple] = {
    "sales_distribution":      ("sales_distribution_schema",    "SALES_DISTRIBUTION_TABLES",    "SALES_DISTRIBUTION_SQL_PATTERNS"),
    "warehouse_management":   ("warehouse_management_schema",   "WAREHOUSE_MANAGEMENT_TABLES",   "WAREHOUSE_MANAGEMENT_SQL_PATTERNS"),
    "quality_management":     ("quality_management_schema",    "QUALITY_MANAGEMENT_TABLES",     "QUALITY_MANAGEMENT_SQL_PATTERNS"),
    "project_system":        ("project_system_schema",         "PROJECT_SYSTEM_TABLES",         "PROJECT_SYSTEM_SQL_PATTERNS"),
    "transportation":        ("transportation_schema",         "TRANSPORTATION_TABLES",         "TRANSPORTATION_SQL_PATTERNS"),
    "customer_service":      ("customer_service_schema",       "CUSTOMER_SERVICE_TABLES",       "CUSTOMER_SERVICE_SQL_PATTERNS"),
    "ehs":                   ("ehs_schema",                    "EHS_TABLES",                    "EHS_SQL_PATTERNS"),
    "variant_configuration":  ("variant_configuration_schema",  "VARIANT_CONFIGURATION_TABLES",  "VARIANT_CONFIGURATION_SQL_PATTERNS"),
    "real_estate":           ("real_estate_schema",            "REAL_ESTATE_TABLES",            "REAL_ESTATE_SQL_PATTERNS"),
    "gts":                   ("gts_schema",                    "GTS_TABLES",                    "GTS_SQL_PATTERNS"),
    "is_oil":                ("is_oil_schema",                 "IS_OIL_TABLES",                 "IS_OIL_SQL_PATTERNS"),
    "is_retail":             ("is_retail_schema",              "IS_RETAIL_TABLES",              "IS_RETAIL_SQL_PATTERNS"),
    "is_utilities":          ("is_utilities_schema",           "IS_UTILITIES_TABLES",           "IS_UTILITIES_TABLES"),
    "is_health":             ("is_health_schema",               "IS_HEALTH_TABLES",             "IS_HEALTH_TABLES"),
    "taxation_india":        ("taxation_india_schema",         "TAXATION_INDIA_TABLES",         "TAXATION_INDIA_SQL_PATTERNS"),
}


def _load_stub_domain(domain_name: str) -> tuple:
    module_name, tables_var, patterns_var = _STUB_SCHEMAS[domain_name]
    module = __import__(f"app.domain.{module_name}", fromlist=[tables_var, patterns_var])
    tables = getattr(module, tables_var, {})
    patterns = getattr(module, patterns_var, [])
    return tables, patterns


# ── Backend adapters ───────────────────────────────────────────────────────────

class ChromaDBAdapter:
    """ChromaDB backend — file-based, zero-setup, single-process."""

    NAME = "chroma"
    SCHEMA_COLLECTION = "sap_master_schemas"
    SQL_COLLECTION = "sap_sql_patterns"

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.client = chromadb.PersistentClient(path=db_path)
        
        # Lazy load or fallback to system Python for torch issues
        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_fn = SentenceTransformer("all-MiniLM-L6-v2")
        except OSError:
            import sys as _sys
            import pathlib as _pathlib
            _sys.path.insert(0, str(_pathlib.Path(_sys.prefix).parent / "Lib" / "site-packages"))
            from sentence_transformers import SentenceTransformer
            self.embedding_fn = SentenceTransformer("all-MiniLM-L6-v2")

        self.schema_collection = self.client.get_or_create_collection(
            name=self.SCHEMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self.sql_collection = self.client.get_or_create_collection(
            name=self.SQL_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def load_domain(self, domain_name: str, tables: Dict, patterns: List[Dict]):
        logger.info(f"[ChromaDB] Loading {domain_name}...")

        if tables:
            ids, vecs, metas, docs = [], [], [], []
            for table_name, table_def in tables.items():
                col_desc = ", ".join(
                    f"{c['name']} ({c.get('type', '')}) : {c.get('desc', '')}"
                    for c in table_def.get("columns", [])
                )
                doc = (
                    f"Table {table_name} - {table_def.get('description', '')}."
                    f" Columns: {col_desc}"
                )
                ids.append(f"schema_{domain_name}_{table_name}")
                vecs.append(self.embedding_fn.encode(doc).tolist())
                docs.append(doc)
                metas.append({
                    "table": table_name,
                    "module": table_def.get("module", ""),
                    "domain": domain_name,
                })
            if ids:
                self.schema_collection.upsert(
                    ids=ids, embeddings=vecs, metadatas=metas, documents=docs
                )

        if patterns:
            ids, vecs, metas, docs = [], [], [], []
            for i, pat in enumerate(patterns):
                ids.append(f"sql_{domain_name}_{i}")
                vecs.append(self.embedding_fn.encode(pat["intent"]).tolist())
                docs.append(pat["sql"])
                metas.append({"intent": pat["intent"], "domain": domain_name})
            if ids:
                self.sql_collection.upsert(
                    ids=ids, embeddings=vecs, metadatas=metas, documents=docs
                )

        logger.info(f"[ChromaDB] {domain_name} loaded.")

    def search_schema(
        self, query: str, n_results: int = 4, domain: str = None
    ) -> List[Dict]:
        vec = self.embedding_fn.encode(query).tolist()
        where = {"domain": domain} if domain and domain not in (
            "auto", "cross_module_purchasing", "transactional_purchasing",
            "cross_module", "transactional"
        ) else None

        res = self.schema_collection.query(
            query_embeddings=[vec],
            n_results=n_results,
            where=where,
        )

        out = []
        if res.get("documents"):
            for i in range(len(res["documents"][0])):
                out.append({
                    "document": res["documents"][0][i],
                    "metadata": res["metadatas"][0][i] if res["metadatas"] else {},
                })
        return out

    def search_sql_patterns(
        self, query: str, n_results: int = 2, domain: str = None
    ) -> List[Dict]:
        vec = self.embedding_fn.encode(query).tolist()
        where = {"domain": domain} if domain and domain not in (
            "auto", "cross_module_purchasing", "transactional_purchasing",
            "cross_module", "transactional"
        ) else None

        res = self.sql_collection.query(
            query_embeddings=[vec],
            n_results=n_results,
            where=where,
        )

        out = []
        if res.get("documents"):
            for i in range(len(res["documents"][0])):
                meta = res["metadatas"][0][i] if res["metadatas"] else {}
                out.append({
                    "intent": meta.get("intent", ""),
                    "sql": res["documents"][0][i],
                })
        return out

    def count(self) -> int:
        return self.schema_collection.count()

    def clear(self):
        try:
            self.client.delete_collection(self.SCHEMA_COLLECTION)
            self.client.delete_collection(self.SQL_COLLECTION)
            logger.info("[ChromaDB] Collections deleted.")
        except Exception:
            pass


class QdrantAdapter:
    """Qdrant backend — clustered, persistent, horizontally scalable."""

    NAME = "qdrant"
    SCHEMA_COLLECTION = "sap_schema"
    SQL_COLLECTION = "sql_patterns"
    VECTOR_SIZE = 384          # all-MiniLM-L6-v2 dimension
    DISTANCE = "Cosine"

    def __init__(
        self,
        *,
        url: str = None,
        host: str = "localhost",
        port: int = 6333,
        grpc_port: int = 6334,
        https: bool = False,
        location: str = None,
    ):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        # Resolve host from env
        host = os.environ.get("QDRANT_HOST", host)
        port = int(os.environ.get("QDRANT_PORT", port))
        https = os.environ.get("QDRANT_HTTPS", "false").lower() == "true"
        url = url or os.environ.get("QDRANT_URL")

        self._url = url
        self._host = host
        self._port = port
        self._https = https
        self._grpc_port = int(os.environ.get("QDRANT_GRPC_PORT", grpc_port))

        # Use host+port mode (not url=) — this enables automatic gRPC
        # detection when port 6334 is reachable. gRPC is ~10x faster
        # than HTTP for high-throughput vector operations.
        self.client = QdrantClient(
            host=host if not url else None,
            port=port if not url else None,
            url=url,
            https=https,
            timeout=10,
            prefer_grpc=True,
        )
        # Lazy encoder — only loaded on first search. Handles broken venv torch gracefully.
        self._embedding_fn = None

    def _get_encoder(self):
        """Lazily load SentenceTransformer, falling back to system Python if venv torch is broken."""
        if self._embedding_fn is not None:
            return self._embedding_fn
        try:
            from sentence_transformers import SentenceTransformer
            self._embedding_fn = SentenceTransformer("all-MiniLM-L6-v2")
            return self._embedding_fn
        except OSError as e:
            if "torch" in str(e) or "shm.dll" in str(e):
                import sys as _sys
                import logging as _logging
                _logging.warning(
                    "[QdrantAdapter] Venv torch broken — routing encoder through system Python. "
                    "This is a startup workaround. Fix: reinstall torch in the venv."
                )
                # Use system Python for encoding only
                _sys.path.insert(0, str(_sys.prefix.parent / "Lib" / "site-packages"))
                from sentence_transformers import SentenceTransformer as _ST
                self._embedding_fn = _ST("all-MiniLM-L6-v2")
                return self._embedding_fn
            raise

        # Ensure collections exist
        self._ensure_collection(self.SCHEMA_COLLECTION)
        self._ensure_collection(self.SQL_COLLECTION)

        logger.info(
            f"[Qdrant] Connected to {host}:{port} (gRPC={'yes' if self.client._client._prefer_grpc else 'no'}, https={https}) "
            f"collections=({self.SCHEMA_COLLECTION}, {self.SQL_COLLECTION})"
        )

    def _ensure_collection(self, name: str):
        from qdrant_client.models import Distance, VectorParams, OptimizersConfigDiff

        collections = [c.name for c in self.client.get_collections().collections]
        if name not in collections:
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(
                    size=self.VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
                optimizers_config=OptimizersConfigDiff(
                    indexing_threshold=20000,  # 20k vectors before HNSW indexing kicks in
                ),
            )
            logger.info(f"[Qdrant] Created collection: {name}")

    def _str_to_uuid(self, s: str) -> str:
        """Convert a string ID to a valid UUID v5 (deterministic)."""
        import hashlib, uuid as _uuid
        return str(_uuid.UUID(bytes=hashlib.md5(s.encode("utf-8")).digest()[:16]))

    def _upsert(
        self,
        collection_name: str,
        ids: List[str],
        vectors: List[List[float]],
        payloads: List[Dict],
    ):
        from qdrant_client.models import PointStruct

        # gRPC requires UUID-formatted IDs — convert string IDs to deterministic UUIDs
        points = [
            PointStruct(
                id=self._str_to_uuid(_id),
                vector=vec,
                payload=payload,
            )
            for _id, vec, payload in zip(ids, vectors, payloads)
        ]
        self.client.upsert(collection_name=collection_name, points=points, wait=True)

    def load_domain(self, domain_name: str, tables: Dict, patterns: List[Dict]):
        logger.info(f"[Qdrant] Loading {domain_name}...")

        if tables:
            self._ensure_collection(self.SCHEMA_COLLECTION)
            ids, vecs, payloads = [], [], []
            for table_name, table_def in tables.items():
                col_desc = ", ".join(
                    f"{c['name']} ({c.get('type', '')}) : {c.get('desc', '')}"
                    for c in table_def.get("columns", [])
                )
                doc = (
                    f"Table {table_name} - {table_def.get('description', '')}."
                    f" Columns: {col_desc}"
                )
                ids.append(f"schema_{domain_name}_{table_name}")
                vecs.append(self._get_encoder().encode(doc).tolist())
                payloads.append({
                    "document": doc,
                    "table": table_name,
                    "module": table_def.get("module", ""),
                    "domain": domain_name,
                })
            if ids:
                self._upsert(self.SCHEMA_COLLECTION, ids, vecs, payloads)

        if patterns:
            self._ensure_collection(self.SQL_COLLECTION)
            ids, vecs, payloads = [], [], []
            for i, pat in enumerate(patterns):
                ids.append(f"sql_{domain_name}_{i}")
                vecs.append(self._get_encoder().encode(pat["intent"]).tolist())
                payloads.append({
                    "intent": pat["intent"],
                    "sql": pat["sql"],
                    "domain": domain_name,
                })
            if ids:
                self._upsert(self.SQL_COLLECTION, ids, vecs, payloads)

        logger.info(f"[Qdrant] {domain_name} loaded.")

    def search_schema(
        self, query: str, n_results: int = 4, domain: str = None
    ) -> List[Dict]:
        vec = self._get_encoder().encode(query).tolist()

        # Build filter
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        filter_cond = None
        if domain and domain not in (
            "auto", "cross_module_purchasing", "transactional_purchasing",
            "cross_module", "transactional"
        ):
            filter_cond = Filter(
                must=[FieldCondition(key="domain", match=MatchValue(value=domain))]
            )

        results = self.client.search(
            collection_name=self.SCHEMA_COLLECTION,
            query_vector=vec,
            limit=n_results,
            query_filter=filter_cond,
            with_payload=True,
        )

        return [
            {
                "document": r.payload.get("document", ""),
                "metadata": {
                    "table": r.payload.get("table", ""),
                    "module": r.payload.get("module", ""),
                    "domain": r.payload.get("domain", ""),
                },
            }
            for r in results
        ]

    def search_sql_patterns(
        self, query: str, n_results: int = 2, domain: str = None
    ) -> List[Dict]:
        vec = self._get_encoder().encode(query).tolist()

        from qdrant_client.models import Filter, FieldCondition, MatchValue
        filter_cond = None
        if domain and domain not in (
            "auto", "cross_module_purchasing", "transactional_purchasing",
            "cross_module", "transactional"
        ):
            filter_cond = Filter(
                must=[FieldCondition(key="domain", match=MatchValue(value=domain))]
            )

        results = self.client.search(
            collection_name=self.SQL_COLLECTION,
            query_vector=vec,
            limit=n_results,
            query_filter=filter_cond,
            with_payload=True,
        )

        return [
            {
                "intent": r.payload.get("intent", ""),
                "sql": r.payload.get("sql", ""),
            }
            for r in results
        ]

    def count(self) -> int:
        try:
            cnt = self.client.count(self.SCHEMA_COLLECTION, exact=True)
            return cnt.count
        except Exception:
            return 0

    def clear(self):
        for name in [self.SCHEMA_COLLECTION, self.SQL_COLLECTION]:
            try:
                self.client.delete_collection(name)
                logger.info(f"[Qdrant] Deleted collection: {name}")
            except Exception:
                pass


# ── Unified VectorStoreManager ─────────────────────────────────────────────────

_BACKEND_CACHE: Optional[object] = None
_ACTIVE_BACKEND_NAME: Optional[str] = None


class VectorStoreManager:
    """
    Unified vector store for Schema RAG and SQL Pattern RAG.

    Supports two backends (ChromaDB default, Qdrant opt-in).
    Switching backend does NOT re-index — each backend maintains its own index.

    Usage:
        # ChromaDB (default)
        store = VectorStoreManager(backend="chroma")

        # Qdrant
        store = VectorStoreManager(backend="qdrant")

        # Switch at runtime
        set_vector_store_backend("qdrant")
    """

    def __init__(
        self,
        *,
        backend: str = None,
        db_path: str = None,
        **kwargs,
    ):
        # Resolve backend from env if not specified
        backend = backend or os.environ.get("VECTOR_STORE_BACKEND", "chroma")
        db_path = db_path or os.environ.get("CHROMA_DB_PATH", "./chroma_db")
        self._backend_name = backend

        if backend == "qdrant":
            self._be: Any = QdrantAdapter(**kwargs)
        else:
            # ChromaDB default
            self._be = ChromaDBAdapter(db_path=db_path)

        logger.info(f"[VectorStoreManager] Backend: {backend} ({self._be.__class__.__name__})")

    # ── Domain loading ──────────────────────────────────────────────────────

    def load_domain(self, domain_name: str, tables: Dict, patterns: List[Dict]):
        self._be.load_domain(domain_name, tables, patterns)

    def load_all_domains(self):
        """Load all 18 SAP domains into the vector store."""
        self.load_domain("business_partner", BUSINESS_PARTNER_TABLES, BUSINESS_PARTNER_SQL_PATTERNS)
        self.load_domain("material_master", MATERIAL_MASTER_TABLES, MATERIAL_MASTER_SQL_PATTERNS)
        self.load_domain("purchasing", PURCHASING_TABLES, PURCHASING_SQL_PATTERNS)

        for domain_name in sorted(_STUB_SCHEMAS.keys()):
            tables, patterns = _load_stub_domain(domain_name)
            real_tables = {t: v for t, v in tables.items() if len(v.get("columns", [])) > 1}
            if real_tables:
                self.load_domain(domain_name, real_tables, patterns)
            else:
                logger.info(f"[{self._backend_name.upper()}] {domain_name}: SKIPPED (stub)")

    # ── Search ───────────────────────────────────────────────────────────────

    def search_schema(self, query: str, n_results: int = 4, domain: str = None) -> List[Dict]:
        return self._be.search_schema(query, n_results=n_results, domain=domain)

    def search_sql_patterns(self, query: str, n_results: int = 2, domain: str = None) -> List[Dict]:
        return self._be.search_sql_patterns(query, n_results=n_results, domain=domain)

    # ── Stats ────────────────────────────────────────────────────────────────

    def count(self) -> int:
        return self._be.count()

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def clear(self):
        """Delete all vectors from the current backend. Use with caution."""
        self._be.clear()


def set_vector_store_backend(backend: str, **kwargs) -> VectorStoreManager:
    """
    Switch vector store backend at runtime.

    Args:
        backend: "chroma" or "qdrant"
        **kwargs: passed to backend adapter

    Returns:
        new VectorStoreManager (also sets the global store_manager)
    """
    global store_manager, _BACKEND_CACHE, _ACTIVE_BACKEND_NAME
    _BACKEND_CACHE = None
    _ACTIVE_BACKEND_NAME = None
    store_manager = VectorStoreManager(backend=backend, **kwargs)
    return store_manager


# ── Module-level lazy singleton (avoids ChromaDB init at import time) ──────────────
# Rationale: ChromaDB v0.4 (system Python) conflicts with ./chroma_db (v1.5.x backend
# venv). By deferring adapter creation until first actual use, we let Qdrant-only
# deployments avoid ChromaDB entirely.
#
# Usage:
#   from app.core.vector_store import store_manager  # same API as before
#   results = store_manager.search_schema(...)

db_path_default = os.path.expanduser("~/.openclaw/workspace/chroma_db")
if not os.path.exists(db_path_default):
    db_path_default = "./chroma_db"


class _LazyStoreManager:
    """Lazy proxy: defers VectorStoreManager creation until first attribute access.

    This prevents ChromaDB (system Python v0.4) from opening the ./chroma_db
    directory when the deployment only uses Qdrant.
    """

    __slots__ = ("_real", "_backend_override")

    def __init__(self, backend_override: str = None):
        self._real: VectorStoreManager = None
        self._backend_override = backend_override

    def _resolve(self) -> VectorStoreManager:
        if self._real is None:
            backend = self._backend_override or os.environ.get(
                "VECTOR_STORE_BACKEND", "chroma"
            )
            if backend == "qdrant":
                self._real = VectorStoreManager(backend="qdrant")
            else:
                self._real = VectorStoreManager(backend="chroma", db_path=db_path_default)
        return self._real

    def __getattr__(self, name):
        return getattr(self._resolve(), name)

    def __repr__(self):
        return repr(self._resolve())


store_manager: VectorStoreManager = _LazyStoreManager()


def init_vector_store(backend: str = None) -> VectorStoreManager:
    """
    Initialize the vector store and load all domains.
    Call once at startup.

    Args:
        backend: "chroma" or "qdrant".
                Defaults to VECTOR_STORE_BACKEND env var or "chroma".
    """
    backend = backend or os.environ.get("VECTOR_STORE_BACKEND", "chroma")
    _db_path = os.path.expanduser("~/.openclaw/workspace/chroma_db")
    if not os.path.exists(_db_path):
        _db_path = "./chroma_db"

    if backend == "qdrant":
        _new_store = VectorStoreManager(backend="qdrant")
    else:
        _new_store = VectorStoreManager(backend="chroma", db_path=_db_path)

    count = _new_store.count()
    if count == 0:
        logger.info(f"[init_vector_store] Collection empty — loading all domains...")
        _new_store.load_all_domains()
    else:
        logger.info(f"[init_vector_store] {_new_store.backend_name}: {count} schema vectors loaded. Skipping.")

    # Resolve the lazy singleton and cache the real instance
    # so that `from app.core.vector_store import store_manager` also sees it
    import app.core.vector_store as _vs_mod
    _vs_mod.store_manager._real = _new_store
    _vs_mod.store_manager._backend_override = backend
    return _new_store


# Alias for old name
QdrantVectorStoreManager = VectorStoreManager


if __name__ == "__main__":
    # Quick smoke test
    store = init_vector_store()
    print(f"Backend: {store.backend_name}")
    print(f"Schema count: {store.count()}")
    print("\nTest search (vendor):")
    results = store.search_schema("find vendors by city and payment terms", n_results=3)
    for r in results:
        print(f"  table={r['metadata'].get('table')} score=ok")
