import sys
sys.path.insert(0, '.')
import time
from app.agents.orchestrator import run_agent_loop
from app.core.security import security_mesh

print("Starting direct orchestrator call...", flush=True)
start = time.time()

auth = security_mesh.get_context("AP_CLERK")
result = run_agent_loop(
    query="vendor payment terms for company code 1000",
    auth_context=auth,
    domain="auto",
    use_supervisor=False,
    use_swarm=False,
)

elapsed = time.time() - start
print(f"Done in {elapsed:.1f}s", flush=True)
print(f"Tables: {result.get('tables_used', [])}", flush=True)
print(f"Status: {result.get('status', 'N/A')}", flush=True)