import sys
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')

import socket
socket.setdefaulttimeout(5)

try:
    from app.workers.celery_app import celery_app_instance as celery_app
    print("Celery app loaded OK")
    print(f"Broker: {celery_app.conf.broker_url}")
    print(f"Backend: {celery_app.conf.result_backend}")
    inspect = celery_app.control.inspect()
    print("Calling inspect.stats()...")
    stats = inspect.stats()
    if stats:
        print(f"Workers: {len(stats)}")
        for w, s in stats.items():
            print(f"  {w}: {s.get('pool')} pool, max-concurrency={s.get('max-concurrency')}")
    else:
        print("No workers registered")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
