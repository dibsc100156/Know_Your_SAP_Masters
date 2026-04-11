"""
memgraph_adapter.py - Memgraph Migration Layer for Know Your SAP Masters
=========================================================================
Drop-in replacement for NetworkX-backed GraphRAGManager.

Maps the existing NetworkX graph semantics onto Memgraph via Cypher.
Preserves the EXACT same public API - same method signatures, same return types.

Why Memgraph over Neo4j for this project:
  ✓ Built-in NetworkX compatibility (mg_networkx)
  ✓ Native vector search (hybrid graph + ANN in one DB)
  ✓ Lower memory footprint (in-memory + disk overflow)
  ✓ Apache 2.0 - no license friction for on-prem / private cloud
  ✓ Cypher is industry-standard; no vendor lock-in
  ✓ Horizontal read replicas for scaling query throughput

Migration status: SCAFFOLD - implement the TODOs to activate.

Usage:
    from app.core.memgraph_adapter import MemgraphGraphRAGManager

    # Replace in-memory NetworkX with distributed Memgraph
    graph = MemgraphGraphRAGManager(uri="bolt://memgraph:7687", user="", password="")
    graph.build_enterprise_schema_graph()   # loads all 80+ nodes + 100+ edges
    path = graph.traverse_graph("MARA", "LFA1")  # same API as before
"""

from __future__ import annotations

import os
import re
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import numpy as np

# Memgraph client - install via: pip install gqlalchemy
# Try multiple possible venv locations to find gqlalchemy
import sys as _sys
import os as _os

def _ensure_gqlalchemy():
    """Try to locate and import gqlalchemy from common venv locations."""
    # Candidate venv site-packages directories to check
    _adapter_dir = _os.path.dirname(_os.path.abspath(__file__))  # .../backend/app/core
    _backend_dir = _os.path.dirname(_adapter_dir)               # .../backend
    _project_dir = _os.path.dirname(_backend_dir)               # .../SAP_HANA_LLM_VendorChatbot
    _candidates = [
        _os.path.join(_backend_dir, ".venv", "Lib", "site-packages"),
        _os.path.join(_project_dir, ".venv", "Lib", "site-packages"),
    ]
    for _p in _candidates:
        if _p not in _sys.path and _os.path.exists(_p):
            _sys.path.insert(0, _p)

_ensure_gqlalchemy()
try:
    from gqlalchemy import Memgraph, Node, Relationship, Field
    MEMGRAPH_AVAILABLE = True
except ImportError:
    MEMGRAPH_AVAILABLE = False
    Memgraph = None

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses - mirror the NetworkX metadata we already defined
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MemgraphNodeMeta:
    module: str
    domain: str
    desc: str
    key_columns: List[str]
    # Structural properties computed from the graph
    degree_centrality: float = 0.0
    betweenness_centrality: float = 0.0
    bridge_table: bool = False   # True if cross-module bridge node


@dataclass
class MemgraphEdgeMeta:
    condition: str
    cardinality: str      # "1:1", "N:1", "1:N"
    bridge_type: str      # "internal" | "cross_module"
    notes: str


# ─────────────────────────────────────────────────────────────────────────────
# Memgraph-backed Graph RAG Manager
# ─────────────────────────────────────────────────────────────────────────────

