import sys
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')

import requests, json

url = 'http://127.0.0.1:8000/api/v1/chat/master-data'
payload = {
    "query": "quality inspection results for material M-100",
    "user_role": "AP_CLERK",
    "domain": "auto",
    "use_swarm": True
}

r = requests.post(url, json=payload, timeout=120)
print(f"Status: {r.status_code}")
data = r.json()
print(json.dumps({k: v for k, v in data.items() if k != 'data'}, indent=2, default=str))
print(f"Data records: {len(data.get('data', []))}")
