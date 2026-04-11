import sys, asyncio
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')
from app.governance.leanix_governance import LeanIXGovernanceService, DataClassificationEngine

svc = LeanIXGovernanceService(demo_mode=True)
print("Demo mode:", svc._demo_mode)
print()

# Test classification
clf = DataClassificationEngine()
for t in ['BSEG', 'PA0002', 'MARA', 'KNA1', 'LFA1']:
    c = clf.classify(t)
    print(t, ": gdpr=", c["gdprRelevant"], " personal=", c["personalData"], " criticality=", c["dataCriticality"])

print()

# Test governance async
async def test():
    r = await svc.pre_authorize('user1', 'AP_CLERK', 'show vendor LFA1 details', ['LFA1', 'LFB1'])
    decision = r['decision'].value if hasattr(r['decision'], 'value') else r['decision']
    print("Auth decision:", decision)
    print("Flags:", r.get('flaggedConditions', []))
    c = await svc.check_compliance('show vendor LFA1', ['LFA1', 'LFB1'])
    print("Compliance:", c['status'])
    audit = svc.log_query(
        'show vendor LFA1', r, c,
        {'tables_accessed': ['LFA1', 'LFB1'], 'row_count': 5, 'execution_time_ms': 200},
        user_id='user1', role_id='AP_CLERK'
    )
    print("Audit ID:", audit['auditId'])
    print()
    print("=== LeanIX Governance: ALL OK ===")

asyncio.run(test())
