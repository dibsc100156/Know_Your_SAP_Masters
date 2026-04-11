from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

client = QdrantClient(url="http://localhost:6333", timeout=30)
encoder = SentenceTransformer("all-MiniLM-L6-v2")

print("=== Qdrant Search Tests ===\n")

# Test 1: Schema search
query = "vendor master data business partner"
vec = encoder.encode(query).tolist()
results = client.search(
    collection_name="sap_schema",
    query_vector=vec,
    limit=3,
    with_payload=True,
)
print(f"[1] Schema search: '{query}'")
for r in results:
    print(f"    score={r.score:.3f} | domain={r.payload['domain']} | tables={r.payload['table_count']}")

# Test 2: SQL pattern search
query2 = "open purchase orders for a vendor"
vec2 = encoder.encode(query2).tolist()
results2 = client.search(
    collection_name="sql_patterns_rag",
    query_vector=vec2,
    limit=3,
    with_payload=True,
)
print(f"\n[2] SQL Pattern search: '{query2}'")
for r in results2:
    print(f"    score={r.score:.3f} | name={r.payload['name']} | domain={r.payload['domain']}")
    print(f"    desc: {r.payload['description'][:80]}")

# Test 3: Cross-domain search
query3 = "material stock valuation price"
vec3 = encoder.encode(query3).tolist()
results3 = client.search(
    collection_name="sql_patterns_rag",
    query_vector=vec3,
    limit=3,
    with_payload=True,
)
print(f"\n[3] SQL Pattern search: '{query3}'")
for r in results3:
    print(f"    score={r.score:.3f} | name={r.payload['name']} | domain={r.payload['domain']}")

print("\n✅ Qdrant search working")
