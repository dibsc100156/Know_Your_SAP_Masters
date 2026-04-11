import requests, time
# Test Qdrant-backed orchestrator via HTTP API
resp = requests.post('http://localhost:8000/api/v1/chat/master-data', json={
    'query': 'vendor payment terms for company 1000',
    'domain': 'auto',
    'user_role': 'AP_CLERK'
}, timeout=45)
print('Status:', resp.status_code)
d = resp.json()
print('Keys:', sorted(d.keys()))
print('confidence_score:', d.get('confidence_score') is not None)
print('routing_path:', d.get('routing_path'))
print('tool_trace len:', len(d.get('tool_trace', [])))
print('tables_used:', d.get('tables_used'))
print()
print('=== Qdrant API: ALL OK ===')