class MemgraphGraphRAGManager:
    """
    Drop-in replacement for GraphRAGManager (NetworkX).
    Stores the SAP enterprise schema graph in Memgraph.

    Public API - IDENTICAL to GraphRAGManager:
        traverse_graph(), find_path(), get_join_condition(),
        get_subgraph_context(), get_neighbors(), get_all_tables(),
        get_table_meta(), stats(), print_map()
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "",
        password: str = "",
        load_on_init: bool = True,
        tenant_id: str = "default",
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.tenant_id = tenant_id
        self.tenant_label = f"Tenant_{tenant_id}"
        self._mg: Optional["Memgraph"] = None
        self._node_meta: Dict[str, MemgraphNodeMeta] = {}
        self._edge_meta: Dict[Tuple[str, str], MemgraphEdgeMeta] = {}
        self._nx_cache: Optional[nx.Graph] = None  # NetworkX mirror for algorithms

        if MEMGRAPH_AVAILABLE:
            self._connect()
        else:
            logger.warning(
                "[MemgraphGraphRAGManager] gqlalchemy not installed. "
                "Run: pip install gqlalchemy\n"
                "Falling back to NetworkX-only mode."
            )

        if load_on_init:
            self.build_enterprise_schema_graph()

    # ─── Connection Management ─────────────────────────────────────────────────

    def _connect(self):
        """Establish connection to Memgraph instance."""
        try:
            self._mg = Memgraph(host=self.uri.split("://")[1].split(":")[0],
                                port=int(self.uri.split(":")[-1]),
                                username=self.user,
                                password=self.password)
            # Test connection
            list(self._mg.execute_and_fetch("RETURN 1 AS test"))
            logger.info(f"[Memgraph] Connected to {self.uri}")
        except Exception as e:
            logger.error(f"[Memgraph] Connection failed: {e}. Falling back to NetworkX.")
            self._mg = None

    def _reconnect(self):
        """Reconnect after a connection loss."""
        self._mg = None
        self._connect()

    @property
    def _is_connected(self) -> bool:
        """Check if Memgraph connection is alive."""
        if not self._mg:
            return False
        try:
            list(self._mg.execute_and_fetch("RETURN 1"))
            return True
        except Exception:
            return False

    # ─── Node / Edge helpers ───────────────────────────────────────────────────

    def _ensure_connected(self):
        if not self._is_connected:
            self._reconnect()
            if not self._is_connected:
                raise RuntimeError(
                    "[Memgraph] Not connected. Start Memgraph or run in NetworkX-only mode."
                )

    def _add_node(self, table: str, module: str, domain: str, desc: str, key_cols: List[str]):
        """Add a table node to Memgraph with full metadata."""
        self._node_meta[table] = MemgraphNodeMeta(
            module=module, domain=domain, desc=desc, key_columns=key_cols
        )

        if self._mg is None:
            return  # NetworkX fallback only

        cypher = f"""
        MERGE (t:SAPTable:{self.tenant_label} {{table_name: $table}})
        SET t.module      = $module,
            t.domain       = $domain,
            t.description  = $desc,
            t.key_columns  = $key_cols,
            t.table        = $table  // legacy label
        """
        try:
            self._mg.execute(
                cypher,
                params={
                    "table": table,
                    "module": module,
                    "domain": domain,
                    "desc": desc,
                    "key_cols": key_cols,
                },
            )
        except Exception as e:
            logger.warning(f"[Memgraph] _add_node({table}) failed: {e}")

    def _add_edge(
        self,
        t1: str, t2: str,
        condition: str,
        cardinality: str = "1:1",
        bridge_type: str = "internal",
        notes: str = "",
    ):
        """Add an FK relationship edge to Memgraph."""
        self._edge_meta[(t1, t2)] = MemgraphEdgeMeta(
            condition=condition,
            cardinality=cardinality,
            bridge_type=bridge_type,
            notes=notes,
        )

        if self._mg is None:
            return  # NetworkX fallback only

        cypher = f"""
        MATCH (a:SAPTable:{self.tenant_label} {{table_name: $t1}})
        MATCH (b:SAPTable:{self.tenant_label} {{table_name: $t2}})
        MERGE (a)-[r:FOREIGN_KEY]->(b)
        SET r.condition   = $condition,
            r.cardinality = $cardinality,
            r.bridge_type = $bridge_type,
            r.notes       = $notes
        """
        try:
            self._mg.execute(
                cypher,
                params={
                    "t1": t1, "t2": t2,
                    "condition": condition,
                    "cardinality": cardinality,
                    "bridge_type": bridge_type,
                    "notes": notes,
                },
            )
        except Exception as e:
            logger.warning(f"[Memgraph] _add_edge({t1}→{t2}) failed: {e}")

    # ─── Sync with NetworkX (for algorithms that aren't yet Cypher-native) ──────

    def _sync_nx_from_memgraph(self):
        """
        Build a NetworkX mirror from local metadata (M2 path) or Memgraph (fallback).

        After Phase M2, _node_meta and _edge_meta are ALWAYS populated by
        build_enterprise_schema_graph() during schema load, so this method
        almost never needs to query Memgraph. It only falls back to Memgraph
        queries if _node_meta is completely empty (e.g., fresh adapter without load).
        """
        if self._nx_cache is not None:
            return

        G = nx.Graph()

        # ── Priority: build from already-populated local metadata (M2 path) ──
        if self._node_meta:
            for table in self._node_meta.keys():
                G.add_node(table)
            for (t1, t2), meta in self._edge_meta.items():
                G.add_edge(t1, t2,
                    condition=meta.condition,
                    cardinality=meta.cardinality,
                    bridge_type=meta.bridge_type,
                    notes=meta.notes,
                )
            self._nx_cache = G
            return

        # ── Fallback: query Memgraph directly (pre-M2 or hot-reload) ─────────
        node_query = f"MATCH (t:SAPTable:{self.tenant_label}) RETURN t.table_name, t.module, t.domain, t.description, t.key_columns"
        try:
            for row in self._mg.execute_and_fetch(node_query):
                t = row["t.table_name"]
                G.add_node(t)
                self._node_meta.setdefault(t, MemgraphNodeMeta(
                    module=row.get("t.module", "?"),
                    domain=row.get("t.domain", "?"),
                    desc=row.get("t.description", ""),
                    key_columns=row.get("t.key_columns", []),
                ))
        except Exception:
            for table in self._node_meta.keys():
                G.add_node(table)

        edge_query = f"""
        MATCH (a:SAPTable:{self.tenant_label})-[r:FOREIGN_KEY]->(b:SAPTable:{self.tenant_label})
        RETURN a.table_name AS src, b.table_name AS tgt,
               r.condition AS condition, r.cardinality AS cardinality,
               r.bridge_type AS bridge_type, r.notes AS notes
        """
        try:
            for row in self._mg.execute_and_fetch(edge_query):
                G.add_edge(
                    row["src"], row["tgt"],
                    condition=row["condition"],
                    cardinality=row["cardinality"],
                    bridge_type=row["bridge_type"],
                    notes=row["notes"],
                )
                self._edge_meta[(row["src"], row["tgt"])] = MemgraphEdgeMeta(
                    condition=row["condition"],
                    cardinality=row["cardinality"],
                    bridge_type=row["bridge_type"],
                    notes=row["notes"],
                )
        except Exception:
            for (t1, t2), meta in self._edge_meta.items():
                G.add_edge(t1, t2,
                    condition=meta.condition,
                    cardinality=meta.cardinality,
                    bridge_type=meta.bridge_type,
                    notes=meta.notes,
                )

        self._nx_cache = G

    def _get_nx(self) -> nx.Graph:
        """Get NetworkX graph (from Memgraph or in-memory fallback)."""
        self._sync_nx_from_memgraph()
        return self._nx_cache

    @property
    def G(self) -> nx.Graph:
        """
        Expose the NetworkX graph directly - enables transparent drop-in
        replacement for code that accesses graph_store.G.nodes / .edges directly
        (e.g. orchestrator_tools.py graph_traverse tool).

        Returns the cached NetworkX mirror (lazily built from Memgraph on first access).
        """
        return self._get_nx()

    # ─── Public API — IDENTICAL signatures to GraphRAGManager ─────────────────

    def _get_schema_path(self) -> Optional[str]:
        """Locate init_schema.cql relative to this adapter's file location."""
        _adapter = _os.path.dirname(_os.path.abspath(__file__))
        _backend = _os.path.dirname(_adapter)
        _project = _os.path.dirname(_backend)
        _candidates = [
            _os.path.join(_project, "docker", "memgraph", "init_schema.cql"),
            _os.path.join(_backend, "docker", "memgraph", "init_schema.cql"),
            _os.path.join(_adapter, "..", "..", "..", "docker", "memgraph", "init_schema.cql"),
        ]
        for p in _candidates:
            if _os.path.exists(p):
                return p
        return None

    def _parse_node_statement(self, line: str) -> Optional[dict]:
        """
        Parse a single MERGE node line from init_schema.cql.
        Returns a dict with table_name, module, domain, description, key_columns, bridge
        or None if the line is not a node statement.
        """
        # Match: MERGE (m:SAPTable {table_name:"TABLE"}) SET m.module="...", ...
        m = re.search(
            r'MERGE\s*\(\s*m:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*'
            r'SET\s*m\.module="([^"]*)"\s*,\s*m\.domain="([^"]*)"'
            r'(?:\s*,\s*m\.description="([^"]*)")?'
            r'(?:\s*,\s*m\.key_columns=\[([^\]]*)\])?'
            r'(?:\s*,\s*m\.bridge=(true|false))?',
            line, re.IGNORECASE
        )
        if not m:
            return None

        table_name = m.group(1).upper()
        module = m.group(2)
        domain = m.group(3)
        description = m.group(4) or ""
        bridge = m.group(6) == "true" if m.lastindex and m.lastindex >= 6 else False

        # Parse key_columns JSON array: ["COL1","COL2"] or ["COL1"]
        key_cols: List[str] = []
        raw_keys = m.group(5) or ""
        if raw_keys:
            key_cols = [k.strip().strip('"').strip("'") for k in raw_keys.split(",") if k.strip()]

        return {
            "table_name": table_name,
            "module": module,
            "domain": domain,
            "description": description,
            "key_columns": key_cols,
            "bridge": bridge,
        }

    def _parse_edge_statement(self, line: str) -> Optional[dict]:
        """
        Parse a single MATCH/MERGE edge line from init_schema.cql.
        Returns a dict with src, tgt, condition, cardinality, bridge_type, notes
        or None if the line is not an edge statement.

        The Cypher edge syntax is:
          MATCH (a:SAPTable {table_name:"SRC"}), (b:SAPTable {table_name:"TGT"})
          MERGE (a)-[:FOREIGN_KEY {condition:"...", cardinality:"...", ...}]->(b)

        Note: the hyphen in ")-[:" is required in the regex.
        Uses two-step matching: (1) main structure, (2) property extraction.
        """
        # Step 1: match the overall edge structure
        # The line looks like: MATCH (a:SAPTable {table_name:"MARA"}), (b:SAPTable {table_name:"MARC"}) MERGE (a)-[:FOREIGN_KEY {condition:"...", cardinality:"...", bridge_type:"...", notes:"..."}]->(b)
        edge_match = re.search(
            r'MATCH\s*\(\s*a:SAPTable\s*\{table_name:"([^"]+)"\}\s*\)\s*,\s*'
            r'\(\s*b:SAPTable\s*\{table_name:"([^"]+)"\}\s*\)\s*'
            r'MERGE\s*\(\s*a\s*\)\s*-\s*\[:FOREIGN_KEY\s*\{([^}]*)\}\s*\]\s*->\s*\(\s*b\s*\)',
            line, re.IGNORECASE
        )
        if not edge_match:
            return None

        # Step 2: extract properties from inside the {...} block
        props_str = edge_match.group(3)
        props_match = re.search(
            r'condition:"([^"]*)"\s*,\s*'
            r'cardinality:"([^"]*)"\s*,\s*'
            r'bridge_type:"([^"]*)"'
            r'(?:\s*,\s*notes:"([^"]*)")?',
            props_str, re.IGNORECASE
        )
        if not props_match:
            return None

        return {
            "src": edge_match.group(1).upper(),
            "tgt": edge_match.group(2).upper(),
            "condition": props_match.group(1),
            "cardinality": props_match.group(2),
            "bridge_type": props_match.group(3),
            "notes": props_match.group(4) if props_match.lastindex and props_match.lastindex >= 4 else "",
        }

    def _build_nx_from_local_metadata(self):
        """
        Build the NetworkX graph from our local _node_meta and _edge_meta
        dictionaries (populated by _add_node / _add_edge).

        Called at the end of build_enterprise_schema_graph() to ensure the NX
        mirror is immediately available without needing to query Memgraph.
        """
        G = nx.Graph()
        for table, meta in self._node_meta.items():
            G.add_node(table)
        for (t1, t2), meta in self._edge_meta.items():
            G.add_edge(t1, t2, **{
                "condition": meta.condition,
                "cardinality": meta.cardinality,
                "bridge_type": meta.bridge_type,
                "notes": meta.notes,
            })
        self._nx_cache = G
        return G

    def build_enterprise_schema_graph(self):
        """
        Phase M2: Direct Cypher port — no NetworkX delegation dependency.

        Loads the full SAP enterprise schema by parsing init_schema.cql directly
        and executing Cypher via Memgraph's Bolt protocol. Populates both
        Memgraph AND local _node_meta / _edge_meta in one pass.

        Schema file is located relative to this adapter's file:
          ../../../docker/memgraph/init_schema.cql
        (or ../../docker/memgraph/init_schema.cql depending on install depth)

        Falls back to the NetworkX delegate path if the schema file is missing.
        """
        schema_path = self._get_schema_path()
        if not schema_path:
            logger.warning(
                f"[Memgraph] init_schema.cql not found. "
                f"Checked: schema_path candidates. Falling back to NetworkX."
            )
            self._build_graph_direct()
            return

        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception as e:
            logger.warning(f"[Memgraph] Could not read {schema_path}: {e}. "
                          "Falling back to NetworkX.")
            self._build_graph_direct()
            return

        # ── Parse and classify all statements ────────────────────────────────
        node_stmts, edge_stmts, index_stmts, other_stmts = [], [], [], []
        buf = []
        for raw_line in raw.splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped.startswith("--"):
                continue
            buf.append(stripped)
            if stripped.endswith(";"):
                stmt = " ".join(buf)
                buf = []
                if re.match(r'CREATE\s+INDEX', stmt, re.IGNORECASE):
                    index_stmts.append(stmt)
                elif self._parse_node_statement(stmt):
                    node_stmts.append(stmt)
                elif self._parse_edge_statement(stmt):
                    edge_stmts.append(stmt)
                elif re.match(r'REturn\s+', stmt, re.IGNORECASE):
                    pass  # skip RETURN verification statement at end
                else:
                    other_stmts.append(stmt)

        logger.info(
            f"[Memgraph] Parsed: {len(index_stmts)} indexes, "
            f"{len(node_stmts)} nodes, {len(edge_stmts)} edges"
        )

        # ── Execute index statements ───────────────────────────────────────────
        for stmt in index_stmts:
            try:
                if self._mg:
                    self._mg.execute(stmt)
            except Exception as e:
                logger.debug(f"[Memgraph] Index stmt skipped: {e}")

        # ── Execute node and edge statements (via _add_node / _add_edge) ──────
        # This populates BOTH Memgraph (via Bolt) AND local metadata dictionaries
        nodes_added, edges_added = 0, 0
        for stmt in node_stmts:
            parsed = self._parse_node_statement(stmt)
            if parsed:
                self._add_node(
                    table=parsed["table_name"],
                    module=parsed["module"],
                    domain=parsed["domain"],
                    desc=parsed["description"],
                    key_cols=parsed["key_columns"],
                )
                nodes_added += 1

        for stmt in edge_stmts:
            parsed = self._parse_edge_statement(stmt)
            if parsed:
                self._add_edge(
                    t1=parsed["src"],
                    t2=parsed["tgt"],
                    condition=parsed["condition"],
                    cardinality=parsed["cardinality"],
                    bridge_type=parsed["bridge_type"],
                    notes=parsed["notes"],
                )
                edges_added += 1

        # ── Build NetworkX mirror from local metadata (no Memgraph round-trip) ─
        self._build_nx_from_local_metadata()

        # ── Compute and store centrality ────────────────────────────────────────
        self._compute_and_store_centrality()

        logger.info(
            f"[Memgraph] Schema loaded: {nodes_added} nodes, "
            f"{edges_added} edges → Memgraph + NetworkX mirror built locally."
        )

    def _build_graph_direct(self):
        """
        Fallback: load schema via GraphRAGManager delegation.

        This is called when init_schema.cql cannot be found or read.
        It delegates to GraphRAGManager (which has all node/edge data in code)
        and syncs the result to Memgraph — same as the original pre-M2 approach.

        This fallback should rarely be hit in production.
        """
        logger.warning(
            "[Memgraph] init_schema.cql not found — falling back to "
            "GraphRAGManager delegation. NetworkX-only mode."
        )
        try:
            from app.core.graph_store import GraphRAGManager as NXGraphRAGManager
            nx_builder = NXGraphRAGManager()
        except Exception as e:
            logger.error(f"[Memgraph] Both init_schema.cql and GraphRAGManager "
                        f"delegation failed: {e}. Graph will be empty.")
            return

        # Sync nodes (GraphRAGManager stores dicts — use .get access)
        for table, meta in nx_builder._node_meta.items():
            node_dict = meta if isinstance(meta, dict) else (meta.__dict__ if hasattr(meta, '__dict__') else {})
            self._add_node(
                table,
                node_dict.get("module", "?"),
                node_dict.get("domain", "?"),
                node_dict.get("desc", ""),
                node_dict.get("key_columns", []),
            )
        # Sync edges
        for (t1, t2), meta in nx_builder._edge_meta.items():
            edge_dict = meta if isinstance(meta, dict) else (meta.__dict__ if hasattr(meta, '__dict__') else {})
            self._add_edge(
                t1, t2,
                edge_dict.get("condition", "?"),
                edge_dict.get("cardinality", "?"),
                edge_dict.get("bridge_type", "?"),
                edge_dict.get("notes", ""),
            )

        self._build_nx_from_local_metadata()
        self._compute_and_store_centrality()
        logger.info(
            f"[Memgraph] Fallback loaded: {len(nx_builder._node_meta)} nodes, "
            f"{len(nx_builder._edge_meta)} edges."
        )

    def _compute_and_store_centrality(self):
        """
        After loading, compute degree and betweenness centrality via NetworkX
        and store results back as node properties in Memgraph for Cypher queries.

        Called automatically at the end of build_enterprise_schema_graph().
        """
        if not self._mg:
            return

        G = self._get_nx()  # Uses cached NX mirror
        if G.number_of_nodes() == 0:
            return

        try:
            degree_c = nx.degree_centrality(G)
            betweenness_c = nx.betweenness_centrality(G)

            for table in G.nodes:
                deg = round(degree_c.get(table, 0.0), 4)
                bet = round(betweenness_c.get(table, 0.0), 4)
                try:
                    self._mg.execute(
                        f"""MATCH (t:SAPTable:{self.tenant_label} {{table_name: $table}})
                           SET t.degree_centrality = $deg,
                               t.betweenness_centrality = $bet""",
                        params={"table": table, "deg": deg, "bet": bet},
                    )
                except Exception as e:
                    logger.debug(f"[Memgraph] centrality store failed for {table}: {e}")

            logger.info(
                f"[Memgraph] Centrality stored for {G.number_of_nodes()} nodes."
            )
        except Exception as e:
            logger.warning(f"[Memgraph] Centrality computation skipped: {e}")

    # ─── Traversal APIs ───────────────────────────────────────────────────────

    def traverse_graph(self, start_table: str, end_table: str) -> str:
        """
        Finds the shortest JOIN path using BFS on the NetworkX mirror.
        Returns a formatted SQL JOIN string - IDENTICAL output to GraphRAGManager.
        """
        start = start_table.upper()
        end = end_table.upper()
        G = self._get_nx()

        if start not in G.nodes:
            return f"Error: Table '{start}' is not in the Graph RAG schema."
        if end not in G.nodes:
            return f"Error: Table '{end}' is not in the Graph RAG schema."

        try:
            path = nx.shortest_path(G, source=start, target=end)
        except nx.NetworkXNoPath:
            return f"No direct join path found between {start} and {end}."

        if len(path) == 1:
            return f"No JOIN needed - query can be resolved entirely within {start}."

        lines = [f"Start at {path[0]}"]
        for i in range(len(path) - 1):
            src, tgt = path[i], path[i + 1]
            edge = G.get_edge_data(src, tgt)
            bridge = " ← CROSS-MODULE → " if edge["bridge_type"] == "cross_module" else " → "
            lines.append(
                f"{edge['condition']}{bridge}({src} → {tgt}) [{edge['cardinality']}]"
            )
        return "\n".join(lines)

    def find_path(self, start_table: str, end_table: str) -> Optional[List[str]]:
        """Returns the raw list of tables in the shortest path."""
        try:
            return nx.shortest_path(
                self._get_nx(),
                source=start_table.upper(),
                target=end_table.upper(),
            )
        except nx.NetworkXNoPath:
            return None

    def get_join_condition(self, table_a: str, table_b: str) -> Optional[str]:
        """Get the FK join condition between two directly connected tables."""
        edge = self._get_nx().get_edge_data(table_a.upper(), table_b.upper())
        return edge["condition"] if edge else None

    def get_subgraph_context(self, path: List[str]) -> Dict:
        """Returns rich metadata for a path - same shape as GraphRAGManager."""
        tables_in_path = []
        joins = []
        cross_module_bridges = []

        for i, table in enumerate(path):
            meta = self._node_meta.get(table, MemgraphNodeMeta("?", "?", "", []))
            tables_in_path.append({
                "table": table,
                "module": meta.module,
                "domain": meta.domain,
                "desc": meta.desc,
                "key_columns": meta.key_columns,
            })
            if i < len(path) - 1:
                edge = self._get_nx().get_edge_data(table, path[i + 1])
                if edge:
                    joins.append({
                        "from": table,
                        "to": path[i + 1],
                        "condition": edge["condition"],
                        "cardinality": edge["cardinality"],
                        "bridge_type": edge["bridge_type"],
                    })
                    if edge["bridge_type"] == "cross_module":
                        cross_module_bridges.append(f"{table} ↔ {path[i + 1]}")

        return {
            "path": path,
            "tables": tables_in_path,
            "joins": joins,
            "cross_module_bridges": cross_module_bridges,
            "is_cross_module": len(cross_module_bridges) > 0,
        }

    def get_neighbors(self, table: str, depth: int = 1) -> Dict[str, List[dict]]:
        """Get all tables reachable from `table` within `depth` hops."""
        table = table.upper()
        G = self._get_nx()
        if table not in G.nodes:
            return {}
        distances = nx.single_source_shortest_path_length(G, table, cutoff=depth)
        result = {}
        for neighbor, dist in distances.items():
            if neighbor == table:
                continue
            edge = G.get_edge_data(table, neighbor)
            meta = self._node_meta.get(neighbor, MemgraphNodeMeta("?", "?", "", []))
            result[neighbor] = [{
                "distance": dist,
                "module": meta.module,
                "domain": meta.domain,
                "join_condition": edge["condition"] if edge else "?",
                "cardinality": edge["cardinality"] if edge else "?",
                "bridge_type": edge["bridge_type"] if edge else "?",
            }]
        return result

    def get_all_tables(self) -> List[str]:
        """Return all tables in the graph."""
        return list(self._get_nx().nodes)

    def get_table_meta(self, table: str) -> Dict:
        """Return metadata for a table."""
        raw = self._node_meta.get(table.upper(), {})
        # Support both MemgraphNodeMeta (attribute access) and plain dict
        if isinstance(raw, MemgraphNodeMeta):
            m = raw
        else:
            m = MemgraphNodeMeta(
                module=raw.get("module", "?"),
                domain=raw.get("domain", "?"),
                desc=raw.get("desc", ""),
                key_columns=raw.get("key_columns", []),
            )
        return {
            "module": m.module,
            "domain": m.domain,
            "desc": m.desc,
            "key_columns": m.key_columns,
            "degree_centrality": m.degree_centrality,
            "betweenness_centrality": m.betweenness_centrality,
            "bridge_table": m.bridge_table,
        }

    def stats(self) -> dict:
        """Return graph statistics."""
        G = self._get_nx()
        return {
            "total_tables": G.number_of_nodes(),
            "total_relationships": G.number_of_edges(),
            "cross_module_bridges": sum(
                1 for u, v in G.edges
                if G.get_edge_data(u, v).get("bridge_type") == "cross_module"
            ),
            "modules": sorted(set(
                m.module if isinstance(m, MemgraphNodeMeta) else m.get("module", "?")
                for m in self._node_meta.values()
            )),
            "domains": sorted(set(
                m.domain if isinstance(m, MemgraphNodeMeta) else m.get("domain", "?")
                for m in self._node_meta.values()
            )),
            "memgraph_connected": self._is_connected,
        }

    def print_map(self):
        """Print a human-readable adjacency map grouped by module."""
        by_module: Dict[str, List[str]] = {}
        for table, meta in self._node_meta.items():
            mod = meta.module if isinstance(meta, MemgraphNodeMeta) else meta.get("module", "?")
            by_module.setdefault(mod, []).append(table)

        for mod in sorted(by_module):
            tables = sorted(by_module[mod])
            print(f"\n[{mod}] ({len(tables)} tables)")
            for t in tables:
                neighbors = list(self._get_nx().neighbors(t))
                print(f"  {t} → {', '.join(sorted(neighbors))}")

    # ─── Vector Search (Memgraph native - no separate ChromaDB needed) ──────────

    def search_tables_by_vector(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        namespace: str = "sap_tables",
    ) -> List[Dict]:
        """
        Memgraph native ANN vector search over table name + description embeddings.
        Replaces the ChromaDB "graph_table_context" collection.

        Requires Memgraph Enterprise with vector search enabled, OR use the
        open-source Memgraph + gqlalchemy combination.

        Returns top_k tables sorted by cosine similarity.
        """
        # TODO: Enable when Memgraph vector search is configured
        # cypher = """
        # CALL vector_search.search(
        #     $namespace, $query_embedding, $top_k
        # ) YIELD node, distance
        # RETURN node.table_name AS table, 1 - distance AS similarity
        # ORDER BY similarity DESC
        # """
        raise NotImplementedError(
            "[MemgraphGraphRAGManager] Vector search integration pending. "
            "Enable Memgraph Enterprise vector search or use Qdrant fallback."
        )

    def upsert_table_vector(
        self,
        table_name: str,
        embedding: List[float],
        namespace: str = "sap_tables",
    ):
        """Store a per-table embedding vector in Memgraph."""
        # TODO: Enable when Memgraph vector search is configured
        raise NotImplementedError(
            "[MemgraphGraphRAGManager] Vector search integration pending."
        )

    # ─── Centrality & Structural Properties (computed on NetworkX mirror) ────

    def compute_centrality(self) -> Dict[str, Dict[str, float]]:
        """
        Compute degree and betweenness centrality for all tables.
        Stores results in node metadata for graph embedding search.
        Call this after build_enterprise_schema_graph().
        """
        G = self._get_nx()
        degree = nx.degree_centrality(G)
        betweenness = nx.betweenness_centrality(G)

        # Identify bridge nodes (cross-module articulation points)
        bridges: Set[str] = set()
        for u, v in G.edges:
            if G.get_edge_data(u, v).get("bridge_type") == "cross_module":
                bridges.add(u)
                bridges.add(v)

        for table in G.nodes:
            if table in self._node_meta:
                self._node_meta[table].degree_centrality = degree.get(table, 0.0)
                self._node_meta[table].betweenness_centrality = betweenness.get(table, 0.0)
                self._node_meta[table].bridge_table = table in bridges

        return {
            table: {
                "degree_centrality": degree.get(table, 0.0),
                "betweenness_centrality": betweenness.get(table, 0.0),
                "is_bridge": table in bridges,
            }
            for table in G.nodes
        }

    # ─── All-Paths Explorer bridge ────────────────────────────────────────────

    def find_all_ranked_paths(
        self,
        start_table: str,
        end_table: str,
        max_depth: int = 5,
        top_k: int = 3,
    ) -> List[dict]:
        """
        Find and rank all JOIN paths - delegates to the existing
        AllPathsExplorer but uses the Memgraph-backed NetworkX mirror.
        """
        from app.core.graph_store import AllPathsExplorer
        explorer = AllPathsExplorer(self)  # passes self as GraphRAGManager-compatible
        return explorer.find_all_ranked_paths(start_table, end_table, max_depth, top_k)

    # ─── Ingestion from SAP DDIC (Production) ─────────────────────────────────

    def ingest_from_ddic_records(self, nodes: List[Dict], edges: List[Dict]):
        """
        Dynamically populates Memgraph from structured DDIC metadata records.
        This is the target of the DDIC Auto-Ingestion pipeline, allowing
        the system to absorb custom Z* and Y* tables seamlessly.
        """
        self._ensure_connected()
        if not self._mg:
            logger.error("[Memgraph] Cannot ingest DDIC records: Not connected.")
            return

        logger.info(f"[Memgraph] Ingesting {len(nodes)} DDIC tables and {len(edges)} DDIC FKs...")

        # Bulk Load Nodes
        for n in nodes:
            self._add_node(
                table=n["table_name"],
                module=n.get("module", "UNKNOWN"),
                domain=n.get("domain", "auto"),
                desc=n.get("description", ""),
                key_cols=n.get("key_columns", [])
            )

        # Bulk Load Edges
        for e in edges:
            self._add_edge(
                t1=e["src"],
                t2=e["tgt"],
                condition=e.get("condition", ""),
                cardinality=e.get("cardinality", "1:1"),
                bridge_type=e.get("bridge_type", "internal"),
                notes=e.get("notes", "")
            )

        # Rebuild NetworkX mirror locally
        self._build_nx_from_local_metadata()

        # Recompute centrality
        self._compute_and_store_centrality()

        logger.info(f"[Memgraph] DDIC Ingestion Complete. Total Nodes: {len(self._node_meta)}, Total Edges: {len(self._edge_meta)}")

    @classmethod
    def ingest_from_ddic(cls, memgraph_uri: str = "bolt://localhost:7687"):
        """
        Production-grade: auto-populate the graph from SAP DD08L (FK relationships)
        and T001/T001W/T024 (organizational tables).

        This replaces manual graph construction with an automated pipeline:
            SAP DDIC (DD08L) → transform → Memgraph

        TODO: Implement SAP RFC call to DD08L, transform FK metadata into
              Cypher MERGE statements, batch load into Memgraph.
        """
        raise NotImplementedError(
            "[MemgraphGraphRAGManager] DDIC auto-ingestion is a Phase roadmap item. "
            "For now, use build_enterprise_schema_graph() with manually curated nodes/edges."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatibility shim - swap GraphRAGManager → MemgraphGraphRAGManager
# ─────────────────────────────────────────────────────────────────────────────

def use_memgraph(
    uri: str = "bolt://localhost:7687",
    user: str = "",
    password: str = "",
    tenant_id: str = "default",
) -> type:
    """
    Call this at startup to replace the global GraphRAGManager with
    the Memgraph-backed version. Preserves all existing imports.

    Args:
        uri:      Memgraph bolt URI (default: bolt://localhost:7687)
        user:     Memgraph username (default: "" = unauthenticated)
        password: Memgraph password (default: "" = unauthenticated)
        tenant_id: Tenant to isolate the subgraph for (Phase M10).

    Usage (in app/core/__init__.py or app/main.py startup):
        from app.core.memgraph_adapter import use_memgraph
        mg = use_memgraph(uri=os.environ["MEMGRAPH_URI"], tenant_id="T100")
        print(mg.stats())
    """
    import app.core.graph_store as gs
    original_class = gs.__class__

    class MemgraphShim(MemgraphGraphRAGManager):
        """
        Thin shim that inherits the original class's method implementations
        via __getattr__ but delegates all graph operations to Memgraph.
        """
        def __init__(self, *args, **kwargs):
            # Pass load_on_init=False to avoid double-building
            kwargs.pop('uri', None)
            kwargs.pop('user', None)
            kwargs.pop('password', None)
            kwargs.pop('tenant_id', None)
            kwargs['load_on_init'] = False
            super().__init__(
                *args,
                uri=uri,
                user=user,
                password=password,
                tenant_id=tenant_id,
                **kwargs,
            )
            # Mirror the original graph's nodes and edges
            orig = original_class()
            for table, meta in orig._node_meta.items():
                self._node_meta[table] = MemgraphNodeMeta(
                    module=meta.get("module", "?"),
                    domain=meta.get("domain", "?"),
                    desc=meta.get("desc", ""),
                    key_columns=meta.get("key_columns", []),
                )
            for (t1, t2), meta in orig._edge_meta.items():
                self._edge_meta[(t1, t2)] = MemgraphEdgeMeta(
                    condition=meta.get("condition", ""),
                    cardinality=meta.get("cardinality", ""),
                    bridge_type=meta.get("bridge_type", "internal"),
                    notes=meta.get("notes", ""),
                )

    # Replace the module-level instance's class with the shim and initialize it
    gs.__class__ = MemgraphShim
    gs.__init__(uri=uri, user=user, password=password)
    logger.info("[Memgraph] graph_store replaced with Memgraph-backed shim.")
    return MemgraphShim
