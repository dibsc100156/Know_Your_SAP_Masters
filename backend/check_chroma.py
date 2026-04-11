import chromadb
import json

try:
    print(f"ChromaDB Version: {chromadb.__version__}")
    client = chromadb.PersistentClient(path='./chroma_db')
    settings = client.get_settings()
    
    # model_dump_json is available in pydantic v2 which chroma 1.5.5 uses
    print("\n--- ChromaDB Configuration ---")
    print(settings.model_dump_json(indent=2))
except Exception as e:
    print(f"Error initializing ChromaDB: {e}")
