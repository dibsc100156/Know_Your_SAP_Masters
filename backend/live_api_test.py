"""
live_api_test.py — End-to-end search test against port 8001
"""
import requests, json, time

url = "http://localhost:8001/api/v1/chat/master-data"
headers = {
    "Content-Type": "application/json",
    "X-Session-ID": "test-sess-e2e-001",
    "X-Role-ID": "AP_CLERK",
}

queries = [
    "show me vendor payment terms for company code 1010",
    "material stock quantities for plant 1010",
    "open purchase orders above 50000",
    "quality inspection results for materials",
    "vendor master data with bank details",
]

print(f"Testing against {url}")
print("=" * 60)

for q in queries:
    payload = {
        "query": q,
        "role_id": "AP_CLERK",
        "tenant_id": "DEFAULT",
        "use_swarm": True,
    }
    t0 = time.time()
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        elapsed = (time.time() - t0) * 1000
        data = r.json()
        confidence = data.get("confidence_score", {})
        composite = confidence.get("composite") if isinstance(confidence, dict) else confidence
        tables = data.get("tables_used", [])
        sql = data.get("sql_generated", "")
        swarm_routing = data.get("swarm_routing", "N/A")
        planner = data.get("planner_reasoning", "")
        agent_count = data.get("agent_count", "N/A")
        exec_ms = data.get("execution_time_ms", 0)
        tool_trace = data.get("tool_trace") or []
        sentinel = data.get("sentinel")
        crit = data.get("critique") or {}

        print(f"\n  Query      : {q}")
        print(f"  Status     : {r.status_code} | {elapsed:.0f}ms | exec={exec_ms}ms")
        print(f"  Tables     : {tables[:6]}")
        print(f"  SQL        : {sql[:70]}..." if len(sql) > 70 else f"  SQL        : {sql}")
        print(f"  Confidence : {composite}")
        print(f"  Swarm      : {swarm_routing} | planner: {planner[:60]}..." if planner else f"  Swarm      : {swarm_routing}")
        if agent_count != "N/A":
            print(f"  Agents     : {agent_count}")
        print(f"  Critique   : score={crit.get('score','?')} passed={crit.get('passed','?')}")
        if sentinel:
            print(f"  Sentinel   : {sentinel.get('verdict','?')}")
        print(f"  Tool trace :", end="")
        for t in tool_trace:
            print(f" {t.get('tool','?')}:{t.get('status','?')}", end="")
        print()
        if data.get("data"):
            print(f"  Rows       : {len(data['data'])} returned")
    except Exception as e:
        print(f"\n  Query  : {q}")
        print(f"  ERROR  : {e}")
    time.sleep(0.3)
