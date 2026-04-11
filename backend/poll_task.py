import requests, time, sys

task_id = 'b450ace6-bd38-4f4a-a9cf-bf2cecd1c93f'
for i in range(1, 10):
    time.sleep(2)
    try:
        r = requests.get(
            f"http://localhost:8000/api/v1/chat/tasks/{task_id}",
            params={"timeout": 1.0},
            timeout=5
        )
        d = r.json()
        print(f"Poll {i}: status={d.get('status')} ready={d.get('ready')}")
        if d.get("ready"):
            result = d.get("result", {})
            print(f"RESULT keys: {sorted(result.keys())}")
            print(f"confidence_score: {result.get('confidence_score') is not None}")
            print(f"routing_path: {result.get('routing_path')}")
            print(f"tool_trace len: {len(result.get('tool_trace', []))}")
            break
    except Exception as e:
        print(f"Error: {e}")
        if i > 3:
            break
