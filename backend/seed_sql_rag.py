import os
from app.core.sql_vector_store import SQLRAGStore

def init_db():
    print("\n--- Initializing SQL RAG Vector Database ---")
    store = SQLRAGStore(db_path="./chroma_db", collection_name="sap_sql_patterns")
    store.initialize_library()
    print("--- Initialization Complete ---\n")
    
def test_retrieval():
    print("\n--- Testing SQL RAG Semantic Retrieval ---")
    store = SQLRAGStore(db_path="./chroma_db", collection_name="sap_sql_patterns")
    
    test_queries = [
        "How many purchase orders are still pending delivery?",
        "Show me which suppliers have invoices that are past due",
        "What is the total amount we spent with our top 10 vendors last month?"
    ]
    
    for query in test_queries:
        print(f"\nUser Query: '{query}'")
        results = store.search(query, top_k=1)
        if results:
            match = results[0]
            print(f"✅ Retrieved Pattern: {match['query_id']} (Distance: {match['distance']:.3f})")
            print(f"   Intent: {match['intent']}")
            print(f"   Tables: {match['tables_used']}")
        else:
            print("❌ No matches found.")

if __name__ == "__main__":
    init_db()
    test_retrieval()