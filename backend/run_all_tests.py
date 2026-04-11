import sys
import os
os.chdir(r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend")
sys.path.insert(0, r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend")

print(f"Python: {sys.version}")

# Test imports
print("\n--- Testing Imports ---")
try:
    from app.core.security import security_mesh
    print("security: OK")
except Exception as e:
    print(f"security: FAILED - {e}")

try:
    from app.core.graph_store import graph_store
    print(f"graph: {graph_store.G.number_of_nodes()} nodes, {graph_store.G.number_of_edges()} edges")
except Exception as e:
    print(f"graph: FAILED - {e}")

try:
    from app.agents.orchestrator import run_agent_loop
    print("orchestrator: OK")
except Exception as e:
    print(f"orchestrator: FAILED - {e}")

# Test FastAPI app
print("\n--- Testing FastAPI App ---")
try:
    from app.main import app
    print(f"FastAPI app loaded: {app.title}")
except Exception as e:
    print(f"FastAPI app: FAILED - {e}")

# Test domain tables
print("\n--- Testing Domain Tables ---")
try:
    from app.domain import BUSINESS_PARTNER_TABLES
    print(f"BP tables: {list(BUSINESS_PARTNER_TABLES.keys())}")
except Exception as e:
    print(f"BP tables: FAILED - {e}")

# Run seed_all stats
print("\n--- Running seed_all.py --stats ---")
import subprocess
result = subprocess.run(
    [r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\.venv\Scripts\python.exe",
     r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\seed_all.py", "--stats"],
    capture_output=True, text=True, cwd=r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend"
)
print(f"seed_all stdout:\n{result.stdout}")
if result.stderr:
    print(f"seed_all stderr:\n{result.stderr}")
print(f"seed_all return code: {result.returncode}")

print("\nDone.")
