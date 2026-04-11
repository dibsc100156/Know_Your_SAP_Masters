"""
seed_qdrant.py — Seed Qdrant with Schema RAG and SQL Pattern RAG
================================================================
Standalone: uses qdrant_client directly (no backend module imports).
System Python has working torch + sentence-transformers.
Qdrant collections use SAME names as QdrantAdapter:
  sap_schema      (384d, cosine)
  sql_patterns    (384d, cosine)

Usage:
    python seed_qdrant_standalone.py
"""
import os, sys, uuid, logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ── Resolve backend path for domain imports ──────────────────────────────────
BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)

QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
SCHEMA_COLLECTION = "sap_schema"
SQL_COLLECTION = "sql_patterns"
EMBEDDING_DIM = 384
ENCODER_MODEL = "all-MiniLM-L6-v2"

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, OptimizersConfigDiff

# ── Domain modules (verified present) ──────────────────────────────────────
DOMAIN_MODULES = [
    "business_partner_schema",
    "material_master_schema",
    "purchasing_schema",
    "sales_distribution_schema",
    "customer_service_schema",
    "warehouse_management_schema",
    "quality_management_schema",
    "project_system_schema",
    "transportation_schema",
    "variant_configuration_schema",
    "ehs_schema",
    "real_estate_schema",
    "gts_schema",
    "is_oil_schema",
    "is_retail_schema",
    "is_utilities_schema",
    "is_health_schema",
    "taxation_india_schema",
]


def str_to_uuid(s: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, s))


def load_domain(mod_name: str):
    """Import domain module, return (domain_name, tables_dict, patterns_list)."""
    mod = __import__(f"app.domain.{mod_name}", fromlist=["X"])
    all_attrs = {x for x in dir(mod) if not x.startswith("_")}
    tables_var = next((x for x in all_attrs if x.endswith("_TABLES")), None)
    patterns_var = next((x for x in all_attrs if x.endswith("_SQL_PATTERNS")), None)
    tables = getattr(mod, tables_var, {}) if tables_var else {}
    patterns = getattr(mod, patterns_var, []) if patterns_var else []
    domain_name = mod_name.replace("_schema", "").replace("_", " ")
    return domain_name, tables, patterns


def table_to_doc(table_name: str, table_def: dict) -> str:
    """Format table def into searchable document text (matches QdrantAdapter format)."""
    cols = table_def.get("columns", [])
    col_desc = ", ".join(
        f"{c['name']} ({c.get('type', '')}) : {c.get('desc', '')}"
        for c in cols
    )
    return (
        f"Table {table_name} - {table_def.get('description', '')}."
        f" Columns: {col_desc}"
    )


def pattern_to_doc(intent: str, sql: str) -> str:
    return f"{intent}"


# ── Encoder (system Python torch works) ─────────────────────────────────────
def get_encoder():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(ENCODER_MODEL)

encoder = None


def encode(texts: list) -> list:
    global encoder
    if encoder is None:
        encoder = get_encoder()
    return encoder.encode(texts, convert_to_numpy=True).tolist()


# ── Qdrant helpers ───────────────────────────────────────────────────────────
def ensure_collection(client, name: str):
    collections = {c.name for c in client.get_collections().collections}
    if name not in collections:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            optimizers_config=OptimizersConfigDiff(indexing_threshold=0),
        )
        logger.info(f"  Created: {name}")
    else:
        logger.info(f"  Exists:  {name}")


def seed_schema(client, encoder_fn):
    """Seed sap_schema collection with all domain tables."""
    ensure_collection(client, SCHEMA_COLLECTION)

    # Check if already populated
    info = client.get_collection(SCHEMA_COLLECTION)
    if info.points_count > 0:
        logger.info(f"  Already has {info.points_count} points — skipping schema seed.")
        return

    points = []
    for mod_name in DOMAIN_MODULES:
        domain_name, tables, _ = load_domain(mod_name)
        docs, vecs, payloads = [], [], []

        for table_name, table_def in tables.items():
            # Skip stubs (tables without columns)
            if len(table_def.get("columns", [])) < 2:
                continue
            doc = table_to_doc(table_name, table_def)
            docs.append(doc)
            payloads.append({
                "document": doc,
                "table": table_name,
                "module": table_def.get("module", ""),
                "domain": domain_name,
            })

        if not docs:
            logger.info(f"  {domain_name}: no table data — skipped")
            continue

        # Batch encode
        batch_vecs = encoder_fn(docs)
        for doc, vec, payload in zip(docs, batch_vecs, payloads):
            points.append(PointStruct(
                id=str_to_uuid(f"schema_{domain_name}_{payload['table']}"),
                vector=vec,
                payload=payload,
            ))

        logger.info(f"  {domain_name}: {len(docs)} tables")

    if points:
        for i in range(0, len(points), 200):
            client.upsert(collection_name=SCHEMA_COLLECTION, points=points[i:i+200], wait=True)
        logger.info(f"  Seeded {len(points)} schema vectors")


