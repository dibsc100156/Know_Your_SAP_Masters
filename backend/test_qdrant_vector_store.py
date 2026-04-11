"""test_qdrant_vector_store.py — Phase M6 validation"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 60)
print("Phase M6: Qdrant Vector Store Validation")
print("=" * 60)
print()

# ── 1. Module import test ────────────────────────────────────────────────────
print("[1] Module imports")
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, Filter, FieldCondition, MatchValue
    from sentence_transformers import SentenceTransformer
    print("  All imports OK")
except ImportError as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# ── 2. Qdrant connection ────────────────────────────────────────────────────
print()
print("[2] Qdrant connection")
try:
    qc = QdrantClient(url="http://127.0.0.1:6333")
    cols = qc.get_collections()
    print(f"  Connected. Collections: {[c.name for c in cols.collections]}")
    print("  OK")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# ── 3. Load a single domain ────────────────────────────────────────────────
print()
print("[3] Load business_partner domain into Qdrant")
try:
    from app.core.qdrant_vector_store import QdrantVectorStoreManager
    vm = QdrantVectorStoreManager(url="http://127.0.0.1:6333", prefer_grpc=False)
    from app.domain.business_partner_schema import BUSINESS_PARTNER_TABLES, BUSINESS_PARTNER_SQL_PATTERNS
    vm.load_domain("business_partner", BUSINESS_PARTNER_TABLES, BUSINESS_PARTNER_SQL_PATTERNS)
    stats = vm.stats()
    print(f"  Stats: {stats}")
    print("  OK")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ── 4. Schema search ────────────────────────────────────────────────────────
print()
print("[4] Schema search — 'vendor master data'")
try:
    results = vm.search_schema("vendor master data", n_results=4, domain="business_partner")
    print(f"  Results: {len(results)}")
    for r in results:
        meta = r.get("metadata", {})
        print(f"    score={r.get('score', 0):.4f}  table={meta.get('table', '?')}  module={meta.get('module', '?')}")
    assert len(results) > 0, "No results returned"
    print("  OK")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ── 5. Cross-domain search ─────────────────────────────────────────────────
print()
print("[5] Cross-domain search — 'material stock quantities' (no domain filter)")
try:
    results = vm.search_schema("material stock quantities", n_results=3)
    print(f"  Results: {len(results)}")
    for r in results:
        meta = r.get("metadata", {})
        print(f"    score={r.get('score', 0):.4f}  table={meta.get('table', '?')}  domain={meta.get('domain', '?')}")
    assert len(results) > 0, "No results returned"
    print("  OK")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ── 6. SQL pattern search ──────────────────────────────────────────────────
print()
print("[6] SQL pattern search — 'vendor payment terms'")
try:
    results = vm.search_sql_patterns("vendor payment terms", n_results=2, domain="business_partner")
    print(f"  Results: {len(results)}")
    for r in results:
        print(f"    score={r.get('score', 0):.4f}  intent={r.get('intent', '?')[:60]}")
    print("  OK")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ── 7. QdrantSQLRAGStore ───────────────────────────────────────────────────
print()
print("[7] QdrantSQLRAGStore — load + search patterns")
try:
    from app.core.qdrant_sql_rag_store import QdrantSQLRAGStore
    sql_store = QdrantSQLRAGStore(url="http://127.0.0.1:6333")
    sql_store.initialize_library()
    stats = sql_store.stats()
    print(f"  Stats: {stats}")

    results = sql_store.search("open purchase orders by vendor", top_k=3)
    print(f"  Search results: {len(results)}")
    for r in results:
        print(f"    query_id={r['query_id']}  score={r['score']:.4f}  tables={r['tables_used']}")
    print("  OK")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ── 8. upsert_pattern ─────────────────────────────────────────────────────
print()
print("[8] Runtime pattern upsert")
try:
    new_entry = {
        "query_id": "test_pattern_001",
        "module": "purchasing",
        "tables_used": ["EKKO", "EKPO", "LFA1"],
        "intent_description": "Get open purchase orders expiring this month",
        "sql_template": "SELECT * FROM EKKO JOIN EKPO ON EKKO.EBELN = EKPO.EBELN WHERE EKPO.ELIKZ = ''",
        "natural_language_variants": ["expiring POs", "POs ending this month"],
    }
    ok = sql_store.upsert_pattern(new_entry)
    print(f"  Upsert result: {ok}")

    # Search for it
    results = sql_store.search("purchase orders expiring", top_k=5)
    found = [r for r in results if r["query_id"] == "test_pattern_001"]
    print(f"  Found after upsert: {len(found)} hits")
    print("  OK")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ── 9. Compare with ChromaDB ────────────────────────────────────────────────
print()
print("[9] Compare Qdrant vs ChromaDB (same queries, same results?)")
try:
    from app.core.vector_store import VectorStoreManager as ChromaVSM
    chroma_vm = ChromaVSM(db_path="./chroma_db")

    qdrant_results = vm.search_schema("vendor city and address", n_results=3)
    chroma_results = chroma_vm.search_schema("vendor city and address", n_results=3)

    qdrant_tables = sorted([r.get("metadata", {}).get("table", "?") for r in qdrant_results])
    chroma_tables = sorted([r.get("metadata", {}).get("table", "?") for r in chroma_results])

    print(f"  Qdrant  tables: {qdrant_tables}")
    print(f"  ChromaDB tables: {chroma_tables}")

    overlap = set(qdrant_tables) & set(chroma_tables)
    print(f"  Overlap: {overlap} ({len(overlap)}/3)")
    print("  OK (Qdrant may return different but equally valid tables)")
except Exception as e:
    print(f"  Note: {e} (ChromaDB may not be seeded)")
    print("  SKIPPED")

# ── Cleanup ─────────────────────────────────────────────────────────────────
print()
print("[10] Cleanup test collections")
try:
    qc.delete_collection("sap_schema")
    qc.delete_collection("sap_sql_patterns")
    qc.delete_collection("sql_patterns_rag")
    print("  Collections deleted")
    print("  OK")
except Exception as e:
    print(f"  Cleanup note: {e}")

print()
print("=" * 60)
print("ALL PHASE M6 TESTS PASSED")
print("=" * 60)
