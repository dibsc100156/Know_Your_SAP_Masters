from typing import Dict, Any, List
from app.core.security import SAPAuthContext
from app.core.graph_store import SAPGraphStore
import re

class RoleAwareGraphRetriever:
    """
    Wraps the Graph RAG Subgraph extraction with AuthContext filtering.
    Given a list of seed tables (from Schema RAG), extracts a minimal
    subgraph of joins, but PRUNES any branches leading to unauthorized tables.
    """
    def __init__(self, auth_context: SAPAuthContext):
        self.auth_context = auth_context
        # We reuse the same store instance across requests in production
        self.store = SAPGraphStore()

    def retrieve(self, seed_tables: List[str]) -> str:
        """
        Step 1: Extract Subgraph from Knowledge Graph (Graph RAG)
        Step 2: Filter results based on AuthContext (Role-Aware)
        Step 3: Format the valid join paths for the LLM.
        """
        print(f"\n[Graph_RAG] Extracting subgraph from seeds: {seed_tables}")
        
        # 1. Ask Graph DB for the connected component (max 2 hops)
        raw_subgraph = self.store.extract_subgraph(seed_tables, max_hops=2)
        
        # 2. Filter out tables the user cannot access
        authorized_tables = []
        for table_str in raw_subgraph.get("tables", []):
            table_name = table_str.split(" ")[0].upper() # e.g. "EKKO (Purchase Order)" -> "EKKO"
            if self.auth_context.is_table_allowed(table_name):
                authorized_tables.append(table_str)
            else:
                print(f"[Graph_RAG] Filtered table {table_name} (Unauthorized for {self.auth_context.user_id})")
                
        # 3. Filter out join paths that reference an unauthorized table
        authorized_edges = []
        for edge_str in raw_subgraph.get("join_paths", []):
            # Extract the table names from "[LFA1] --(JOINS_TO on LFA1.LIFNR = BSIK.LIFNR)--> [BSIK]"
            match = re.search(r'\[([A-Z0-9_]+)\].*?\[([A-Z0-9_]+)\]', edge_str)
            if match:
                t1, t2 = match.groups()
                if self.auth_context.is_table_allowed(t1) and self.auth_context.is_table_allowed(t2):
                    authorized_edges.append(edge_str)
                else:
                    print(f"[Graph_RAG] Pruned edge {t1}->{t2} (Unauthorized table in path)")
                    
        if not authorized_edges:
            return "No authorized structural relationships found for these tables."
            
        # Format for LLM prompt context (Subgraph Injection)
        context_str = "SAP STRUCTURAL RELATIONSHIPS (Join paths to use in SQL):\n\n"
        context_str += "Connected Tables Available:\n"
        for t in authorized_tables:
            context_str += f"- {t}\n"
            
        context_str += "\nExplicit Join Paths (Use these EXACT keys when joining):\n"
        for e in authorized_edges:
            context_str += f"- {e}\n"
            
        return context_str