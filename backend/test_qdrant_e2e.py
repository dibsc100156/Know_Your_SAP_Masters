"""End-to-end test: hit the /api/v1/chat/master-data endpoint with Qdrant backend."""
import urllib.request, json, time

req = {
    "query": "vendor master for company code 1000",
    "role_id": "AP_CLERK"
}

url = "http://localhost:8000/api/v1/chat/master-data"
data = json.dumps(req).encode("utf-8")
headers = {
    "Content-Type": "application/json",
    "X-Session-ID": f"test-qdrant-{int(time.time())}"
}

httpreq = urllib.request.Request(url, data=data, headers=headers, method="POST")
with urllib.request.urlopen(httpreq, timeout=30) as resp:
    body = json.loads(resp.read().decode("utf-8"))
    # Pretty-print without the data rows (too long)
    top_level = {k: v for k, v in body.items() if k != "data"}
    print("Top-level fields:", json.dumps(top_level, indent=2))
    d = body.get("data", {})
    if isinstance(d, dict):
        print(f"\nTables used:    {d.get('tables_used', [])}")
        print(f"SQL generated:   {str(d.get('sql_generated',''))[:120]}")
        print(f"Pillars active:  {list(d.get('pillars',{}).keys())}")
        print(f"Confidence:      {d.get('confidence_score',{}).get('composite')}")
        print(f"Backend used:    {d.get('confidence_score',{}).get('backend', d.get('pillars',{}).get('schema_rag',{}).get('backend','?'))}")
    elif isinstance(d, list):
        print(f"\n[OK] Data rows returned: {len(d)} records (mock executor)")
        print(f"  Sample: {d[0] if d else 'empty'}")
