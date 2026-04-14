$env:CELERY_BROKER_URL="amqp://sapmasters:sapmasters123@localhost:5672//"
$env:CELERY_RESULT_BACKEND="redis://localhost:6379/0"
$env:QDRANT_URL="http://localhost:6333"
$env:MEMGRAPH_URI="bolt://localhost:7687"
$env:VECTOR_STORE_BACKEND="qdrant"
$env:HANA_MODE="mock"
cd C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend
.\.venv\Scripts\celery.exe -A app.workers.celery_app worker --loglevel=info --concurrency=4 --pool=threads --queues=agent,priority
