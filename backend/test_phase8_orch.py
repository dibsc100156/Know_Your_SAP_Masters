"""Test Phase 8 wired into orchestrator — QM Semantic Search + Negotiation Briefing"""
import sys
sys.path.insert(0, '.')

from app.agents.orchestrator import run_agent_loop
from app.core.security import SAPAuthContext

auth = SAPAuthContext(
    role_id="CFO_GLOBAL",
    description="Global CFO for Phase 8 tests",
    allowed_company_codes=["*"],
    allowed_purchasing_orgs=["*"],
    allowed_plants=["*"],
    denied_tables=[],
    masked_fields={},
)

print("=" * 70)
print("TEST 1: QM Semantic Search query (should fire Step 1.75)")
print("=" * 70)
result1 = run_agent_loop(
    query="Show me all quality notifications for equipment B-2047 with bearing vibration issues",
    auth_context=auth,
    domain="quality_management",
    verbose=True,
    use_supervisor=False,  # test main orchestrator path
)
print(f"\nResult keys: {list(result1.keys())}")
print(f"QM semantic count: {result1.get('qm_semantic', {}).get('count', 'N/A')}")
qm_results = result1.get('qm_semantic', {}).get('results', [])
if qm_results:
    print(f"QM semantic top result: {qm_results[0].get('text', '')[:80]}...")
else:
    print("QM semantic: no results (index may need seeding)")
print(f"Execution time: {result1.get('execution_time_ms', 0)}ms")

print("\n" + "=" * 70)
print("TEST 2: Negotiation Briefing query (should fire Step 2d)")
print("=" * 70)
result2 = run_agent_loop(
    query="Generate a negotiation briefing for customer KUNNR-10000142 for contract renewal price increase",
    auth_context=auth,
    domain="sales",
    verbose=True,
    use_supervisor=False,  # test main orchestrator path
)
print(f"\nResult keys: {list(result2.keys())}")
brief = result2.get('negotiation_brief')
if brief:
    hdr = brief.get('header', {})
    km = brief.get('key_metrics', {})
    rec = brief.get('recommendation', {})
    print(f"Brief entity: {hdr.get('entity_name', 'N/A')} ({hdr.get('entity_type', 'N/A')})")
    print(f"CLV Tier: {km.get('clv_tier', 'N/A')} | PSI: {km.get('price_sensitivity_index', 'N/A')}")
    print(f"Churn Risk: {km.get('churn_risk', 'N/A')} | BATNA Strength: {km.get('batna_strength', 'N/A')}")
    print(f"Recommended increase: +{rec.get('target_increase_pct', 'N/A')}%")
    print(f"Top tactic: {brief.get('tactics', ['N/A'])[0][:80]}")
else:
    print("No negotiation brief returned")
print(f"Execution time: {result2.get('execution_time_ms', 0)}ms")

print("\n" + "=" * 70)
print("TEST 3: Regular query (should NOT fire Phase 8 steps)")
print("=" * 70)
result3 = run_agent_loop(
    query="Show me vendor master data for company code 1000",
    auth_context=auth,
    domain="business_partner",
    verbose=True,
    use_supervisor=False,  # test main orchestrator path
)
print(f"QM semantic skipped: {result3.get('qm_semantic', {}).get('count', 'N/A')}")
print(f"Negotiation brief: {result3.get('negotiation_brief', 'N/A')}")
print(f"Execution time: {result3.get('execution_time_ms', 0)}ms")

print("\n✅ Phase 8 orchestrator wiring tests complete")
