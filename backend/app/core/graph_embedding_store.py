"""
graph_embedding_store.py — Phase 2: Graph Embeddings for Semantic Table Discovery
===================================================================================
Pillar 5½ (Graph Embeddings) — closes the loop between structural graph topology
and semantic vector search.

Three embedding layers over the NetworkX enterprise schema graph:

  Layer 1 — Node2Vec Structural Embeddings
    Walks on the FK relationship graph → Word2Vec → per-table 64-dim vector.
    Captures: structural role (hub/authority), cross-module bridges,
    domain-local centrality. Stored in ChromaDB collection "graph_node_embeddings".

  Layer 2 — Context-Rich Text Embeddings
    Each table's semantic vector encodes:
      table_name + DDIC description + module + domain + structural_role
      + top_5_neighbors + cross_module_bridge_flag + centrality_rank
    Stored in ChromaDB collection "graph_table_context".
    Uses all-MiniLM-L6-v2 (already loaded by vector_store.py).

  Layer 3 — Hybrid Search
    Query → Node2Vec approximate-ANN (cosine) + text semantic → score fusion
    → top-K tables with full structural explainability (why this table?).

Why this matters:
  Without graph embeddings:  "show me vendor payment terms" → LFA1, LFB1 only
  With graph embeddings:     also surfaces LFB5 (payment history), BSEG (paid items),
                             BSAK/BSIK (open/cleared), EKES (confirmation) —
                             tables that are structurally central to the vendor-payment
                             subgraph even if they don't mention "vendor" in their name.

Exports:
  graph_embedding_store : GraphEmbeddingStore  (singleton)
  init_graph_embeddings() : callable            — call once at startup
  search_graph_tables()  : public API           — orchestrator calls here
"""

from __future__ import annotations

import os
import math
import warnings
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from functools import lru_cache

import networkx as nx
import numpy as np
from node2vec import Node2Vec
from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import MinMaxScaler

# ChromaDB (already used by vector_store.py)
import chromadb

# Local imports
from app.core.graph_store import graph_store  # NetworkX graph singleton


# =============================================================================
# Configuration
# =============================================================================

GRAPH_EMBEDDING_DIM   = 64      # Node2Vec embedding dimension
NODE2VEC_WALKS        = 10      # Random walks per node
NODE2VEC_WALK_LEN     = 80      # Steps per walk
NODE2VEC_WINDOW        = 10      # Word2Vec context window
NODE2VEC_EPOCHS        = 10     # Word2Vec training epochs
NODE2VEC_P             = 1.0   # Return hyperparameter (Node2Vec)
NODE2VEC_Q             = 0.5   # In-out hyperparameter (Node2Vec favors breadth — cross-module discovery)

CHROMA_DB_PATH         = "./chroma_graph_db"
NODE_EMBEDDINGS_COL    = "graph_node_embeddings"   # Node2Vec structural vectors
TABLE_CONTEXT_COL      = "graph_table_context"     # Text + structural semantic vectors
TOP_K_STRUCTURAL       = 20      # Nodes to consider for context building
CROSS_MODULE_BRIDGE_PENALTY = 0.3  # Penalty for cross-module edges in centrality

# =============================================================================
# Data classes
# =============================================================================

@dataclass
class StructuralContext:
    """Structural metadata computed per table node."""
    table_name:            str
    degree:               int
    degree_centrality:    float
    betweenness_centrality: float
    closeness_centrality: float
    page_rank:            float
    is_cross_module_bridge: bool       # touches ≥2 domains
    neighbor_domains:      List[str]    # unique domains of neighboring nodes
    structural_role:      str          # "hub", "authority", "bridge", "leaf", "isolated"
    centrality_percentile: float        # 0–1 where 1 = most central
    cross_module_degree:  int          # edges that cross domain boundaries


@dataclass
class TableGraphContext:
    """Full context for a table node — structural + semantic."""
    table_name:      str
    description:     str
    module:          str
    domain:          str
    key_columns:     List[str]
    structural:      StructuralContext
    neighbors:       List[Dict[str, str]]   # [{table, edge_condition, domain}]
    cross_module_paths: int                 # how many cross-module paths this node enables


