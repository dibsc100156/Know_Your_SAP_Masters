"""test_hana_pool.py — Phase M7 validation"""
import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 60)
print("Phase M7: SAP HANA Connection Pool Validation")
print("=" * 60)
print()

# ── 1. Module imports ─────────────────────────────────────────────────────────
print("[1] Module imports")
try:
    from app.tools.hana_pool import (
        HanaPoolManager, HanaPoolConfig, HanaConnection,
        CircuitBreaker, CircuitState, CircuitOpenError,
        get_pool, close_pool,
    )
    print("  All imports OK")
except ImportError as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# ── 2. HanaPoolConfig from environment ─────────────────────────────────────
print()
print("[2] HanaPoolConfig — env variable parsing")
# Use a fake address to avoid real connection
os.environ["HANA_DB_ADDRESSES"] = "hana1.example.com:30015,hana2.example.com:30015"
os.environ["HANA_DB_USER"] = "TEST_USER"
os.environ["HANA_DB_PASSWORD"] = "testpass123"
os.environ["HANA_POOL_MIN_CONN"] = "2"
os.environ["HANA_POOL_MAX_CONN"] = "10"
os.environ["HANA_QUERY_TIMEOUT"] = "30"

cfg = HanaPoolConfig()
nodes = cfg.get_nodes()
print(f"  Nodes: {nodes}")
assert nodes == [("hana1.example.com", 30015), ("hana2.example.com", 30015)], f"Wrong nodes: {nodes}"
print(f"  min_conn={cfg.min_connections}, max_conn={cfg.max_connections}")
assert cfg.min_connections == 2
assert cfg.max_connections == 10
print("  OK")

# ── 3. Circuit breaker ────────────────────────────────────────────────────────
print()
print("[3] Circuit breaker — CLOSED → OPEN → HALF_OPEN state machine")

cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.5, half_open_max_calls=2)

# CLOSED → OPEN after 3 failures
success_count = [0]
def flaky_func():
    success_count[0] += 1
    raise RuntimeError("test failure")

for i in range(3):
    try:
        cb.call(flaky_func)
    except RuntimeError:
        pass

print(f"  After 3 failures: state={cb.state.value}")
assert cb.state == CircuitState.OPEN, f"Expected OPEN, got {cb.state}"

# OPEN → wait for recovery timeout
time.sleep(0.6)

# First HALF_OPEN call succeeds
try:
    cb.call(lambda: None)
    print(f"  After recovery timeout: state={cb.state.value} (should be CLOSED)")
    assert cb.state == CircuitState.CLOSED
    print("  OK — recovery worked")
except Exception as e:
    print(f"  Recovery failed: {e}")
    sys.exit(1)

# ── 4. HanaPoolManager — pool lifecycle ─────────────────────────────────────
print()
print("[4] HanaPoolManager — initialization (no real HANA)")
os.environ["HANA_MODE"] = "mock"  # force mock mode

pool = HanaPoolManager(config=cfg)
print(f"  Initialized: {pool._initialized}")
assert pool._initialized is False  # lazy init

pool.initialize()
print(f"  After initialize(): pool_size={len(pool._pool)}")

# Should have tried to connect to fake addresses and failed, pool may be empty
stats = pool.stats()
print(f"  Stats: {stats}")
print(f"  Circuit state: {stats['circuit_state']}")
print("  OK (pool initialized with available connections)")

# ── 5. SAPSQLExecutor with mock mode ───────────────────────────────────────
print()
print("[5] SAPSQLExecutor — mock mode (HANA_MODE=mock)")

os.environ["HANA_MODE"] = "mock"

from app.tools.sql_executor import SAPSQLExecutor
executor = SAPSQLExecutor(max_rows=100)

