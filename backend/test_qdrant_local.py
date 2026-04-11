"""
Test which qdrant approach works on this system.
Run: python test_qdrant_local.py
"""
import sys

# Try qdrant-client-local (true embedded)
try:
    from qdrant_client.local import QdrantLocal
    c = QdrantLocal("./test_local")
    print("qdrant-client-local: AVAILABLE")
    # Try creating a collection
    from qdrant_client.local.qdrant_local import QdrantLocal
    import numpy as np
    v = np.random.rand(384).astype(float).tolist()
    c.upsert("test", [{"id": "1", "vector": v, "payload": {"a": 1}}])
    r = c.search("test", query_vector=v, limit=1)
    print(f"  upsert+search: OK, found {len(r)} results")
    sys.exit(0)
except ImportError:
    print("qdrant-client-local: NOT INSTALLED")
except Exception as e:
    print(f"qdrant-client-local: ERROR — {e}")

# Try qdrant-client with remote server
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    c = QdrantClient(location="./test_remote")
    c.create_collection("test_c", vectors_config=VectorParams(size=384, distance=Distance.COSINE))
    print("qdrant-client remote-location: OK")
    import numpy as np
    v = np.random.rand(384).astype(float).tolist()
    c.upsert("test_c", points=[PointStruct(id=1, vector=v, payload={"a": 1})])
    r = c.search("test_c", query_vector=v, limit=1)
    print(f"  upsert+search: OK, found {len(r)} results")
    sys.exit(0)
except ImportError:
    print("qdrant-client: NOT INSTALLED")
except Exception as e:
    print(f"qdrant-client remote-location: ERROR — {e}")

print("\nNeither approach works. Install qdrant-client-local for true embedded mode:")
print("  pip install qdrant-client-local")
