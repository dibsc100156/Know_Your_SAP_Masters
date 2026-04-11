"""Test Qdrant wiring via store_manager + orchestrator_tools."""
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
os.environ["VECTOR_STORE_BACKEND"] = "qdrant"

from app.core.vector_store import init_vector_store, store_manager

sm = init_vector_store()
print(f"Backend: {sm.backend_name}")
print(f"Schema count: {sm.count()}")
print()

# Test schema search
print("[1] Schema search: 'vendor payment terms'")
results = sm.search_schema("vendor payment terms", n_results=3)
print(f"  {len(results)} results")
for r in results:
    print(f"  table={r['metadata'].get('table')} module={r['metadata'].get('module')}")

print()

# Test pattern search
print("[2] Pattern search: 'open purchase orders by vendor'")
patterns = sm.search_sql_patterns("open purchase orders by vendor", n_results=2)
print(f"  {len(patterns)} results")
for p in patterns:
    print(f"  intent={p.get('intent','')[:70]}")

print()

# Test orchestrator_tools schema_lookup
print("[3] orchestrator_tools.schema_lookup()")
from app.agents.orchestrator_tools import schema_lookup, sql_pattern_lookup
from app.core.security import security_mesh

ctx = security_mesh.get_context("AP_CLERK")
r1 = schema_lookup("vendor master by city", auth_context=ctx, n_results=3)
print(f"  schema_lookup status: {r1.status}")
if r1.data:
    print(f"  tables: {[s['table'] for s in r1.data.get('schemas', [])]}")
    print(f"  backend reported: {r1.data.get('backend')}")

print()

r2 = sql_pattern_lookup("show me open purchase orders", auth_context=ctx, n_results=2)
print(f"  sql_pattern_lookup status: {r2.status}")
if r2.data:
    print(f"  patterns: {[p['intent'][:50] for p in r2.data.get('patterns', [])]}")
    print(f"  backend reported: {r2.data.get('backend')}")