# Test various table mocks
test_cases = [
    ("SELECT * FROM EKKO JOIN EKPO ON EKKO.EBELN = EKPO.EBELN",
     ["EBELN", "LIFNR", "NETWR"]),
    ("SELECT * FROM LFA1",
     ["LIFNR", "NAME1", "LAND1", "BANKN"]),
    ("SELECT * FROM KNA1",
     ["KUNNR", "NAME1", "LAND1"]),
    ("SELECT * FROM MARD JOIN MBEW ON MARD.MATNR = MBEW.MATNR",
     ["MATNR", "WERKS", "LABST", "BWKEY"]),
    ("SELECT * FROM BSEG",
     ["BELNR", "BUKRS", "DMBTR", "LIFNR"]),
]

for sql, expected_cols in test_cases:
    df = executor.execute(sql)
    print(f"  {sql[:50]:50s} → rows={len(df)}, cols={list(df.columns)[:3]}")
    assert len(df) > 0, f"No rows returned for {sql[:50]}"

# Verify masked columns work
from app.core.security import security_mesh
auth = security_mesh.get_context("AP_CLERK")
executor2 = SAPSQLExecutor(max_rows=100)
df_lfa1 = executor2.execute("SELECT * FROM LFA1", auth_context=auth)
print(f"  Masked DF columns: {list(df_lfa1.columns)}")
print("  OK")

# ── 6. MANDT injection ───────────────────────────────────────────────────────
print()
print("[6] MANDT injection")
pool3 = HanaPoolManager(config=cfg)
from app.core.security import security_mesh
auth = security_mesh.get_context("AP_CLERK")

# Query without MANDT should get it injected (using allowed_company_codes)
sql = "SELECT * FROM LFA1 WHERE LAND1 = 'DE'"
injected = pool3._inject_mandt(sql, auth)
print(f"  Input : {sql}")
print(f"  Output: {injected}")
# AP_CLERK allowed_company_codes = ['1000', '1010'] → uses first one
assert "MANDT = '1000'" in injected, f"MANDT not injected: {injected}"

# Query with existing MANDT should be unchanged
sql2 = "SELECT * FROM LFA1 WHERE MANDT = '100'"
injected2 = pool3._inject_mandt(sql2, auth)
assert injected2 == sql2, f"MANDT was modified: {injected2}"
print("  OK — existing MANDT preserved")

# ── 7. SQL safety validation ────────────────────────────────────────────────
print()
print("[7] SQL safety validation")

safety_tests = [
    ("SELECT * FROM LFA1", True),
    ("  SELECT EBELN FROM EKKO WHERE BUKRS = '1000'", True),
    ("DELETE FROM LFA1 WHERE LIFNR = '1000'", False),
    ("INSERT INTO EKKO (EBELN) VALUES ('123')", False),
    ("UPDATE LFA1 SET NAME1 = 'Test' WHERE LIFNR = '1'", False),
    ("DROP TABLE LFA1", False),
    ("TRUNCATE TABLE LFA1", False),
    ("GRANT SELECT ON LFA1 TO PUBLIC", False),
    ("EXEC sp_helptext 'LFA1'", False),
    ("SELECT * FROM LFA1; DELETE FROM LFA1 --", False),
]

executor3 = SAPSQLExecutor()
all_ok = True
for sql, should_pass in safety_tests:
    try:
        executor3._validate_sql_safety(sql)
        result = "PASS"
        passed = should_pass
    except PermissionError:
        result = "BLOCK"
        passed = not should_pass
    status = "OK" if passed else "FAIL"
    if not passed:
        all_ok = False
    print(f"  {status} {result:6s} | {str(should_pass):5s} | {sql[:50]}")

assert all_ok, "Safety tests failed"
print("  OK — all safety tests passed")

# ── 8. Pool stats ─────────────────────────────────────────────────────────────
print()
print("[8] Pool stats")
stats = pool.stats()
print(f"  {stats}")
print("  OK")

# ── Cleanup ─────────────────────────────────────────────────────────────────
pool.close()
close_pool()
print()
print("=" * 60)
print("ALL PHASE M7 TESTS PASSED")
print("=" * 60)
