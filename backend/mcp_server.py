import sys
import os
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Basic configure
logging.basicConfig(level=logging.WARNING)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("mcp package is required. Install via `pip install mcp`")
    sys.exit(1)

from app.agents.orchestrator_tools import schema_lookup, sql_pattern_lookup, all_paths_explore

# We need a dummy auth context to bypass role filtering since MCP clients might not have a real role.
class DummyAuthContext:
    def __init__(self, role_id="MCP_ADMIN"):
        self.role_id = role_id
        
    def is_table_allowed(self, table: str) -> bool:
        return True
        
    def filter_columns(self, table: str, columns: list) -> list:
        return columns

mcp = FastMCP("KYSM_MCP", dependencies=["mcp"])

@mcp.tool()
def search_sap_schema(query: str, domain: str = "auto", n_results: int = 4) -> str:
    """
    Search for relevant SAP tables and fields based on a natural language query.
    Returns schema metadata including table names, descriptions, and key columns.
    """
    try:
        ctx = DummyAuthContext()
        res = schema_lookup(query=query, auth_context=ctx, domain=domain, n_results=n_results)
        if res.status.value == "error":
            return f"Error: {res.message}"
        return json.dumps(res.data, indent=2)
    except Exception as e:
        return f"Exception: {str(e)}"

@mcp.tool()
def match_sql_patterns(query: str, domain: str = "auto", n_results: int = 2) -> str:
    """
    Find proven SAP SQL query patterns matching a natural language intent.
    Returns SQL templates and the tables they use.
    """
    try:
        ctx = DummyAuthContext()
        res = sql_pattern_lookup(query=query, auth_context=ctx, domain=domain, n_results=n_results)
        if res.status.value == "error":
            return f"Error: {res.message}"
        return json.dumps(res.data, indent=2)
    except Exception as e:
        return f"Exception: {str(e)}"

@mcp.tool()
def traverse_graph(start_table: str, end_table: str, max_depth: int = 5, top_k: int = 3) -> str:
    """
    Find the best JOIN paths between two SAP tables.
    Returns ranked paths with JOIN conditions.
    """
    try:
        res = all_paths_explore(start_table=start_table, end_table=end_table, max_depth=max_depth, top_k=top_k)
        if res.status.value == "error":
            return f"Error: {res.message}"
        return json.dumps(res.data, indent=2)
    except Exception as e:
        return f"Exception: {str(e)}"

if __name__ == "__main__":
    mcp.run()