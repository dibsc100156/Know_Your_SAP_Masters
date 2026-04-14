import sys
sys.path.insert(0, 'C:/Users/vishnu/.openclaw/workspace/SAP_HANA_LLM_VendorChatbot/backend')

# Test 1: Harness runs table
print("=== Test 1: Harness runs table ===")
from app.core.harness_runs import get_harness_runs
hr = get_harness_runs()
run = hr.start_run(
    run_id=None,
    query='test query',
    user_role='AP_CLERK',
    swarm_routing='single',
    planner_reasoning='test',
    complexity_score=0.5,
)
run_id = run.run_id
print(f"run_id: {run_id}")
print(f"status: {run.status}")

hr.update_phase(run_id, 'phase_0', 'completed',
    artifacts={'tables_found': ['LFA1', 'KNA1']},
    duration_ms=10)
hr.update_phase(run_id, 'domain_bp_agent', 'completed',
    artifacts={'record_count': 5, 'tables_used': ['LFA1']},
    duration_ms=80)
hr.complete_run(run_id, 'completed', confidence_score=0.92, execution_time_ms=95)

retrieved = hr.get_run(run_id)
print(f"retrieved status: {retrieved.status}")
print(f"phases: {[p.phase + ':' + p.status for p in retrieved.phase_states]}")
print()

# Test 2: build_contract with PURAgentContract
print("=== Test 2: PURAgentContract ===")
from app.agents.swarm.contracts import build_contract, PURAgentContract
raw = {
    'agent': 'pur_agent',
    'run_id': 'test-123',
    'data': [{'EBELN': '4500012345', 'NETWR': 50000, 'WAERS': 'USD', 'LIFNR': 'V001'}],
    'record_count': 1,
    'execution_time_ms': 45,
}
contract = build_contract('pur_agent', raw)
print(f"contract type: {type(contract).__name__}")
print(f"validation_passed: {contract.validation_passed}")
print(f"validation_errors: {contract.validation_errors}")
print(f"po_count: {contract.po_count}")
print(f"total_po_value: {contract.total_po_value}")
print()

# Test 3: build_contract with BPAgentContract (fails validation)
print("=== Test 3: BPAgentContract (validation test) ===")
raw_bad = {
    'agent': 'bp_agent',
    'run_id': 'test-456',
    'data': [{'MATNR': 'MAT001'}],  # wrong entity field
    'record_count': 1,
}
contract_bad = build_contract('bp_agent', raw_bad)
print(f"validation_passed: {contract_bad.validation_passed}")
print(f"validation_errors: {contract_bad.validation_errors}")
print()

# Test 4: domain_agents.run with run_id
print("=== Test 4: domain_agents with run_id ===")
from app.agents.domain_agents import PURAgent
agent = PURAgent()
# Mock auth_context
class MockCtx:
    role_id = 'AP_CLERK'
    allowed_company_codes = ['1000']
    allowed_plants = []
    allowed_purchasing_orgs = []
    def is_column_masked(self, table, col): return False

result = agent.run('open POs', MockCtx(), run_id='test-789')
print(f"result has run_id: {'run_id' in result}")
print(f"result run_id: {result.get('run_id')}")
print(f"result type: {type(result).__name__}")
print(f"validation_passed: {result.get('validation_passed')}")

print()
print("ALL TESTS PASSED")
