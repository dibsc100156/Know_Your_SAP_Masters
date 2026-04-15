import sys
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')

from app.workers.celery_app import celery_app_instance as celery_app
inspect = celery_app.control.inspect()
active = inspect.active()
queues = inspect.active_queues()
print("=== Active tasks ===")
if active:
    for w, tasks in active.items():
        print(f"  Worker {w}:")
        for t in tasks:
            print(f"    {t}")
else:
    print("  None")
print()
print("=== Active queues ===")
if queues:
    for w, qs in queues.items():
        print(f"  Worker {w}: {[q['name'] for q in qs]}")
else:
    print("  None")

stats = inspect.stats()
print()
print("=== Worker stats ===")
if stats:
    for w, s in stats.items():
        print(f"  Worker {w}: pool={s.get('pool')}, max-concurrency={s.get('max-concurrency')}")
else:
    print("  No stats available — workers may not be running")
