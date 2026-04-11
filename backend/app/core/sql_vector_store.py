import os
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
import chromadb
from app.core.sql_library import get_sql_library

class SQLRAGStore:
    """
    Manages the Vector Database for the SQL Pattern Library.
    Embeds the natural language intents of proven queries,
    and retrieves them based on semantic similarity to the user's question.
    """
    def __init__(self, db_path: str = "./chroma_db", collection_name: str = "sap_sql_patterns"):
        self.db_path = db_path
        self.collection_name = collection_name
        
        # In production, use text-embedding-3-large or Gemini via LangChain.
        # For scaffolding locally without keys, use an open-source local model.
        print(f"[SQL_RAG] Loading embedding model (all-MiniLM-L6-v2)...")
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
        
        print(f"[SQL_RAG] Initializing ChromaDB at {self.db_path}")
        self.client = chromadb.PersistentClient(path=self.db_path)
        
        # Create or get the collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def initialize_library(self):
        """Seed the vector store with the SQL template library."""
        library = get_sql_library()
        
        print(f"[SQL_RAG] Seeding {len(library)} proven query patterns...")
        
        ids = []
        embeddings = []
        metadatas = []
        documents = []
        
        for entry in library:
            # We embed the business intent + variants, NOT the raw SQL syntax.
            text_to_embed = f"Business Question: {entry['intent_description']} | Variants: {' '.join(entry['natural_language_variants'])}"
            
            ids.append(entry["query_id"])
            embeddings.append(self.encoder.encode(text_to_embed).tolist())
            documents.append(entry["sql_template"])
            metadatas.append({
                "module": entry["module"],
                "tables_used": ",".join(entry["tables_used"]),
                "intent": entry["intent_description"]
            })
            
        # Upsert into ChromaDB
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            metadatas=metadatas,
            documents=documents
        )
        print(f"[SQL_RAG] Vector store seeded successfully.")

    def search(self, query: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """Find the most semantically similar proven queries for few-shot injection."""
        print(f"[SQL_RAG] Searching for patterns matching: '{query}'")
        
        query_embedding = self.encoder.encode(query).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        retrieved_patterns = []
        if results and results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                retrieved_patterns.append({
                    "query_id": results['ids'][0][i],
                    "intent": results['metadatas'][0][i]['intent'],
                    "sql_template": results['documents'][0][i],
                    "tables_used": results['metadatas'][0][i]['tables_used'].split(','),
                    "distance": results['distances'][0][i] if 'distances' in results else 0.0
                })
                
        return retrieved_patterns