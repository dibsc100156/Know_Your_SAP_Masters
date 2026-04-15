import requests, json

url = 'http://127.0.0.1:8000/api/v1/chat/master-data'

queries = [
    {'query': 'show me vendor 1010 bank details', 'user_role': 'AP_CLERK', 'domain': 'auto', 'use_swarm': False},
    {'query': 'open POs for vendor 1010 above 50000', 'user_role': 'AP_CLERK', 'domain': 'auto', 'use_swarm': False},
    {'query': 'material stock quantities for plant 1000', 'user_role': 'MM_CLERK', 'domain': 'auto', 'use_swarm': False},
    {'query': 'customer credit limit for customer 1000', 'user_role': 'SD_CLERK', 'domain': 'auto', 'use_swarm': False},
    {'query': 'quality inspection results for material M-100', 'user_role': 'QM_CLERK', 'domain': 'auto', 'use_swarm': False},
]

for q in queries:
    r = requests.post(url, json=q, timeout=60)
    data = r.json()
    print(f'Query: {q["query"]}')
    print(f'  Status: {r.status_code} | Tables: {data.get("tables_used", [])} | Time: {data.get("execution_time_ms", 0)}ms')
    print()