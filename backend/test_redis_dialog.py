"""test_redis_dialog.py — Phase M5 validation script"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.core.redis_dialog_manager import RedisDialogManager
from app.core.dialog_manager import ClarificationType, Clarification

REDIS_URL = "redis://127.0.0.1:6379/0"

def test_session_lifecycle():
    dm = RedisDialogManager(redis_url=REDIS_URL)
    print(f"Stats: {dm.stats()}")

    # Start session
    state = dm.start_session(user_id="sanjeev", role="AP_CLERK")
    print(f"Session started: {state.session_id}")
    assert state.role == "AP_CLERK"

    # Resume session
    resumed = dm.resume_session(state.session_id)
    print(f"Session resumed: {resumed.session_id}")
    assert resumed.session_id == state.session_id

    # Update context
    dm.update_context(state.session_id, {"vendor_scope": "all", "time_range": "FY2024"})
    ctx = dm.get_context(state.session_id)
    print(f"Context: {ctx}")
    assert ctx.get("vendor_scope") == "all"

    # Rate limiting
    allowed, info = dm.check_rate_limit("sanjeev")
    print(f"Rate limit: allowed={allowed}, remaining={info['remaining']}, reset_in={info['reset_in']}")
    assert allowed is True

    # End session
    dm.end_session(state.session_id)
    print("Session ended OK")
    print()

def test_preferences():
    dm = RedisDialogManager(redis_url=REDIS_URL)

    dm.set_preference("AP_CLERK", output_format="json", max_rows=50, include_sql=True)
    prefs = dm.get_preference("AP_CLERK")
    print(f"AP_CLERK prefs: {prefs}")
    assert prefs["output_format"] == "json"
    assert prefs["max_rows"] == 50
    print()

def test_task_metadata():
    dm = RedisDialogManager(redis_url=REDIS_URL)

    task_id = "test-task-001"
    dm.set_task_meta(task_id, query="vendor payment terms", user_id="sanjeev", role="AP_CLERK")
    print(f"Task meta set: {dm.get_task_meta(task_id)}")

    dm.update_task_status(task_id, "SUCCESS", {
        "answer": "Found 42 vendors",
        "tables_used": ["LFA1", "LFB1"],
        "execution_time_ms": 320,
    })
    meta = dm.get_task_meta(task_id)
    print(f"Task status updated: {meta}")
    assert meta["status"] == "SUCCESS"
    print()

def test_rate_limit_enforcement():
    dm = RedisDialogManager(redis_url=REDIS_URL)
    dm.RATE_LIMIT_MAX = 3  # low limit for test
    dm.RATE_LIMIT_TTL = 5  # short window

    user = "test_user_rate"
    results = []
    for i in range(5):
        allowed, info = dm.check_rate_limit(user)
        results.append((allowed, info["remaining"]))
        print(f"  Request {i+1}: allowed={allowed}, remaining={info['remaining']}")

    print(f"Rate limit test: {results}")
    # First 3 should be allowed, next 2 should be denied
    assert results[0][0] is True
    assert results[1][0] is True
    assert results[2][0] is True
    assert results[3][0] is False  # limit hit
    print()

def test_fallback_on_connection_error():
    # Create a new DM instance pointing to a non-existent Redis
    # The singleton should NOT be reused; use __new__ to bypass
    import app.core.redis_dialog_manager as rdm_mod
    # Clear the singleton first
    if hasattr(rdm_mod.get_dialog_manager, '_instance'):
        delattr(rdm_mod.get_dialog_manager, '_instance')

    dm = RedisDialogManager(redis_url="redis://127.0.0.1:9999")  # wrong port
    state = dm.start_session(user_id="test", role="AP_CLERK")
    # Should fall back to file-based
    print(f"Fallback mode: session_id={state.session_id}, role={state.role}")
    print()

if __name__ == "__main__":
    import time
    print("=" * 60)
    print("Phase M5: Redis Dialog Manager Tests")
    print("=" * 60)
    print()

    print("[1] Session lifecycle")
    test_session_lifecycle()

    print("[2] User preferences")
    test_preferences()

    print("[3] Celery task metadata")
    test_task_metadata()

    print("[4] Rate limit enforcement")
    test_rate_limit_enforcement()

    print("[5] Fallback on connection error")
    test_fallback_on_connection_error()

    # Cleanup
    dm = RedisDialogManager(redis_url=REDIS_URL)
    dm._r.flushdb()
    print("[CLEANUP] Redis flushed")

    print()
    print("=" * 60)
    print("ALL PHASE M5 TESTS PASSED")
    print("=" * 60)
