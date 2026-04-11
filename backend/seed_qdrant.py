"""
seed_qdrant.py — Seed Qdrant with Schema RAG and SQL Pattern RAG
Uses system Python (torch works there, not in backend .venv).
"""
import sys, os, uuid, logging, time

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger()

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)

QDRANT_HOST = os.environ.get("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.environ.get("QDRANT_PORT", "6333"))
SCHEMA_COLLECTION = "sap_schema"
SQL_COLLECTION = "sql_patterns"
EMBEDDING_DIM = 384
MODEL = "all-MiniLM-L6-v2"

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, OptimizersConfigDiff

client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT, timeout=60, prefer_grpc=False)
logger.info(f"Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")

# Load encoder via system Python (torch works there)
from sentence_transformers import SentenceTransformer
encoder = SentenceTransformer(MODEL)
logger.info(f"Encoder: {MODEL}")

def encode(texts):
    return encoder.encode(texts, convert_to_numpy=True).tolist()

def str_uuid(s):
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, s))

domain_modules = [
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

schema_points = []
pattern_points = []

for mn in domain_modules:
    mod = __import__(f"app.domain.{mn}", fromlist=["X"])
    all_attrs = [x for x in dir(mod) if not x.startswith("_")]
    tv = next((x for x in all_attrs if x.endswith("_TABLES")), None)
    pv = next((x for x in all_attrs if x.endswith("_SQL_PATTERNS")), None)
    tables = getattr(mod, tv, {}) if tv else {}
    patterns = getattr(mod, pv, []) if pv else []
    domain_name = mn.replace("_schema", "").replace("_", " ")

    for tname, tdef in tables.items():
        cols = tdef.get("columns", [])
        if len(cols) < 2:
            continue
        col_desc = ", ".join(
            f"{c['name']} ({c.get('type', '')}) : {c.get('desc', '')}" for c in cols
        )
        doc = f"Table {tname} - {tdef.get('description', '')}. Columns: {col_desc}"
        vec = encode([doc])[0]
        schema_points.append(
            PointStruct(
                id=str_uuid(f"schema_{domain_name}_{tname}"),
                vector=vec,
                payload={
                    "document": doc,
                    "table": tname,
                    "module": tdef.get("module", ""),
                    "domain": domain_name,
                },
            )
        )

    for pat in patterns:
        intent = pat.get("intent", "")
        if not intent:
            continue
        sql = pat.get("sql", "")
        vec = encode([intent])[0]
        pid = f"pattern_{domain_name}_{intent[:40]}"
        pattern_points.append(
            PointStruct(
                id=str_uuid(pid),
                vector=vec,
                payload={"intent": intent, "sql": sql, "domain": domain_name},
            )
        )

    real_tables = sum(1 for t in tables.values() if len(t.get("columns", [])) > 1)
    logger.info(f"  {mn}: {real_tables} tables, {len(patterns)} patterns")

logger.info(f"\nTotal: {len(schema_points)} schema vectors, {len(pattern_points)} patterns")

# Upsert schema
logger.info(f"\n[1/2] Seeding Schema RAG ({SCHEMA_COLLECTION})...")
for i in range(0, len(schema_points), 200):
    batch = schema_points[i : i + 200]
    client.upsert(collection_name=SCHEMA_COLLECTION, points=batch, wait=True)
    logger.info(f"  upserted {min(i + 200, len(schema_points))}/{len(schema_points)}")

# Upsert patterns
logger.info(f"\n[2/2] Seeding SQL Patterns ({SQL_COLLECTION})...")
for i in range(0, len(pattern_points), 200):
    batch = pattern_points[i : i + 200]
    client.upsert(collection_name=SQL_COLLECTION, points=batch, wait=True)
    logger.info(f"  upserted {min(i + 200, len(pattern_points))}/{len(pattern_points)}")

# Central SQL library
try:
    from app.core.sql_library import get_sql_library
    central = get_sql_library()
    central_pts = []
    for pat in central:
        domain_name2 = pat.get("module", "general").lower()
        intent_desc = pat.get("intent_description", "")
        nl_vars = pat.get("natural_language_variants", [])
        text = f"[{domain_name2}] {intent_desc} -- variants: {', '.join(nl_vars[:3])}"
        vec = encode([text])[0]
        qid = pat.get("query_id", "unknown")
        central_pts.append(
            PointStruct(
                id=str_uuid(f"central_{qid}"),
                vector=vec,
                payload={
                    "intent": intent_desc,
                    "sql": pat.get("sql_template", ""),
                    "domain": domain_name2,
                    "query_id": qid,
                    "tables_used": pat.get("tables_used", []),
                    "tags": pat.get("tags", []),
                },
            )
        )
    if central_pts:
        for i in range(0, len(central_pts), 200):
            client.upsert(collection_name=SQL_COLLECTION, points=central_pts[i : i + 200], wait=True)
        logger.info(f"  Central library: {len(central_pts)} patterns")
except Exception as e:
    logger.warning(f"  Central library skipped: {e}")

logger.info("\n" + "=" * 50)
logger.info("  VERIFICATION:")
for col in [SCHEMA_COLLECTION, SQL_COLLECTION]:
    try:
        info = client.get_collection(col)
        logger.info(f"  {col}: {info.points_count} points  [{info.vectors_count} vectors]")
    except Exception as e:
        logger.error(f"  {col}: ERROR -- {e}")
logger.info("=" * 50)
logger.info("  Qdrant seeding complete!")
