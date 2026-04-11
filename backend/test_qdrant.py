import sys, os
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')
os.environ['VECTOR_STORE_BACKEND'] = 'qdrant'
os.environ['QDRANT_HOST'] = 'localhost'
os.environ['QDRANT_PORT'] = '6333'
from app.core.vector_store import VectorStoreManager
store = VectorStoreManager(backend='qdrant')

print('=== Schema Search ===')
results = store.search_schema('vendor payment terms company code', n_results=3)
for r in results:
    print('  table=' + r['metadata'].get('table', ''))

print()
print('=== SQL Pattern Search ===')
patterns = store.search_sql_patterns('find open purchase orders for vendor', n_results=2)
for p in patterns:
    print('  intent=' + p['intent'][:60])

print()
print('=== Qdrant search: ALL OK ===')
