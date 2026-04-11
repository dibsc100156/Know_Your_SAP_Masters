import asyncio
import json

# Local
from app.core.vector_store import init_vector_store
from app.core.rag_service import query_master_data

async def run_persona_tests():
    """
    Simulates API requests to the Master Data Chatbot from different SAP Personas.
    Demonstrates how the Role-Aware Security Mesh (Pillar 1) filters tables (Schema RAG)
    and masks fields (Row/Column-level security) dynamically.
    """
    
    print("\n--- INITIALIZING VECTOR STORE (Pillars 3 & 4) ---")
    # Load the Business Partner and Material Master DDIC schemas into ChromaDB
    init_vector_store()

    print("\n=======================================================")
    print("      SAP S/4 HANA MASTER DATA CHATBOT TEST SUITE      ")
    print("=======================================================")

    test_cases = [
        {
            "name": "TEST 1: AP Clerk querying Vendor Master (LFA1)",
            "query": "Show me the tax details and address for vendor Acme Corp",
            "domain": "business_partner",
            "role": "AP_CLERK",
            "expected_behavior": "Should retrieve LFA1 but mask the STCD1 (Tax Number) field."
        },
        {
            "name": "TEST 2: Procurement Manager querying Vendor Master (LFA1)",
            "query": "Show me the tax details and address for vendor Acme Corp",
            "domain": "business_partner",
            "role": "PROCUREMENT_MANAGER_EU",
            "expected_behavior": "Should retrieve LFA1 and show the actual STCD1 (Tax Number) field unmasked."
        },
        {
            "name": "TEST 3: HR Admin querying Vendor Groupings (BUT000)",
            "query": "What is the business partner grouping for partner 1000?",
            "domain": "business_partner",
            "role": "HR_ADMIN",
            "expected_behavior": "Should retrieve BUT000 but mask the BU_GROUP field."
        },
        {
            "name": "TEST 4: AP Clerk querying Material Valuation (MBEW)",
            "query": "What is the standard price and moving average price for material P-100?",
            "domain": "material_master",
            "role": "AP_CLERK",
            "expected_behavior": "Should completely block access to the MBEW table via SAP Auth Objects."
        },
        {
            "name": "TEST 5: CFO querying Material Valuation (MBEW)",
            "query": "What is the standard price and moving average price for material P-100?",
            "domain": "material_master",
            "role": "CFO_GLOBAL",
            "expected_behavior": "Should allow access to the MBEW table and return the valuation data."
        },
        {
            "name": "TEST 6: Phase 2 - Graph RAG (Cross-Module Purchasing)",
            "query": "Which vendor supplies material P-100?",
            "domain": "auto",
            "role": "PROCUREMENT_MANAGER_EU",
            "expected_behavior": "Should detect a cross-module query and use Graph RAG to join MARA to LFA1 via EINA."
        },
        {
            "name": "TEST 7: Phase 3 - Transactional Data Integration (Purchase Orders)",
            "query": "Find all purchase orders for material P-100 from vendor Acme Corp",
            "domain": "auto",
            "role": "AP_CLERK",
            "expected_behavior": "Should detect a transactional query and use Graph RAG to join EKPO, EKKO, and MARA."
        }
    ]

    for i, test in enumerate(test_cases, 1):
        print(f"\n\n>>> {test['name']}")
        print(f"Query: '{test['query']}' | Role: {test['role']}")
        print(f"Expectation: {test['expected_behavior']}")
        print("-" * 50)
        
        try:
            # Simulate the FastAPI endpoint call
            response = await query_master_data(
                query=test['query'],
                domain=test['domain'],
                role=test['role']
            )
            
            # Print the formatted JSON response
            print(json.dumps(response, indent=2))
            
        except Exception as e:
            print(f"ERROR: {e}")

if __name__ == "__main__":
    # Ensure we run from the project root so ChromaDB creates locally
    asyncio.run(run_persona_tests())
