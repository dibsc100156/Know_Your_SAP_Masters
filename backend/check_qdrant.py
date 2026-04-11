from qdrant_client import QdrantClient

client = QdrantClient(url="http://localhost:6333", timeout=60)
SCHEMA_COLLECTION = "sap_schema"
SQL_COLLECTION = "sql_patterns_rag"

for col in [SCHEMA_COLLECTION, SQL_COLLECTION]:
    print(f"\n=== {col} ===")
    try:
        info = client.get_collection(col)
        print(f"points_count: {info.points_count}")
        print(f"vectors_count: {info.vectors_count}")
        results = client.scroll(collection_name=col, limit=30, with_payload=True)
        for pt in results[0]:
            print(f"  ID={pt.id} | domain={pt.payload.get('domain','?')} | type={pt.payload.get('type','?')} | name={pt.payload.get('name','?')}")
    except Exception as e:
        print(f"ERROR: {e}")
