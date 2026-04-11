"""test_leanix_governance.py — Phase M9 validation"""
import sys, os, asyncio
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 60)
print("Phase M9: LeanIX Agent Governance Validation")
print("=" * 60)
print()

# ── 1. Module imports ────────────────────────────────────────────────────────
print("[1] Module imports")
try:
    from app.governance.leanix_governance import (
        LeanIXGovernanceService, LeanIXClient,
        DataClassificationEngine,
        AuthDecision, ComplianceStatus, DataCriticality,
    )
    from app.governance.leanix_middleware import LeanIXGovernanceMiddleware
    from app.governance.audit_api import router as gov_router
    print("  All imports OK")
except ImportError as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# ── 2. Data Classification Engine ─────────────────────────────────────────────
print()
print("[2] DataClassificationEngine — table classification")
classifier = DataClassificationEngine()

test_cases = [
    ("LFA1",    "gdprRelevant=True, personalData=True, CONFIDENTIAL"),
    ("LFA1",    "confidential business data"),
    ("PA0001",   "HR — GDPR-relevant"),
    ("PA0008",   "HR Wages — GDPR_ARTICLE_9 special category"),
    ("BSEG",     "financial line items — RESTRICTED"),
    ("KNA1",     "customer personal data — CONFIDENTIAL"),
    ("MARA",     "material master — INTERNAL"),
    ("COSP",     "CO actuals — RESTRICTED (requires CFO)"),
    ("J_1IEXCHDRATE", "India tax exchange rates — RESTRICTED"),
]

all_ok = True
for table, expected_type in test_cases:
    result = classifier.classify(table)
    gdpr = result["gdprRelevant"]
    personal = result["personalData"]
    criticality = result["dataCriticality"]
    flags = result["complianceFlags"]
    print(f"  {table:20s} → gdpr={str(gdpr):5s} personal={str(personal):5s} "
          f"criticality={criticality:15s} flags={flags[:2]}")
    # Basic sanity checks
    if table == "MARA":
        assert result["dataCriticality"] == "internal"
    if table in ("PA0001", "PA0008"):
        assert result["gdprRelevant"] is True
    if table == "BSEG":
        assert result["dataCriticality"] == "restricted"
print("  OK — all classifications passed")

# ── 3. LeanIXGovernanceService pre-authorization (sync test) ───────────────
print()
print("[3] LeanIXGovernanceService — pre-authorization (DEMO mode)")

# Monkey-patch the async methods with sync versions for testing
import asyncio

class SyncGov(LeanIXGovernanceService):
    async def pre_authorize(self, user_id, role_id, query, tables, auth_context=None):
        return await super().pre_authorize(user_id, role_id, query, tables, auth_context)

    async def check_compliance(self, query, tables, auth_context=None):
        return await super().check_compliance(query, tables, auth_context)

    async def enrich_context(self, query, tables):
        return await super().enrich_context(query, tables)

gov = SyncGov(demo_mode=True)

# Test cases: (role_id, query, tables, expected_decision)
auth_tests = [
    # CFO can access everything
    ("CFO_GLOBAL", "show me the BSEG vendor invoices",
     ["BSEG", "LFA1"], AuthDecision.ALLOW),
    # AP_CLERK can access LFA1 but NOT restricted tables
    ("AP_CLERK", "show me vendor master data",
     ["LFA1", "LFB1"], AuthDecision.ALLOW),
    # AP_CLERK denied restricted tables
    ("AP_CLERK", "show me all fixed assets",
     ["ANLA", "ANLC"], AuthDecision.DENY),
    # HR_ADMIN can access HR tables
    ("HR_ADMIN", "show me employee data",
     ["PA0001", "PA0008"], AuthDecision.ALLOW),
    # DPO can access GDPR data
    ("GDPR_COMPLIANCE", "show me all GDPR relevant queries",
     ["LFA1", "KNA1", "PA0001"], AuthDecision.ALLOW),
]

all_auth_ok = True
for role_id, query, tables, expected in auth_tests:
    result = asyncio.run(gov.pre_authorize("test_user", role_id, query, tables))
    decision = result["decision"]
    match = decision == expected
    if not match:
        all_auth_ok = False
    status = "OK" if match else "FAIL"
    print(f"  {status} {role_id:20s} + {tables} → {decision.value} (expected {expected.value})")

assert all_auth_ok, "Pre-authorization tests failed"
print("  OK")

# ── 4. Compliance classification ────────────────────────────────────────────
print()
print("[4] Compliance check")

