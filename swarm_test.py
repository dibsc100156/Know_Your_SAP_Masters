import sys
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')

import requests, time

url = 'http://127.0.0.1:8000/api/v1/chat/master-data'
payload = {
    "query": "quality inspection results for material M-100",
    "user_role": "AP_CLERK",
    "domain": "auto",
    "use_swarm": True
}

print("Sending swarm query...")
start = time.time()
try:
    r = requests.post(url, json=payload, timeout=120)
    elapsed = time.time() - start
    print(f"Status: {r.status_code} in {elapsed:.1f}s")
    if r.status_code == 200:
        data = r.json()
        print(f"Tables: {data.get('tables_used', [])}")
        print(f"Swarm routing: {data.get('routing_path', 'N/A')}")
        print(f"Agent count: {data.get('agent_count', 'N/A')}")
        print(f"Success!")
    else:
        print(f"Error: {r.text[:400]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
