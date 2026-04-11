import requests
import json
import time
import os
import sys

# Add backend to path to allow importing the vector store init
sys.path.append(os.path.join(os.path.dirname(__file__), "backend"))
from app.core.vector_store import init_vector_store

API_URL = "http://127.0.0.1:8000/api/v1/chat/master-data"

def test_semantic_search():
    print("--- Initializing ChromaDB Vector Store ---")
    init_vector_store()

    print("\n--- Testing True Semantic Vector Search via API ---")
    
    # In the mock, "who supplies" wouldn't match "vendor" unless explicitly hardcoded.
    # In ChromaDB, the vector distance between "supplies" and "Vendor Master (LFA1)" should be close.
    test_query = "Who supplies me with products?"
    
    payload = {
        "query": test_query,
        "domain": "auto", 
        "user_role": "PROCUREMENT_MANAGER_EU" 
    }
    
    print(f"\nSending Query: '{test_query}'")
    
    try:
        start_time = time.time()
        response = requests.post(API_URL, json=payload, timeout=15)
        latency = time.time() - start_time
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nSuccess! Response received in {latency:.2f} seconds.")
            print(f"Orchestrator identified domain: {data.get('explanation', '')}")
            print(f"Tables resolved via Semantic Search (Schema RAG): {data.get('tables', [])}")
            print(f"LLM Generated SQL:\n{data.get('sql_generated', 'N/A')}")
        else:
            print(f"Failed: {response.status_code}")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
         print("Backend is not accepting connections on port 8000.")

if __name__ == "__main__":
    test_semantic_search()