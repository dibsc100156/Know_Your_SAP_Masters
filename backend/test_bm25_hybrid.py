"""test_bm25_hybrid.py — Verify BM25 Hybrid Search"""
import sys, time
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')

from app.core.bm25_hybrid import is_keyword_heavy_query, BM25HybridSearch
from app.core.vector_store import VectorStoreManager

# Test 1: keyword detector
tests = [
    ("LFA1 vendor for company 1000", True),
    ("vendor payment terms", True),
    ("company code 1000", True),
    ("EKKO open POs above 50000", True),
    ("T001 configuration", True),
    ("MARA material description", True),
    ("what is the vendor name", False),
    ("how many open POs above 50k for EU plant", False),
    ("analyze vendor performance with quality", False),
    ("tell me about material stock levels", False),
    ("LFA1 LFB1 KNA1 relationship", True),
]

all_ok = True
for query, expected in tests:
    got = is_keyword_heavy_query(query)
    ok = got == expected
    if not ok: all_ok = False
    print("OK" if ok else "FAIL", repr(query[:40]), "exp=", expected, "got=", got)

print("\n" + ("ALL PASS" if all_ok else "SOME FAILURES"))

# Test 2: hybrid search (pass VSM as adapter so VSM fallback works)
print("\n--- BM25 Hybrid Search ---")
vsm = VectorStoreManager()
# Pass vsm as adapter=None so _vector_search uses vsm.search_schema fallback
search = BM25HybridSearch(vsm, None)
t0 = time.time()
search._build_bm25_index()
print(f"index built in {round(time.time()-t0,1)}s: {search._indexed_count} docs")

if search._indexed_count > 0:
    for query, qtype in [
        ("LFA1 vendor", "keyword"),
        ("vendor payment terms", "keyword"),
        ("open purchase orders above 50000", "NL"),
        ("what are the vendor payment terms", "NL"),
    ]:
        results = search.search(query, domain=None, top_k=5)
        top = results[0] if results else {}
        print(f"\nquery: {query}")
        print(f"  keyword_heavy: {top.get('signals',{}).get('keyword_heavy')}")
        print(f"  fusion: {top.get('signals',{}).get('fusion_used')}")
        print(f"  top: {top.get('table','?')} score={top.get('fused_score',0):.4f}")
        print(f"  all tables: {[r.get('table') for r in results]}")
else:
    print("WARNING: 0 docs indexed — seed Qdrant first")
