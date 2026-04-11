import sys, os
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')
os.environ['MEMGRAPH_URI'] = 'bolt://localhost:7687'
os.environ['REDIS_HOST'] = 'localhost'
os.environ['CELERY_BROKER_HOST'] = 'localhost'
os.environ['RABBITMQ_PASS'] = 'sapmasters123'
os.environ['LEANIX_ENABLED'] = 'true'
os.environ['VECTOR_STORE_BACKEND'] = 'qdrant'
os.environ['QDRANT_HOST'] = 'localhost'
os.environ['QDRANT_PORT'] = '6333'
import io, sys as _sys
old_stdout = _sys.stdout
_sys.stdout = io.StringIO()
from app.main import on_startup
on_startup()
output = _sys.stdout.getvalue()
_sys.stdout = old_stdout
for line in output.split('\n'):
    if line.strip():
        print(line)
print()
print('=== Full startup with Qdrant: OK ===')