def seed_patterns(client, encoder_fn):
    """Seed sql_patterns collection with all domain SQL patterns."""
    ensure_collection(client, SQL_COLLECTION)

    info = client.get_collection(SQL_COLLECTION)
    if info.points_count > 0:
        logger.info(f"  Already has {info.points_count} points — skipping pattern seed.")
        return

    points = []

    # Domain patterns
    for mod_name in DOMAIN_MODULES:
        domain_name, _, patterns = load_domain(mod_name)
        for pat in patterns:
            intent = pat.get("intent", "")
            sql = pat.get("sql", "")
            if not intent:
                continue
            doc = pattern_to_doc(intent, sql)
            vec = encoder_fn([doc])[0]
            pid = f"pattern_{domain_name}_{intent[:40]}"
            points.append(PointStruct(
                id=str_to_uuid(pid),
                vector=vec,
                payload={
                    "intent": intent,
                    "sql": sql,
                    "domain": domain_name,
                },
            ))
        if patterns:
            logger.info(f"  {domain_name}: {len(patterns)} patterns")

    # Central SQL_RAG_LIBRARY patterns
    try:
        from app.core.sql_library import get_sql_library
        central = get_sql_library()
        for pat in central:
            domain_name = pat.get("module", "general").lower()
            intent_desc = pat.get("intent_description", "")
            nl_vars = pat.get("natural_language_variants", [])
            text = f"[{domain_name}] {intent_desc} — variants: {', '.join(nl_vars[:3])}"
            vec = encoder_fn([text])[0]
            qid = pat.get("query_id", "unknown")
            points.append(PointStruct(
                id=str_to_uuid(f"central_{qid}"),
                vector=vec,
                payload={
                    "intent": intent_desc,
                    "sql": pat.get("sql_template", ""),
                    "domain": domain_name,
                    "query_id": qid,
                    "tables_used": pat.get("tables_used", []),
                    "tags": pat.get("tags", []),
                },
            ))
        logger.info(f"  Central library: {len(central)} patterns")
    except Exception as e:
        logger.warning(f"  Central library skipped: {e}")

    if points:
        for i in range(0, len(points), 200):
            client.upsert(collection_name=SQL_COLLECTION, points=points[i:i+200], wait=True)
        logger.info(f"  Seeded {len(points)} SQL patterns total")


def main():
    print("=" * 60)
    print("  Qdrant Schema + SQL Pattern Seeder")
    print("=" * 60)
    print(f"\n  Target: {QDRANT_HOST}:{QDRANT_PORT}")
    print(f"  Collections: {SCHEMA_COLLECTION}, {SQL_COLLECTION}")
    print(f"  Encoder: {ENCODER_MODEL}")

    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=60, prefer_grpc=False)
    logger.info(f"\n  Connected to Qdrant")

    existing = {c.name for c in client.get_collections().collections}
    logger.info(f"  Existing collections: {list(existing)}")

    print(f"\n[1] Seeding Schema RAG...")
    seed_schema(client, encode)

    print(f"\n[2] Seeding SQL Patterns...")
    seed_patterns(client, encode)

    print(f"\n[3] Verification:")
    for col in [SCHEMA_COLLECTION, SQL_COLLECTION]:
        try:
            info = client.get_collection(col)
            print(f"    {col}: {info.points_count} points")
        except Exception as e:
            print(f"    {col}: ERROR — {e}")

    print("\n" + "=" * 60)
    print("  ✅ Qdrant seeding complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
