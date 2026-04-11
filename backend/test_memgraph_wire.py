import sys
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')
sys.stdout.reconfigure(encoding='utf-8')

print('=== Step 1: Load memgraph_adapter ===')
from app.core import memgraph_adapter as ma
print('module loaded ok')

print()
print('=== Step 2: Check use_memgraph ===')
from app.core.memgraph_adapter import use_memgraph
print('use_memgraph fn:', use_memgraph)

print()
print('=== Step 3: Verify Memgraph connection ===')
from gqlalchemy import Memgraph
mg = Memgraph(host='127.0.0.1', port=7687)
result = list(mg.execute_and_fetch('MATCH (t:SAPTable) RETURN count(t) as cnt'))
print('Memgraph SAPTable count:', result[0]['cnt'])

print()
print('=== Step 4: Call use_memgraph ===')
result_cls = use_memgraph(uri='bolt://127.0.0.1:7687')
print('use_memgraph returned:', result_cls)

print()
print('=== Step 5: Check graph_store ===')
from app.core import graph_store
print('graph_store class:', graph_store.__class__.__name__)
print('all_paths_explore:', hasattr(graph_store, 'all_paths_explore'))
print('stats:', graph_store.stats() if hasattr(graph_store, 'stats') else 'N/A')

print()
print('=== SUCCESS: Memgraph wired into graph_store ===')