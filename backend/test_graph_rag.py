import os
import sys

# Ensure the backend directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.security import get_user_auth_context
from app.core.graph_store import SAPGraphStore
from app.tools.graph_retriever import RoleAwareGraphRetriever

def test_graph_extraction():
    print("\n--- Testing Graph RAG Subgraph Extraction ---")
    store = SAPGraphStore()
    
    seeds = ["EKKO", "LFA1"]
    
    # Simulate an auditor looking at the P2P cycle
    print(f"Extracting subgraph for seeds: {seeds}")
    subgraph = store.extract_subgraph(seeds, max_hops=2)
    
    print("Tables found in 2-hop radius:")
    for t in subgraph.get("tables", []):
        print(f"  - {t}")
        
    print("\nJoin Paths:")
    for j in subgraph.get("join_paths", []):
        print(f"  - {j}")
        
def test_role_aware_graph():
    print("\n--- Testing Role-Aware Graph Retrieval ---")
    
    # Procurement Manager: should see MM tables but NOT FI tables (BSIK, BKPF)
    procurement_auth = get_user_auth_context("PROCUREMENT_MGR")
    procurement_retriever = RoleAwareGraphRetriever(procurement_auth)
    
    # AP Clerk: should see FI tables but NOT MM tables (EKKO)
    ap_clerk_auth = get_user_auth_context("AP_CLERK")
    ap_clerk_retriever = RoleAwareGraphRetriever(ap_clerk_auth)
    
    # Auditor: sees everything
    auditor_auth = get_user_auth_context("AUDITOR")
    auditor_retriever = RoleAwareGraphRetriever(auditor_auth)

    seeds = ["LFA1"]
    
    print("\n1. PROCUREMENT MANAGER VIEW (Should prune BSIK/BKPF branches):")
    proc_context = procurement_retriever.retrieve(seeds)
    print(proc_context)
    
    print("\n2. AP CLERK VIEW (Should prune EKKO/EKPO branches):")
    ap_context = ap_clerk_retriever.retrieve(seeds)
    print(ap_context)
    
    print("\n3. AUDITOR VIEW (Full 2-hop P2P cycle):")
    auditor_context = auditor_retriever.retrieve(seeds)
    print(auditor_context)

if __name__ == "__main__":
    test_graph_extraction()
    test_role_aware_graph()