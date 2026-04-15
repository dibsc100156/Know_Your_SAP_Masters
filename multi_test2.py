import requests

url = 'http://127.0.0.1:8000/api/v1/chat/master-data'

queries = [
    {'query': 'show me vendor 1010 bank details', 'user_role': 'AP_CLERK', 'domain': 'auto', 'use_swarm': False},
    {'query': 'open POs for vendor 1010 above 50000', 'user_role': 'AP_CLERK', 'domain': 'auto', 'use_swarm': False},
    {'query': 'material stock quantities for plant 1000', 'user_role': 'MM_CLERK', 'domain': 'auto', 'use_swarm': False},
]

for q in queries:
    r = requests.post(url, json=q, timeout=60)
    print(f'Query: {q["query"]}')
    print(f'  Status: {r.status_code}')
    if r.status_code != 200:
        print(f'  Error: {r.text[:200]}')
    else:
        data = r.json()
        print(f'  Tables: {data.get("tables_used", [])} | Time: {data.get("execution_time_ms", 0)}ms')
    print()