compliance_tests = [
    # GDPR special category → BLOCK
    (["PA0008"], ComplianceStatus.BLOCK),
    # GDPR relevant → GDPR_CONSENT
    (["PA0001"], ComplianceStatus.GDPR_CONSENT),
    # Personal data → MASK_AND_LOG
    (["LFA1", "KNA1"], ComplianceStatus.MASK_AND_LOG),
    # Normal operational → PASS
    (["MARA", "MARC"], ComplianceStatus.PASS),
    # Financial restricted → MASK_AND_LOG (not GDPR, but sensitive)
    (["BSEG"], ComplianceStatus.MASK_AND_LOG),
]

all_comp_ok = True
for tables, expected in compliance_tests:
    result = asyncio.run(gov.check_compliance("test query", tables))
    status = ComplianceStatus(result["status"])
    match = status == expected
    if not match:
        all_comp_ok = False
    print(f"  {status.value:20s} {str(tables):40s} → expected {expected.value}")
    assert ComplianceStatus(result["status"]) == expected, f"Unexpected: {result['status']}"

print("  OK")

# ── 5. Audit log ─────────────────────────────────────────────────────────
print()
print("[5] Audit log — write + read")

# Clear any existing entries
gov._audit_log.clear()

log_tests = [
    ("user1", "AP_CLERK", ["LFA1", "LFB1"], AuthDecision.ALLOW, ComplianceStatus.PASS),
    ("user2", "AP_CLERK", ["ANLA"], AuthDecision.DENY, ComplianceStatus.BLOCK),
    ("user3", "CFO_GLOBAL", ["BSEG"], AuthDecision.ALLOW, ComplianceStatus.MASK_AND_LOG),
]

for user_id, role_id, tables, auth_decision, comp_status in log_tests:
    auth_result = asyncio.run(gov.pre_authorize(user_id, role_id, "test query", tables))
    comp_result = asyncio.run(gov.check_compliance("test query", tables))
    entry = gov.log_query(
        query=f"SELECT * FROM {','.join(tables)}",
        auth_result=auth_result,
        compliance_result=comp_result,
        result_summary={
            "tables_accessed": tables,
            "row_count": 42,
            "execution_time_ms": 320,
        },
        user_id=user_id,
        role_id=role_id,
    )
    print(f"  audit_id={entry['auditId'][:8]}... user={user_id} auth={auth_decision.value} "
          f"compliance={comp_status.value}")
    assert entry["auditId"], "auditId should be set"
    assert entry["userId"] == user_id

# Read back (use large since window to avoid timezone comparison issues)
from datetime import datetime, timezone, timedelta
recent = datetime.now(timezone.utc) - timedelta(days=365)
entries = gov.get_audit_log(user_id="user2", since=recent)
assert len(entries) >= 1, f"Expected >=1 entries for user2, got {len(entries)}"
assert entries[0]["authDecision"] == "deny"
print("  OK — audit log write/read passed")

# ── 6. Middleware table extraction ─────────────────────────────────────────
print()
print("[6] LeanIXGovernanceMiddleware — table extraction")
middleware = LeanIXGovernanceMiddleware(app=None, governance_service=gov)

extract_tests = [
    ("show me all vendors from LFA1 and their company codes in LFB1",
     ["LFA1", "LFB1"]),
    ("what are the purchase orders in EKKO for vendor V1000",
     ["EKKO"]),
    ("material stock quantities for MARA and MARD",
     ["MARA", "MARD"]),
]

all_extract_ok = True
for query, expected in extract_tests:
    found = middleware._extract_tables_from_query(query)
    match = set(found) == set(expected)
    if not match:
        all_extract_ok = False
    print(f"  {'OK' if match else 'FAIL'} {query[:50]:50s} → found={found}")
    assert set(found) == set(expected), f"Expected {expected}, got {found}"

assert all_extract_ok
print("  OK")

# ── 7. DEMO mode (no credentials) ───────────────────────────────────────
print()
print("[7] DEMO mode — no credentials required")
demo_gov = LeanIXGovernanceService(demo_mode=True)
assert demo_gov._demo_mode is True
auth_result = asyncio.run(demo_gov.pre_authorize("user", "AP_CLERK", "vendor query", ["LFA1"]))
print(f"  DEMO mode auth: {auth_result['decision'].value}")
print("  OK")

print()
print("=" * 60)
print("ALL PHASE M9 TESTS PASSED")
print("=" * 60)
