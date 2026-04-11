from typing import Dict, Any, List
from app.core.security import SAPAuthContext
from app.core.sql_vector_store import SQLRAGStore
import re

class RoleAwareSQLRetriever:
    """
    Wraps the SQL RAG Vector DB lookup with AuthContext filtering.
    Only returns proven query patterns that reference tables the user
    is authorized to see.
    """
    def __init__(self, auth_context: SAPAuthContext):
        self.auth_context = auth_context
        # We reuse the same store instance across requests in production, 
        # but for scoping, we instantiate here.
        self.store = SQLRAGStore()

    def retrieve(self, query: str) -> str:
        """
        Step 1: Perform Semantic Vector Search on SQL Library
        Step 2: Filter results based on AuthContext (Role-Aware)
        Step 3: Format the valid templates into a few-shot prompt block.
        """
        print(f"\n[SQL_RAG] Retrieving proven query patterns for: '{query}'")
        raw_patterns = self.store.search(query, top_k=3)
        
        filtered_patterns = []
        for pattern in raw_patterns:
            allowed = True
            for table in pattern["tables_used"]:
                if not self.auth_context.is_table_allowed(table):
                    print(f"[SQL_RAG] Filtered out {pattern['query_id']} (Unauthorized table {table} for {self.auth_context.user_id})")
                    allowed = False
                    break
            
            if allowed:
                # Basic threshold filter for cosine distance (adjust per model)
                # Lower distance = higher similarity
                if pattern["distance"] < 1.0: 
                    filtered_patterns.append(pattern)
                else:
                    print(f"[SQL_RAG] Filtered out {pattern['query_id']} (Distance {pattern['distance']} > threshold)")

        if not filtered_patterns:
            return "No relevant or authorized SQL patterns found in library. Generate from schema only."
            
        # Format for LLM prompt context (Few-Shot Injection)
        context_str = "PROVEN SAP HANA SQL PATTERNS (Use as templates):\n\n"
        for i, fp in enumerate(filtered_patterns, 1):
            context_str += f"--- Example {i} ({fp['query_id']}) ---\n"
            context_str += f"Business Intent: {fp['intent']}\n"
            context_str += f"SQL Template:\n{fp['sql_template'].strip()}\n\n"
            
        return context_str