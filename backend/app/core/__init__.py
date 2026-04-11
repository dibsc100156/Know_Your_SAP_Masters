"""
Core services — Security, Vector Stores, Graph, RAG.
"""
from app.core.security import security_mesh, SAP_ROLES, SAPAuthContext
from app.core.graph_store import graph_store

# ── Memgraph migration (Phase M1-M6) ───────────────────────────────────────
# Lazy-import Memgraph components — only load if Memgraph is available and configured.
# In NetworkX-only mode (default), these remain None.
#
# To enable Memgraph:
#   from app.core import use_memgraph
#   graph_store = use_memgraph(uri="bolt://localhost:7687")
#   # All graph_store calls now route through Memgraph.
#
MEMGRAPH_GRAPH_STORE: "MemgraphGraphRAGManager | None" = None


def use_memgraph(uri: str = "bolt://localhost:7687", user: str = "", password: str = "", tenant_id: str = "default") -> "MemgraphGraphRAGManager":
    """
    Replace the global `graph_store` singleton with a Memgraph-backed manager.
    All subsequent calls to `graph_store.traverse_graph()`, `find_path()`, etc.
    route through Memgraph instead of in-memory NetworkX.
    """
    try:
        from app.core.memgraph_adapter import use_memgraph as adapter_use_memgraph
        return adapter_use_memgraph(uri=uri, user=user, password=password, tenant_id=tenant_id)
    except Exception as e:
        import logging, traceback
        traceback.print_exc()
        logging.getLogger(__name__).error(
            f"[use_memgraph] Failed to connect to Memgraph at {uri}: {e}\n"
            "Falling back to NetworkX graph_store."
        )
        raise


__all__ = [
    "security_mesh",
    "SAP_ROLES",
    "SAPAuthContext",
    "graph_store",
    "use_memgraph",
    "MEMGRAPH_GRAPH_STORE",
]