# =============================================================================
# Core class
# =============================================================================

class GraphEmbeddingStore:
    """
    Builds and queries graph structure + text embeddings over the SAP schema graph.

    Two ChromaDB collections:
      graph_node_embeddings : Node2Vec structural vectors (cosine similarity)
      graph_table_context    : text+structural semantic vectors (reranking source)

    Orchestrator调用路径:
      search_graph_tables(query, domain, top_k)
        → Node2Vec ANN search  (structural relevance)
        → text semantic search (description match)
        → score fusion (0.6 * structural + 0.4 * text)
        → return top-k with structural explainability
    """

    def __init__(
        self,
        db_path: str = CHROMA_DB_PATH,
        embedding_dim: int = GRAPH_EMBEDDING_DIM,
    ):
        self.G = graph_store.G                       # NetworkX graph
        
        # Convert _node_meta and _edge_meta objects to dicts for backward compatibility
        self._node_meta = {}
        for k, v in graph_store._node_meta.items():
            self._node_meta[k] = v if isinstance(v, dict) else (v.__dict__ if hasattr(v, '__dict__') else {})
            
        self._edge_meta = {}
        for k, v in graph_store._edge_meta.items():
            self._edge_meta[k] = v if isinstance(v, dict) else (v.__dict__ if hasattr(v, '__dict__') else {})

        self.embedding_dim = embedding_dim

        # --- ChromaDB client ---
        self.chroma_client = chromadb.PersistentClient(path=db_path)

        # --- Sentence Transformer (shared with VectorStoreManager) ---
        self.text_encoder = SentenceTransformer("all-MiniLM-L6-v2")

        # --- ChromaDB collections ---
        self._node_col = self.chroma_client.get_or_create_collection(
            name=NODE_EMBEDDINGS_COL,
            metadata={"hnsw:space": "cosine", "hnsw:M": 16, "efConstruction": 64},
        )
        self._context_col = self.chroma_client.get_or_create_collection(
            name=TABLE_CONTEXT_COL,
            metadata={"hnsw:space": "cosine", "hnsw:M": 16, "efConstruction": 64},
        )

        # --- Node2Vec model (lazy — populated on build) ---
        self._node2vec_model: Optional[Any] = None
        self._node_embeddings: Dict[str, np.ndarray] = {}   # table → np.ndarray

        # --- Structural metrics (lazy — populated on build) ---
        self._structural_ctx: Dict[str, StructuralContext] = {}

        # --- Pre-computed cross-module edges set ---
        self._cross_module_edges: set = self._detect_cross_module_edges()

        # --- Domain index map ---
        self._domain_tables: Dict[str, List[str]] = self._build_domain_index()

    # -------------------------------------------------------------------------
    # Initialization / Build
    # -------------------------------------------------------------------------

    def build(self, force: bool = False) -> "GraphEmbeddingStore":
        """
        Full pipeline: compute Node2Vec → structural metrics → context texts → ChromaDB.

        Safe to call repeatedly — will skip if collections already have data
        unless force=True.
        """
        node_count = self._node_col.count()
        if node_count > 0 and not force:
            print(f"[GraphEmbeddings] Collections already populated ({node_count} nodes). "
                  "Call build(force=True) to rebuild.")
            self._load_existing()
            return self

        print("[GraphEmbeddings] Building graph embeddings from scratch...")

        # Step 1: Compute structural metrics (needed for context texts + sorting)
        print("  [1/5] Computing structural metrics (centrality, bridges)...")
        self._compute_structural_metrics()

        # Step 2: Node2Vec walks → Word2Vec embeddings
        print(f"  [2/5] Node2Vec walks (p={NODE2VEC_P}, q={NODE2VEC_Q}, "
              f"walks={NODE2VEC_WALKS}, len={NODE2VEC_WALK_LEN})...")
        self._compute_node2vec()

        # Step 3: Build context-rich text for each table
        print("  [3/5] Building context-rich documents for semantic embedding...")
        context_docs = self._build_context_documents()

        # Step 4: Encode and store in ChromaDB
        print("  [4/5] Storing Node2Vec embeddings in ChromaDB...")
        self._index_node_embeddings()

        print("  [5/5] Storing context embeddings in ChromaDB...")
        self._index_context_embeddings(context_docs)

        print("[GraphEmbeddings] Build complete.")
        return self

    def _load_existing(self):
        """
        Reload structural metrics from in-memory graph (when ChromaDB is already
        populated but the process just started and needs to repopulate _structural_ctx).

        Also loads Node2Vec embeddings back from ChromaDB so that structural scoring
        is available without a full rebuild.
        """
        # Structural metrics are always computed fresh (lightweight — O(N+E) NetworkX ops)
        self._compute_structural_metrics()

        # Load Node2Vec embeddings from ChromaDB if not already populated
        if not self._node_embeddings and self._node_col.count() > 0:
            print("  [_load_existing] Restoring Node2Vec embeddings from ChromaDB...")
            stored = self._node_col.get(include=["metadatas", "embeddings"])
            if stored and stored.get("ids") is not None and stored.get("embeddings") is not None:
                for i, node_id in enumerate(stored["ids"]):
                    table = stored["metadatas"][i]["table"]
                    embedding = stored["embeddings"][i]
                    self._node_embeddings[table] = np.array(embedding, dtype=np.float32)

    # -------------------------------------------------------------------------
    # Step 1: Structural Metrics
    # -------------------------------------------------------------------------

    def _detect_cross_module_edges(self) -> set:
        """Find edges where source and target nodes belong to different domains."""
        cross_edges = set()
        for (u, v), meta in self._edge_meta.items():
            u_meta = self._node_meta.get(u, {})
            v_meta = self._node_meta.get(v, {})
            if u_meta.get("domain") != v_meta.get("domain"):
                cross_edges.add((u, v))
        return cross_edges

    def _build_domain_index(self) -> Dict[str, List[str]]:
        """Map each domain → list of its tables."""
        index: Dict[str, List[str]] = {}
        for table, meta in self._node_meta.items():
            dom = meta.get("domain", "unknown")
            index.setdefault(dom, []).append(table)
        return index

    def _compute_structural_metrics(self):
        """
        Compute per-node: degree, centrality metrics, cross-module flags,
        structural role classification.
        """
        n = self.G.number_of_nodes()
        if n == 0:
            return

        # Centrality computations (on undirected graph)
        deg        = dict(self.G.degree())
        dc         = nx.degree_centrality(self.G)
        bc         = nx.betweenness_centrality(self.G)
        cc         = nx.closeness_centrality(self.G)
        pr         = nx.pagerank(self.G)

        # Normalize betweenness to [0,1] (already is, but guard)
        bc_max = max(bc.values()) if bc else 1.0
        if bc_max == 0:
            bc_max = 1.0

        # Per-node percentile of degree centrality
        dc_values = sorted(dc.values())
        dc_percentile = lambda v: (
            sorted(dc_values).index(v) / max(len(dc_values) - 1, 1)
        )

        cross_degree = {}
        for node in self.G.nodes():
            cross_degree[node] = sum(
                1 for (u, v) in self.G.edges(node)
                if (u, v) in self._cross_module_edges or (v, u) in self._cross_module_edges
            )

        for node in self.G.nodes():
            node_meta = self._node_meta.get(node, {})
            neighbors = list(self.G.neighbors(node))
            neighbor_domains = list(set(
                self._node_meta.get(n, {}).get("domain", "unknown")
                for n in neighbors
            ))
            is_bridge = cross_degree[node] > 0 and len(neighbor_domains) > 1

            # Classify structural role
            d = deg[node]
            cross_d = cross_degree[node]
            if d <= 2 and not is_bridge:
                role = "leaf"
            elif d >= 10 and cross_d >= 2:
                role = "hub"           # highly connected, cross-domain
            elif is_bridge and cross_d >= 1:
                role = "bridge"        # cross-module connector
            elif d >= 5 and cross_d == 0:
                role = "authority"     # domain-local hub
            elif d == 0:
                role = "isolated"
            else:
                role = "transit"       # regular node

            self._structural_ctx[node] = StructuralContext(
                table_name              = node,
                degree                  = d,
                degree_centrality       = dc.get(node, 0.0),
                betweenness_centrality  = bc.get(node, 0.0) / bc_max,
                closeness_centrality    = cc.get(node, 0.0),
                page_rank               = pr.get(node, 0.0),
                is_cross_module_bridge  = is_bridge,
                neighbor_domains        = neighbor_domains,
                structural_role         = role,
                centrality_percentile   = dc_percentile(dc.get(node, 0.0)),
                cross_module_degree     = cross_d,
            )

    # -------------------------------------------------------------------------
    # Step 2: Node2Vec
    # -------------------------------------------------------------------------

    def _compute_node2vec(self):
        """Run Node2Vec random walks → Word2Vec → per-node embeddings."""
        if self.G.number_of_nodes() == 0:
            return

        try:
            # Suppress node2vec verbose output
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                n2v = Node2Vec(
                    self.G,
                    dimensions=self.embedding_dim,
                    walk_length=NODE2VEC_WALK_LEN,
                    num_walks=NODE2VEC_WALKS,
                    p=NODE2VEC_P,
                    q=NODE2VEC_Q,
                    workers=1,           # Single-threaded for stability
                    quiet=True,
                    seed=42,
                )
                model = n2v.fit(window=NODE2VEC_WINDOW, epochs=NODE2VEC_EPOCHS, seed=42)
        except Exception as e:
            print(f"[GraphEmbeddings] Node2Vec failed: {e}. Falling back to identity+centrality vectors.")
            model = None

        self._node2vec_model = model

        if model is not None:
            for node in self.G.nodes():
                try:
                    vec = model.wv[node]
                    self._node_embeddings[node] = vec
                except KeyError:
                    # Node not in vocabulary (should not happen)
                    self._node_embeddings[node] = self._fallback_embedding(node)
        else:
            # Fallback: identity vector + centrality features
            for node in self.G.nodes():
                self._node_embeddings[node] = self._fallback_embedding(node)

    def _fallback_embedding(self, node: str) -> np.ndarray:
        """
        Fallback when Node2Vec fails: combine degree centrality, betweenness,
        page-rank, and a hash-based component into a dense vector.
        """
        ctx = self._structural_ctx.get(node)
        if ctx is None:
            return np.zeros(self.embedding_dim)

        base = np.array([
            ctx.degree_centrality,
            ctx.betweenness_centrality,
            ctx.closeness_centrality,
            ctx.page_rank,
            1.0 if ctx.is_cross_module_bridge else 0.0,
            ctx.centrality_percentile,
            ctx.cross_module_degree / max(self.G.number_of_edges(), 1),
            float(ctx.degree) / max(self.G.number_of_nodes() - 1, 1),
        ])

        # Pad to embedding_dim using a deterministic hash projection
        hash_comp = self._hash_to_vec(node, self.embedding_dim - len(base))
        vec = np.concatenate([base, hash_comp])

        # L2-normalize to match Node2Vec output convention
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    @staticmethod
    def _hash_to_vec(s: str, dim: int) -> np.ndarray:
        """Deterministic pseudo-random vector from a string hash (for fallback)."""
        import hashlib
        h = hashlib.sha256(s.encode()).digest()
        # Use first `dim` bytes, project to [-1, 1]
        arr = np.array([b for b in h[:dim]], dtype=np.float32)
        arr = (arr / 127.5) - 1.0
        if len(arr) < dim:
            arr = np.pad(arr, (0, dim - len(arr)))
        return arr

    # -------------------------------------------------------------------------
    # Step 3: Context Documents
    # -------------------------------------------------------------------------

    def _build_context_documents(self) -> Dict[str, Dict]:
        """
        Build rich text documents for each table node.
        Document = structural role + description + neighbors + domain context.
        """
        docs: Dict[str, Dict] = {}
        all_tables = list(self.G.nodes())

        # Sort by centrality so we can add "rank among N" context
        sorted_by_centrality = sorted(
            all_tables,
            key=lambda t: self._structural_ctx.get(t, StructuralContext(t, 0, 0, 0, 0, 0, False, [], "leaf", 0, 0)).degree_centrality,
            reverse=True,
        )
        centrality_rank = {t: i / max(len(sorted_by_centrality) - 1, 1)
                           for i, t in enumerate(sorted_by_centrality)}

        for table in all_tables:
            meta = self._node_meta.get(table, {})
            ctx  = self._structural_ctx.get(table)

            # Neighbor details
            neighbors = []
            for neighbor in self.G.neighbors(table):
                n_meta = self._node_meta.get(neighbor, {})
                edge_data = self.G.get_edge_data(table, neighbor) or {}
                neighbors.append({
                    "table":   neighbor,
                    "domain":  n_meta.get("domain", ""),
                    "module":  n_meta.get("module", ""),
                    "condition": edge_data.get("condition", ""),
                    "cardinality": edge_data.get("cardinality", "1:1"),
                    "bridge_type": edge_data.get("bridge_type", "internal"),
                })

            # Cross-module paths enabled by this node
            cross_module_paths = sum(
                1 for n in neighbors
                if n["domain"] != meta.get("domain", "") and n["domain"] != ""
            )

            # Build document text
            neighbor_str = "; ".join(
                f"{n['table']}({n['domain']}, {n['cardinality']})"
                for n in sorted(neighbors, key=lambda x: x["table"])[:6]
            )
            cross_str = "CROSS-MODULE BRIDGE" if (ctx and ctx.is_cross_module_bridge) else "DOMAIN-LOCAL"

            doc_text = (
                f"Table {table} | Domain: {meta.get('domain', '')} | "
                f"Module: {meta.get('module', '')} | "
                f"Role: {ctx.structural_role if ctx else 'unknown'} [{cross_str}] | "
                f"Centrality: {f'{ctx.centrality_percentile:.2f}' if ctx else 'n/a'} percentile | "
                f"Cross-module connections: {cross_module_paths} | "
                f"Description: {meta.get('desc', meta.get('description', ''))} | "
                f"Key columns: {', '.join(meta.get('key_columns', []))} | "
                f"Top neighbors: {neighbor_str}"
            )

            docs[table] = {
                "document":       doc_text,
                "table":          table,
                "domain":         meta.get("domain", ""),
                "module":         meta.get("module", ""),
                "structural_role": ctx.structural_role if ctx else "unknown",
                "is_cross_module_bridge": ctx.is_cross_module_bridge if ctx else False,
                "centrality_percentile": ctx.centrality_percentile if ctx else 0.0,
                "degree":         ctx.degree if ctx else 0,
                "neighbors":      neighbors[:6],
                "cross_module_paths": cross_module_paths,
            }

        return docs

    # -------------------------------------------------------------------------
    # Step 4 & 5: ChromaDB Indexing
    # -------------------------------------------------------------------------

    def _index_node_embeddings(self):
        """Store Node2Vec / fallback vectors in ChromaDB."""
        existing_nodes = self._node_col.get()
        if existing_nodes and existing_nodes.get("ids"):
            self._node_col.delete(ids=existing_nodes["ids"])

        ids, vectors, metas, docs = [], [], [], []
        for table, embedding in self._node_embeddings.items():
            ctx = self._structural_ctx.get(table)
            meta = self._node_meta.get(table, {})
            ids.append(f"node_{table}")
            vectors.append(embedding.tolist())
            docs.append(f"Graph structural embedding for {table}")
            metas.append({
                "table":                table,
                "domain":               meta.get("domain", ""),
                "structural_role":      ctx.structural_role if ctx else "unknown",
                "is_cross_module_bridge": ctx.is_cross_module_bridge if ctx else False,
                "degree":               ctx.degree if ctx else 0,
                "centrality_percentile": ctx.centrality_percentile if ctx else 0.0,
            })

        if ids:
            self._node_col.upsert(ids=ids, embeddings=vectors, metadatas=metas, documents=docs)
            print(f"  [Node2Vec] Indexed {len(ids)} table embeddings.")

    def _index_context_embeddings(self, context_docs: Dict[str, Dict]):
        """Store context-rich text embeddings in ChromaDB."""
        existing_ctx = self._context_col.get()
        if existing_ctx and existing_ctx.get("ids"):
            self._context_col.delete(ids=existing_ctx["ids"])

        ids, vectors, metas, docs = [], [], [], []
        for table, cdoc in context_docs.items():
            ids.append(f"context_{table}")
            vector = self.text_encoder.encode(cdoc["document"]).tolist()
            vectors.append(vector)
            docs.append(cdoc["document"])
            metas.append({
                "table":                 table,
                "domain":                cdoc["domain"],
                "module":                cdoc["module"],
                "structural_role":       cdoc["structural_role"],
                "is_cross_module_bridge": cdoc["is_cross_module_bridge"],
                "centrality_percentile": cdoc["centrality_percentile"],
                "cross_module_paths":    cdoc["cross_module_paths"],
            })

        if ids:
            self._context_col.upsert(ids=ids, embeddings=vectors, metadatas=metas, documents=docs)
            print(f"  [Context] Indexed {len(ids)} context documents.")

    # -------------------------------------------------------------------------
    # Public API: Hybrid Search
    # -------------------------------------------------------------------------

    def search_graph_tables(
        self,
        query: str,
        domain: str = "auto",
        top_k: int = 5,
        structural_weight: float = 0.6,
        text_weight: float = 0.4,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search: Node2Vec structural similarity + text semantic similarity.

        Args:
            query:            Natural language query (e.g., "vendor payment history")
            domain:           Filter by domain (default: auto — all domains)
            top_k:            Return top-k results
            structural_weight: Weight for structural neighborhood coherence score (0–1)
            text_weight:       Weight for text semantic similarity score (0–1)

        Returns:
            List of dicts with:
              table, domain, module, structural_role, is_cross_module_bridge,
              centrality_percentile, cross_module_paths, degree,
              composite_score, structural_score, text_score, rank
        """
        # Normalize weights
        total = structural_weight + text_weight
        sw = structural_weight / total
        tw = text_weight / total

        # ── Step 1: Text semantic search to get candidate tables ───────────
        query_vec_text = self.text_encoder.encode(query).tolist()

        domain_filter = None
        if domain and domain not in ("auto", "cross_module", "transactional"):
            domain_filter = {"domain": domain}

        text_results = self._context_col.query(
            query_embeddings=[query_vec_text],
            n_results=TOP_K_STRUCTURAL,
            where=domain_filter,
        )

        if not text_results or not text_results.get("documents"):
            return []

        candidate_tables = [m["table"] for m in text_results["metadatas"][0]]

        # ── Step 2: Structural neighborhood coherence scores ─────────────────
        # For each candidate table: compare its embedding to the mean of its
        # neighbor embeddings in the graph. High coherence = table is well-
        # integrated into its domain subgraph. Low coherence = outlier/bridge.
        structural_scores: Dict[str, float] = {}
        if self._node_embeddings and self.G:
            # Structural score = centrality composite using percentile ranks:
            #   - degree centrality percentile (40%): rank in sorted degree-distribution
            #   - betweenness centrality percentile (30%): rank in sorted betweenness-dist
            #   - cross-module bridge bonus (30%): extra weight for cross-domain nodes
            #
            # Percentiles ensure scores spread across [0, 1] regardless of graph size.
            all_ctx = list(self._structural_ctx.values())
            if not all_ctx:
                structural_scores = {t: 0.0 for t in candidate_tables}
            else:
                # Precompute percentile ranks
                sorted_dc  = sorted(set(c.degree_centrality        for c in all_ctx))
                sorted_bc  = sorted(set(c.betweenness_centrality  for c in all_ctx))

                def pct_rank(val: float, sorted_vals: List[float]) -> float:
                    if not sorted_vals:
                        return 0.0
                    # Binary search index / len → percentile
                    idx = 0
                    lo, hi = 0, len(sorted_vals) - 1
                    while lo <= hi:
                        mid = (lo + hi) // 2
                        if sorted_vals[mid] <= val:
                            idx = mid + 1
                            lo  = mid + 1
                        else:
                            hi  = mid - 1
                    return idx / len(sorted_vals)

                for table in candidate_tables:
                    ctx = self._structural_ctx.get(table)
                    if ctx is None:
                        structural_scores[table] = 0.0
                        continue
                    # Degree percentile: rank / count (0.5 = median)
                    dc_pct = pct_rank(ctx.degree_centrality,        sorted_dc)
                    # Betweenness percentile
                    bc_pct = pct_rank(ctx.betweenness_centrality,   sorted_bc)
                    # Bridge bonus: +0.5 if cross-module, +0.25 if isolated in-domain
                    bridge_bonus = 0.5 if ctx.is_cross_module_bridge else (
                        0.25 if ctx.degree == 0 else 0.0)
                    # Cross-module degree: fraction of total cross-module edges
                    n_edges = self.G.number_of_edges()
                    cross_pct = min(ctx.cross_module_degree / max(1, n_edges * 0.08), 1.0)

                    raw = (0.35 * dc_pct
                         + 0.25 * bc_pct
                         + 0.25 * bridge_bonus
                         + 0.15 * cross_pct)
                    structural_scores[table] = round(min(1.0, raw), 4)

        # ── Step 3: Text similarity scores (from ChromaDB L2 distance) ────
        text_scores: Dict[str, float] = {}
        for i, meta in enumerate(text_results["metadatas"][0]):
            table = meta["table"]
            dist  = text_results["distances"][0][i] if text_results.get("distances") else 0.0
            text_scores[table] = 1.0 / (1.0 + dist)

        # ── Step 4: Composite fusion + metadata enrichment ─────────────────
        scored: List[Dict[str, Any]] = []
        for table in candidate_tables:
            ss = structural_scores.get(table, 0.0)
            ts = text_scores.get(table, 0.0)
            composite = sw * ss + tw * ts

            ctx_doc = self._context_col.get(
                where={"table": table},
                include=["metadatas", "documents"],
            )
            meta = {}
            doc  = ""
            if ctx_doc and ctx_doc.get("metadatas"):
                meta = ctx_doc["metadatas"][0]
                doc  = (ctx_doc["documents"] or [""])[0]

            scored.append({
                "table":                    table,
                "domain":                   meta.get("domain", ""),
                "module":                   meta.get("module", ""),
                "structural_role":          meta.get("structural_role", ""),
                "is_cross_module_bridge":   meta.get("is_cross_module_bridge", False),
                "centrality_percentile":    meta.get("centrality_percentile", 0.0),
                "cross_module_paths":       meta.get("cross_module_paths", 0),
                "degree":                   meta.get("degree", 0),
                "description":              doc,
                "composite_score":          round(composite, 4),
                "structural_score":         round(ss, 4),
                "text_score":             round(ts, 4),
            })

        # Sort by composite score descending, add rank
        scored.sort(key=lambda x: x["composite_score"], reverse=True)
        for i, row in enumerate(scored):
            row["rank"] = i + 1

        return scored[:top_k]

    # -------------------------------------------------------------------------
    # Utility: Get full structural context for a table
    # -------------------------------------------------------------------------

    def get_structural_context(self, table: str) -> Optional[TableGraphContext]:
        """Return full structural + semantic context for a specific table."""
        table = table.upper()
        if table not in self.G.nodes():
            return None

        meta = self._node_meta.get(table, {})
        ctx  = self._structural_ctx.get(table)

        neighbors = []
        for neighbor in self.G.neighbors(table):
            n_meta = self._node_meta.get(neighbor, {})
            edge_data = self.G.get_edge_data(table, neighbor) or {}
            neighbors.append({
                "table":       neighbor,
                "domain":      n_meta.get("domain", ""),
                "condition":   edge_data.get("condition", ""),
                "cardinality": edge_data.get("cardinality", "1:1"),
                "bridge_type": edge_data.get("bridge_type", "internal"),
            })

        cross_module_paths = sum(
            1 for n in neighbors if n["domain"] != meta.get("domain", "")
        )

        if ctx is None:
            return None

        return TableGraphContext(
            table_name          = table,
            description         = meta.get("desc", meta.get("description", "")),
            module              = meta.get("module", ""),
            domain              = meta.get("domain", ""),
            key_columns         = meta.get("key_columns", []),
            structural          = ctx,
            neighbors           = neighbors,
            cross_module_paths  = cross_module_paths,
        )

    # -------------------------------------------------------------------------
    # Utility: Tables by domain
    # -------------------------------------------------------------------------

    def get_tables_by_domain(self, domain: str) -> List[str]:
        """Return all tables in a given domain."""
        return self._domain_tables.get(domain, [])

    def get_cross_module_bridges(self) -> List[str]:
        """Return all tables that are cross-module bridges."""
        return [
            t for t, ctx in self._structural_ctx.items()
            if ctx.is_cross_module_bridge
        ]

    def get_domain_graph_summary(self) -> Dict[str, Dict]:
        """
        Return per-domain summary: table count, bridge count, avg centrality,
        top-3 most central tables.
        """
        summary: Dict[str, Dict] = {}
        for domain, tables in self._domain_tables.items():
            if not tables:
                continue
            centralities = [(t, self._structural_ctx.get(t, StructuralContext(t, 0, 0, 0, 0, 0, False, [], "leaf", 0, 0)).centrality_percentile) for t in tables]
            centralities.sort(key=lambda x: x[1], reverse=True)
            bridges = [t for t in tables if self._structural_ctx.get(t, StructuralContext(t, 0, 0, 0, 0, 0, False, [], "leaf", 0, 0)).is_cross_module_bridge]
            avg_cent = sum(c for _, c in centralities) / len(centralities) if centralities else 0
            summary[domain] = {
                "table_count":        len(tables),
                "bridge_count":       len(bridges),
                "avg_centrality":     round(avg_cent, 4),
                "top_3_central":      [t for t, _ in centralities[:3]],
            }
        return summary


# =============================================================================
# Singleton + Init
# =============================================================================

graph_embedding_store = GraphEmbeddingStore()

def init_graph_embeddings(force: bool = False) -> GraphEmbeddingStore:
    """
    Call at application startup (before the orchestrator handles requests).

    Args:
        force: Rebuild embeddings even if collections are already populated.

    Returns:
        The singleton GraphEmbeddingStore instance.
    """
    return graph_embedding_store.build(force=force)


# =============================================================================
# CLI / Test
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Graph Embedding Store — Build & Test")
    print("=" * 60)

    init_graph_embeddings(force=False)

    print("\n--- Domain Graph Summary ---")
    summary = graph_embedding_store.get_domain_graph_summary()
    for domain, info in sorted(summary.items()):
        print(f"  {domain:30s} tables={info['table_count']:3d}  "
              f"bridges={info['bridge_count']:2d}  "
              f"avg_cent={info['avg_centrality']:.3f}  "
              f"top: {', '.join(info['top_3_central'][:2])}")

    print("\n--- Cross-Module Bridges ---")
    bridges = graph_embedding_store.get_cross_module_bridges()
    print(f"  {len(bridges)} bridges: {bridges[:10]}")

    print("\n--- Test Queries ---")
    test_queries = [
        "vendor payment terms and bank details",
        "material stock and warehouse quantities",
        "purchase order delivery schedule",
        "customer sales area and pricing",
        "quality inspection results for materials",
    ]
    for q in test_queries:
        results = graph_embedding_store.search_graph_tables(q, top_k=5)
        top = results[0] if results else None
        print(f"\n  Query: {q}")
        if top:
            print(f"    #1: {top['table']} [{top['domain']}] "
                  f"role={top['structural_role']} "
                  f"bridge={top['is_cross_module_bridge']} "
                  f"score={top['composite_score']:.3f} "
                  f"(struct={top['structural_score']:.3f}, text={top['text_score']:.3f})")
        else:
            print("    (no results)")
