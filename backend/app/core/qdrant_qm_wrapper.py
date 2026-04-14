import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, Range

class QdrantCollectionWrapper:
    """Wrapper that makes QdrantClient act like ChromaDB's Collection for QM Semantic Search."""
    def __init__(self, collection_name: str):
        host = os.environ.get("QDRANT_HOST", "localhost")
        port = int(os.environ.get("QDRANT_PORT", "6333"))
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        self._ensure_collection()

    def _ensure_collection(self):
        colls = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in colls:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE)
            )

    def add(self, documents: list, embeddings: list, metadatas: list, ids: list):
        import uuid
        points = []
        for doc, emb, meta, text_id in zip(documents, embeddings, metadatas, ids):
            # Convert text_id (hash string) to UUID
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, text_id))
            meta["document"] = doc
            points.append(PointStruct(id=point_id, vector=emb, payload=meta))
        
        for i in range(0, len(points), 200):
            self.client.upsert(collection_name=self.collection_name, points=points[i:i+200])

    def query(self, query_embeddings: list = None, query_texts: list = None, n_results: int = 10, where: dict = None, include: list = None):
        q_filter = None
        if where:
            conditions = []
            for k, v in where.items():
                if isinstance(v, dict):
                    if "$gte" in v or "$lte" in v:
                        conditions.append(FieldCondition(key=k, range=Range(gte=v.get("$gte"), lte=v.get("$lte"))))
                    elif "$in" in v:
                        from qdrant_client.models import MatchAny
                        conditions.append(FieldCondition(key=k, match=MatchAny(any=v["$in"])))
                else:
                    conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
            if conditions:
                q_filter = Filter(must=conditions)
        
        if query_embeddings:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embeddings[0],
                limit=n_results,
                query_filter=q_filter,
                with_payload=True,
                with_vectors=False
            )
        elif query_texts:
            # Qdrant requires vectors, we can't do keyword search easily without an encoder
            # If this is fallback, we just return empty
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        
        # Return format mimicking ChromaDB
        out = {
            "documents": [[r.payload.get("document", "")] for r in results],
            "metadatas": [[{k:v for k,v in r.payload.items() if k != "document"}] for r in results],
            "distances": [[1.0 - r.score] for r in results] # Convert cosine similarity to distance
        }
        return out

    def count(self) -> int:
        return self.client.count(self.collection_name, exact=True).count
