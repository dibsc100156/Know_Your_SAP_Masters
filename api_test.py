import requests, json, time

url = "http://127.0.0.1:8000/api/v1/chat/master-data"
payload = {
    "query": "vendor payment terms for company code 1000",
    "user_role": "AP_CLERK",
    "domain": "auto",
    "use_swarm": False
}

print("Sending request...", flush=True)
start = time.time()
try:
    r = requests.post(url, json=payload, timeout=60)
    elapsed = time.time() - start
    print(f"Status: {r.status_code} in {elapsed:.1f}s", flush=True)
    data = r.json()
    print(f"Tables: {data.get('tables_used', [])}", flush=True)
    print(f"Success!" if r.status_code == 200 else f"Error: {data}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}", flush=True)