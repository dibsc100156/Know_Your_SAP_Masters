"""
Phase 23: Safety Guardrails — Smoke Tests
==========================================
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.core.safety_guardrails import (
    SafetyGuardrailsLayer,
    GuardContext,
    GuardAction,
    ThreatSeverity,
    guard,
    get_guardrails,
    get_sentinel,
    SQLInjectionEngine,
    CrossModuleEscalationEngine,
    SchemaEnumerationEngine,
    DeniedTableProbeEngine,
    DataExfiltrationEngine,
    TemporalInferenceEngine,
    RoleImpersonationEngine,
    OutputPIILeakEngine,
    SessionProfile,
)

passed = 0
failed = 0

def test(name, cond, detail=""):
    global passed, failed
    if cond:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name} — {detail}")
        failed += 1

print("=== Phase 23: Safety Guardrails — Smoke Tests ===\n")

# ── Test 1: SafetyGuardrailsLayer instantiates ──────────────────────────────
print("Test 1: Layer instantiation")
layer = SafetyGuardrailsLayer(mode="ENFORCING")
test("layer created", layer is not None)
test("8 engines loaded", len(layer.engines) == 8)
test("default mode is ENFORCING", layer.mode == "ENFORCING")

# ── Test 2: GuardAction enum helpers ────────────────────────────────────────
print("\nTest 2: GuardAction enum")
test("ALLOW.is_allowed == True", GuardAction.ALLOW.is_allowed)
test("WARN.is_allowed == True", GuardAction.WARN.is_allowed)
test("BLOCK.is_allowed == False", not GuardAction.BLOCK.is_allowed)
test("BLOCK.is_blocked == True", GuardAction.BLOCK.is_blocked)
test("ALLOW.is_flagged == False", not GuardAction.ALLOW.is_flagged)
test("WARN.is_flagged == True", GuardAction.WARN.is_flagged)

# ── Test 3: GuardContext dataclass ─────────────────────────────────────────
print("\nTest 3: GuardContext")
ctx = GuardContext(
    query="show me vendors for company code 1000",
    role_id="AP_CLERK",
    session_id="test_session_001",
    tables_accessed=["LFA1", "LFB1"],
    domains_accessed=["vendor_master"],
    row_count=150,
)
test("query stored", ctx.query == "show me vendors for company code 1000")
test("role_id stored", ctx.role_id == "AP_CLERK")
test("tables_accessed has 2", len(ctx.tables_accessed) == 2)
test("temporal_mode default=none", ctx.temporal_mode == "none")

# ── Test 4: Safe query passes through ──────────────────────────────────────
print("\nTest 4: Safe query — ALLOW verdict")
verdict = layer.guard(
    query="show vendor LFA1 for company code 1000",
    role_id="AP_CLERK",
    session_id="safe_session_001",
    tables_accessed=["LFA1", "LFB1"],
    domains_accessed=["vendor_master"],
    row_count=10,
)
test("is_safe=True", verdict.is_safe)
test("action=ALLOW", verdict.action == GuardAction.ALLOW)
test("threat_type=None", verdict.threat_type is None)
test("confidence=0.0", verdict.confidence == 0.0)

# ── Test 5: SQL Injection — DROP TABLE detected ────────────────────────────
print("\nTest 5: SQL Injection (DROP TABLE) — BLOCK verdict")
verdict = layer.guard(
    query="show vendors; DROP TABLE LFA1; --",
    role_id="AP_CLERK",
    session_id="inject_session_001",
    tables_accessed=["LFA1"],
    row_count=0,
)
test("is_safe=False", not verdict.is_safe)
test("action=BLOCK", verdict.action == GuardAction.BLOCK)
test("threat_type=sql_injection_probe", verdict.threat_type == "sql_injection_probe")
test("severity=CRITICAL", verdict.severity == ThreatSeverity.CRITICAL)
test("confidence>=0.9", verdict.confidence >= 0.9)
test("has evidence", len(verdict.evidence) > 0)
test("has remediation", len(verdict.remediation) > 0)
test("engine=SQLInjection", verdict.engine_name == "SQLInjection")
test("has session flag SQL_INJECTION", "SQL_INJECTION" in verdict.session_flags)

# ── Test 6: OR 1=1 injection detected ──────────────────────────────────────
print("\nTest 6: OR 1=1 tautology injection")
verdict = layer.guard(
    query="show all records where 1=1 OR ''=''",
    role_id="MM_CLERK",
    session_id="inject_session_002",
    tables_accessed=["MARA"],
)
test("is_safe=False", not verdict.is_safe)
test("action=BLOCK", verdict.action == GuardAction.BLOCK)
test("threat_type=sql_injection_probe", verdict.threat_type == "sql_injection_probe")

# ── Test 7: Cross-Module Escalation — HR_ADMIN accessing FI tables ─────────
print("\nTest 7: Cross-Module Escalation (HR→FI)")
verdict = layer.guard(
    query="show vendor master for all company codes",
    role_id="HR_ADMIN",
    session_id="escalate_session_001",
    tables_accessed=["LFA1", "KNA1"],  # Vendor/customer tables — not in HR scope
    domains_accessed=["vendor_master", "customer_master"],
    row_count=500,
)
test("is_safe=False", not verdict.is_safe)
test("action=WARN or BLOCK", verdict.action in (GuardAction.WARN, GuardAction.BLOCK))
test("threat_type=cross_module_escalation", verdict.threat_type == "cross_module_escalation")
test("severity>=MEDIUM", verdict.severity.value >= ThreatSeverity.MEDIUM.value)
test("engine=CrossModuleEscalation", verdict.engine_name == "CrossModuleEscalation")

# ── Test 8: AP_CLERK normal tables — no escalation ─────────────────────────
print("\nTest 8: AP_CLERK within scope — ALLOW")
verdict = layer.guard(
    query="show open invoices for vendor",
    role_id="AP_CLERK",
    session_id="safe_ap_001",
    tables_accessed=["LFA1", "BSIK", "EKKO"],
    row_count=25,
)
test("is_safe=True", verdict.is_safe)
test("action=ALLOW", verdict.action == GuardAction.ALLOW)

# ── Test 9: PII Leak — MM_CLERK accessing LFA1 (vendor PII, in-scope but PII) ─
print("\nTest 9: PII Leak — MM_CLERK accessing LFA1 (vendor PII, in-scope)")
# MM_CLERK scope includes LFA1 via EINA/EINE → but LFA1 contains PII (names/addresses)
# LFA1 is in MM_CLERK scope (via EINA), so CrossModuleEscalation won't fire
# Instead use EINA which is explicitly in MM_CLERK scope but LFA1 (PII) is accessible via it
# Actually: MM_CLERK scope = MARA, EINA... LFA1 is NOT in MM_CLERK scope directly
# Let me use EKKO → not PII. For PII: LFA1 (vendor name/address) is PII but in MM scope via EINA?
# MM_CLERK scope = [MARA, MARC, MARD, MBEW, MSKA, MSLB, MKOL, EINA, EINE, EKKO, EKPO, EKET, QALS, QAMV]
# LFA1 is NOT in MM_CLERK scope. So CrossModule fires first.
# For PII test: Need a role WITHOUT cross_module_escalation hitting first.
# Use a role that has BOTH tables in scope but PII engine still fires.
# Actually let's just directly test OutputPIILeakEngine in isolation.
eng_pii = OutputPIILeakEngine()
ctx_pii = GuardContext(
    query="show address records",
    role_id="MM_CLERK",
    session_id="pii_test_s",
    tables_accessed=["ADRC"],  # ADRC contains address PII (not in MM_CLERK scope)
)
profile_pii = SessionProfile(session_id="pii_test_s", role_id="MM_CLERK")
v_pii = eng_pii.check(ctx_pii, profile_pii)
test("OutputPIILeak: threat detected", v_pii is not None and not v_pii.is_safe)
test("OutputPIILeak: threat_type=pii_leak_attempt", v_pii.threat_type == "pii_leak_attempt")
test("OutputPIILeak: severity=HIGH", v_pii.severity == ThreatSeverity.HIGH)

# ── Test 10: PII Leak — CFO_GLOBAL (PII authorized) ────────────────────────
print("\nTest 10: PII Leak — CFO_GLOBAL (PII authorized) — ALLOW")
eng_cfo = OutputPIILeakEngine()
ctx_cfo = GuardContext(
    query="show customer addresses for analysis",
    role_id="CFO_GLOBAL",
    session_id="pii_cfo_s",
    tables_accessed=["KNA1", "ADRC"],
)
profile_cfo = SessionProfile(session_id="pii_cfo_s", role_id="CFO_GLOBAL")
v_cfo = eng_cfo.check(ctx_cfo, profile_cfo)
test("CFO_GLOBAL PII: no threat (authorized)", v_cfo is None or v_cfo.is_safe)

# ── Test 11: Data Exfiltration — large row count ────────────────────────────
print("\nTest 11: Data Exfiltration — row count exceeds threshold")
verdict = layer.guard(
    query="show all BSEG records",
    role_id="AP_CLERK",
    session_id="exfil_session_001",
    tables_accessed=["BSEG"],
    row_count=20000,   # threshold for AP_CLERK is 5000
)
test("is_safe=False", not verdict.is_safe)
test("threat_type=data_exfiltration", verdict.threat_type == "data_exfiltration")
test("action=WARN or BLOCK", verdict.action in (GuardAction.WARN, GuardAction.BLOCK))

# ── Test 12: Denied Table Probe — session lock ─────────────────────────────
print("\nTest 12: Denied Table Probe → session lock")
eng_probe = DeniedTableProbeEngine()
ctx_probe = GuardContext(
    query="show PA0001 records",
    role_id="AP_CLERK",
    session_id="probe_lock_s",
    tables_accessed=["PA0001"],  # Denied for AP_CLERK
)
profile_probe = SessionProfile(session_id="probe_lock_s", role_id="AP_CLERK")
# Simulate 4 probes (threshold=2, lock at 4)
for i in range(4):
    eng_probe._probe_counts["probe_lock_s"] = i + 1
verdict = eng_probe.check(ctx_probe, profile_probe)
test("is_safe=False", not verdict.is_safe)
test("action=BLOCK after threshold", verdict.action == GuardAction.BLOCK)
test("session locked (tightens_auth)", verdict.tightens_auth)

# ── Test 13: DISABLED mode passes everything ────────────────────────────────
print("\nTest 13: DISABLED mode — all queries ALLOW")
disabled_layer = SafetyGuardrailsLayer(mode="DISABLED")
verdict = disabled_layer.guard(
    query="show all tables; DROP TABLE LFA1;",
    role_id="HR_ADMIN",
    session_id="disabled_session",
    tables_accessed=["BSEG", "COSP"],
    row_count=999999,
)
test("is_safe=True in DISABLED mode", verdict.is_safe)
test("action=ALLOW in DISABLED mode", verdict.action == GuardAction.ALLOW)

# ── Test 14: guard() convenience function ───────────────────────────────────
print("\nTest 14: guard() convenience function")
verdict = guard(
    query="list POs for vendor 1000",
    role_id="MM_CLERK",
    session_id="convenience_001",
    tables_accessed=["EKKO", "EKPO"],
)
test("guard() convenience works", verdict.is_safe)
test("guard() ALLOW for safe query", verdict.action == GuardAction.ALLOW)

# ── Test 15: guard() SQL injection via convenience ──────────────────────────
print("\nTest 15: guard() SQL injection — BLOCK")
verdict = guard(
    query="list records; DELETE FROM LFA1 WHERE 1=1; --",
    role_id="MM_CLERK",
    session_id="convenience_002",
    tables_accessed=["LFA1"],
)
test("guard() detects injection", not verdict.is_safe)
test("guard() returns BLOCK", verdict.action == GuardAction.BLOCK)

# ── Test 16: get_guardrails() singleton ─────────────────────────────────────
print("\nTest 16: Module singletons")
g1 = get_guardrails()
g2 = get_guardrails()
test("get_guardrails() returns same instance", g1 is g2)
s1 = get_sentinel()
s2 = get_sentinel()
test("get_sentinel() returns same instance", s1 is s2)

# ── Test 17: LegacySentinelAdapter.evaluate() backward compat ───────────────
print("\nTest 17: LegacySentinelAdapter — backward compat")
sentinel = get_sentinel()
class MockAuthContext:
    role_id = "AP_CLERK"
verdict = sentinel.evaluate(
    query="show vendor payment terms",
    auth_context=MockAuthContext(),
    session_id="legacy_test_001",
    tables_accessed=["LFA1", "LFB1"],
    domains_accessed=["vendor_master"],
    row_count=10,
)
test("evaluate() returns verdict-like object", hasattr(verdict, "threat_detected"))
test("evaluate() threat_detected=False for safe", not verdict.threat_detected)
test("evaluate() recommended_action=allow", verdict.recommended_action == "allow")

# ── Test 18: LegacySentinelAdapter — SQL injection ───────────────────────────
print("\nTest 18: LegacySentinelAdapter — SQL injection")
verdict = sentinel.evaluate(
    query="show records; DROP TABLE LFA1; --",
    auth_context=MockAuthContext(),
    session_id="legacy_inject_001",
    tables_accessed=["LFA1"],
    row_count=0,
)
test("evaluate() threat_detected=True", verdict.threat_detected)
test("evaluate() recommended_action=block", verdict.recommended_action == "block")

# ── Test 19: GuardVerdict.as_dict() ────────────────────────────────────────
print("\nTest 19: GuardVerdict serialization")
verdict = layer.guard(
    query="UNION SELECT * FROM BSEG --",
    role_id="AP_CLERK",
    session_id="union_session",
    tables_accessed=["BSEG"],
)
d = verdict.as_dict()
test("as_dict() returns dict", isinstance(d, dict))
test("as_dict() has is_safe", "is_safe" in d)
test("as_dict() has action", "action" in d)
test("as_dict() has threat_type", "threat_type" in d)
test("as_dict() has evidence (max 4)", len(d["evidence"]) <= 4)

# ── Test 20: ThreatSeverity ordering ──────────────────────────────────────
print("\nTest 20: ThreatSeverity ordering")
test("CRITICAL > HIGH", ThreatSeverity.CRITICAL.value > ThreatSeverity.HIGH.value)
test("HIGH > MEDIUM", ThreatSeverity.HIGH.value > ThreatSeverity.MEDIUM.value)
test("MEDIUM > LOW", ThreatSeverity.MEDIUM.value > ThreatSeverity.LOW.value)
test("LOW > INFO", ThreatSeverity.LOW.value > ThreatSeverity.INFO.value)

# ── Test 21: AUDIT mode never blocks ──────────────────────────────────────
print("\nTest 21: AUDIT mode — never blocks, only logs")
audit_layer = SafetyGuardrailsLayer(mode="AUDIT")
verdict = audit_layer.guard(
    query="UNION SELECT * FROM BSEG; DROP TABLE LFA1;",
    role_id="AP_CLERK",
    session_id="audit_session",
    tables_accessed=["BSEG"],
)
test("AUDIT: threat detected (logged)", not verdict.is_safe)
test("AUDIT: returns WARN not BLOCK", verdict.action == GuardAction.WARN)

# ── Test 22: Session profile management ─────────────────────────────────────
print("\nTest 22: Session management")
layer2 = SafetyGuardrailsLayer()
layer2.guard(
    query="test",
    role_id="AP_CLERK",
    session_id="session_to_reset",
    tables_accessed=["LFA1"],
)
profile = layer2.get_session_profile("session_to_reset")
test("profile created after guard()", profile is not None)
test("queries_logged incremented", profile.queries_logged == 1)
layer2.reset_session("session_to_reset")
profile_after = layer2.get_session_profile("session_to_reset")
test("profile removed after reset_session()", profile_after is None)

# ── Test 23: Schema enumeration engine ─────────────────────────────────────
print("\nTest 23: SchemaEnumerationEngine — bulk discovery")
eng_enum = SchemaEnumerationEngine()
ctx_enum = GuardContext(
    query="show me all tables in the system",
    role_id="MM_CLERK",
    session_id="enum_s",
    tables_accessed=["MARA", "MARC", "MARD", "MBEW", "MSKA", "LFA1", "EKKO"],
)
profile_enum = SessionProfile(session_id="enum_s", role_id="MM_CLERK")
v_enum = eng_enum.check(ctx_enum, profile_enum)
test("SchemaEnum: threat detected", v_enum is not None and not v_enum.is_safe)
test("SchemaEnum: action=WARN or BLOCK", v_enum.action in (GuardAction.WARN, GuardAction.BLOCK))

# ── Test 24: get_threat_stats() ──────────────────────────────────────────────
print("\nTest 24: Threat statistics")
stats = layer.get_threat_stats()
test("stats is dict", isinstance(stats, dict))
test("stats has mode", "mode" in stats)
test("stats has engine_count", stats["engine_count"] == 8)
test("stats has active_sessions", "active_sessions" in stats)

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print("=" * 60)
if failed == 0:
    print(f"ALL {passed} TESTS PASSED ✅")
else:
    print(f"FAILED: {failed}/{passed+failed} — see above")
    sys.exit(1)
