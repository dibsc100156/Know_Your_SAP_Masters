from typing import Dict, Any, List
from app.core.security import SAPAuthContext
from app.core.schema_store import search_tables

class RoleAwareSchemaRetriever:
    """
    Wraps the raw Schema RAG lookup with AuthContext filtering.
    Only returns table definitions the user is authorized to see.
    Also strips sensitive columns from the schema definition
    so the LLM cannot hallucinate queries that select them.
    """
    def __init__(self, auth_context: SAPAuthContext):
        self.auth_context = auth_context

    def retrieve(self, query: str) -> str:
        """
        Step 1: Perform Vector Search (Schema RAG)
        Step 2: Filter the results based on AuthContext (Role-Aware RAG)
        """
        print(f"\n[SchemaRAG] Retrieving schema for: '{query}'")
        raw_schemas = search_tables(query)
        
        filtered_schemas = []
        for schema in raw_schemas:
            # 1. Check if the table is explicitly denied by role
            if not self.auth_context.is_table_allowed(schema["table"]):
                print(f"[SchemaRAG] Filtered out {schema['table']} (Unauthorized for {self.auth_context.user_id})")
                continue
                
            # 2. Filter out sensitive columns from the schema context
            safe_columns = []
            for col in schema.get("key_columns", []):
                # If the column is NOT in the user's masked list, the LLM can see it exists
                if col.upper() not in [m.upper() for m in self.auth_context.masked_columns]:
                    safe_columns.append(col)
                    
            filtered_schema = {
                "Table": schema["table"],
                "Description": schema["description"],
                "Safe Columns to Query": safe_columns
            }
            filtered_schemas.append(filtered_schema)

        if not filtered_schemas:
            return "No authorized tables found for your query. You may lack the necessary SAP role."
            
        # Format for LLM prompt context
        context_str = "SAP Schema Metadata:\n"
        for fs in filtered_schemas:
            context_str += f"- Table: {fs['Table']}\n  Description: {fs['Description']}\n  Columns: {', '.join(fs['Safe Columns to Query'])}\n\n"
            
        return context_str