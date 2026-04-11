import sys
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')
sys.stdout.reconfigure(encoding='utf-8')

print('Testing use_memgraph with bolt://localhost:7687...')
from app.core.memgraph_adapter import use_memgraph, MemgraphGraphRAGManager

try:
    cls = use_memgraph(uri='bolt://localhost:7687')
    print('SUCCESS: graph_store class =', cls)
except Exception as e:
    print(f'FAILED: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()