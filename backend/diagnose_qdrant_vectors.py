"""
diagnose_qdrant_vectors.py
Diagnose why Qdrant collections have points but 0 vectors.
"""
import sys, os, json
sys.path.insert(0, r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend")

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
import numpy as np

client = QdrantClient(host="localhost", port=6333, timeout=10)

collections = [
    "sap_schema",
    "sql_patterns",
    "graph_node_embeddings",
    "graph_table_context",
]

print("=== Collection Configs ===")
for name in collections:
    try:
        info = client.get_collection(name)
        params = info.config.params
        vectors_config = params.vectors if hasattr(params, 'vectors') else getattr(params, 'vector_params', None)
        print(f"\n{name}:")
        print(f"  points_count : {info.points_count}")
        print(f"  vectors_count: {getattr(info, 'vectors_count', 'N/A')}")
        print(f"  vectors_config: {vectors_config}")
        print(f"  index_status : {getattr(info, 'index_status', 'N/A')}")
    except Exception as e:
        print(f"\n{name}: ERROR {e}")

print("\n\n=== Attempting Direct Upsert with Vector ===")
# Test: upsert a single point with a known vector
test_vector = [0.1] * 384
test_payload = {"document": "test doc", "table": "TEST_TABLE", "domain": "test"}
import uuid

test_points = [
    PointStruct(
        id=str(uuid.uuid4()),
        vector=test_vector,
        payload=test_payload,
    )
]

try:
    # Create test collection
    from qdrant_client.models import Distance, VectorParams
    try:
        client.delete_collection("test_vector_col")
    except:
        pass
    client.create_collection(
        collection_name="test_vector_col",
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )
    client.upsert(collection_name="test_vector_col", points=test_points, wait=True)
    info = client.get_collection("test_vector_col")
    print(f"  Test upsert: points={info.points_count}, vectors_count={getattr(info, 'vectors_count', 'N/A')}")
    client.delete_collection("test_vector_col")
    print("  Test PASSED — Qdrant accepts vectors normally")
except Exception as e:
    print(f"  Test FAILED: {e}")

print("\n\n=== Checking if graph_embedding_store is Importable ===")
try:
    from app.core.graph_embedding_store import graph_embedding_store
    print(f"  graph_embedding_store loaded OK")
    print(f"  qdrant_client: {type(graph_embedding_store.qdrant_client)}")
    print(f"  embedding_dim: {graph_embedding_store.embedding_dim}")
    print(f"  node_embeddings count: {len(graph_embedding_store._node_embeddings)}")
except Exception as e:
    print(f"  Import FAILED: {e}")
    import traceback; traceback.print_exc()
