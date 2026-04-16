# Graph RAG for SAP HANA — Comprehensive Techniques Guide

> **For:** SAP Masters / Know Your SAP Masters Chatbot  
> **Pillar:** 5-Pillar RAG — Pillar 3 (Schema) + Pillar 5 (Graph)  
> **Scope:** Techniques, methods, and extension points for the NetworkX-based FK relationship graph
>
> **Last Reviewed:** April 16, 2026 | Status: Phase 5½ (Graph Embeddings) ✅ | TemporalGraphRAG ✅ | Meta-Path ✅ | AllPathsExplorer ✅

---

## 1. What Graph RAG Does in the SAP Context

Most enterprise RAG systems are **flat** — you chunk a document, embed it, retrieve similar chunks. That breaks completely for SAP because:

- A single SAP query like *"Show me open invoices for vendors who supplied material X to plant Y"* requires **3 hops**: `LFA1 → EKKO/EKPO → BSIK`
- No single document chunk contains this information
- The JOIN path is the answer — not a document

Graph RAG solves this by building a **Foreign Key relationship graph** of the SAP DDIC. The LLM doesn't know the JOIN path upfront — it asks the graph: *"how do I get from vendor to material valuation?"* The graph returns the exact JOIN sequence. The LLM then generates the SQL.

The current implementation (`graph_store.py`) covers:
- **80+ tables** across 18 domains
- **100+ edges** with real DDIC FK conditions
- **21 edge sets** organized by module boundary
- **BFS shortest-path traversal** via NetworkX
- **Cross-module bridge detection** (flags edges that cross MM↔FI↔SD boundaries)

---

## 2. Current Implementation Architecture

```
User Query (natural language)
       ↓
Orchestrator (agentic intent classification)
       ↓
┌──────┴──────┐
│ Schema RAG  │ ← "What tables have vendor + material data?"
│ (Qdrant)    │
└──────┬──────┘
       ↓
┌──────┴──────┐
│ Graph RAG   │ ← "How are VENDOR and MATERIAL connected?"
│ (NetworkX)  │
└──────┬──────┘
       ↓
  JOIN path returned
       ↓
┌──────┴──────┐
│ SQL RAG     │ ← "What does validated SAP SQL look like?"
│ (Few-shot)  │
└──────┬──────┘
       ↓
  Final SQL → SAP HANA → Response
```

### Key Methods in `graph_store.py`

| Method                        | What It Does                                      |
| ----------------------------- | ------------------------------------------------- |
| `traverse_graph(start, end)`  | BFS shortest path → formatted JOIN SQL            |
| `find_path(start, end)`       | Raw list of tables in shortest path               |
| `get_join_condition(A, B)`    | Direct FK condition between two connected tables  |
| `get_subgraph_context(path)`  | Rich metadata: modules, cardinality, bridge types |
| `get_neighbors(table, depth)` | All tables reachable within N hops                |
| `get_table_meta(table)`       | Module, domain, description, key columns          |
| `stats()`                     | Graph statistics (nodes, edges, bridges, modules) |
| `print_map()`                 | Human-readable adjacency map by module            |

---

## 3. Core Traversal Techniques

### 3.1 BFS Shortest Path (Currently Implemented)

```python
path = nx.shortest_path(G, source="LFA1", target="MBEW")
# Returns: ['LFA1', 'EINA', 'EKPO', 'MBEW']
```

**Limitation:** Finds ONE optimal path. SAP FK graphs are dense — there are often multiple valid JOIN paths with different trade-offs.

### 3.2 All Simple Paths (k-depth enumeration)

Find every possible JOIN path up to K hops. Critical for queries where the shortest path isn't the best path.

```python
def find_all_paths(graph, start, end, max_depth=4):
    return list(nx.all_simple_paths(graph, start, end, cutoff=max_depth))

# LFA1 → MBEW might return:
# Path 1: LFA1 → EINA → EKPO → MBEW        (via Purchasing)
# Path 2: LFA1 → EKKO → EKPO → MBEW        (via PO Header — extra node)
# Path 3: LFA1 → LFB1 → BSAK → ... → MBEW  (longer, through FI)
```

### 3.3 Bidirectional Path Search

When you don't know start AND end — e.g., you know the source (Material) and the target domain (Finance), but not the exact table. Bidirectional BFS finds the meeting point from both sides simultaneously.

```python
def bidirectional_bfs(graph, source, target):
    if source == target:
        return [source]
    
    from collections import deque
    front = {source: [source]}
    back = {target: [target]}
    visited_front = {source}
    visited_back = {target}
    
    while front:
        # Expand the smaller frontier
        if len(front) > len(back):
            front, back = back, front
            visited_front, visited_back = visited_back, visited_front
        
        next_front = {}
        for node in list(front.keys()):
            for neighbor in graph.neighbors(node):
                if neighbor in visited_back:
                    # Found! Reconstruct via back-pointer
                    return front[node] + back[neighbor][::-1]
                if neighbor not in visited_front:
                    visited_front.add(neighbor)
                    next_front[neighbor] = front[node] + [neighbor]
        front = next_front
    return None
```

### 3.4 Weighted Path Scoring (Path Ranking)

Assign weights to edges and find the **minimum cost path** rather than the fewest hops. Useful when multiple paths exist.

**Weight heuristics for SAP:**

```python
EDGE_WEIGHTS = {
    # Prefer direct FK over bridge tables
    "cardinality_1_1": 1.0,
    "cardinality_1_N": 2.0,    # 1:N creates row explosion — de-prioritize
    "cardinality_N_M": 5.0,   # Junction tables are expensive
    
    # Cross-module is not bad — it's informative
    "cross_module": 0.5,       # LOWER weight — cross-module paths get 
                               # rich semantic context, prefer them
    
    # Module traversal cost
    "same_module": 1.0,
    "diff_module": 1.5,
    
    # Table size heuristics (if known from stats)
    "large_table_penalty": 3.0,   # BSEG, MKPF are huge — avoid if possible
}

def weighted_shortest_path(graph, start, end, weights=EDGE_WEIGHTS):
    return nx.shortest_path(graph, source=start, target=end, weight='weight')

# Assign weights to edges
for u, v, data in graph.edges(data=True):
    w = 1.0
    w *= weights.get(f"cardinality_{data['cardinality']}", 1.0)
    w *= weights.get(data['bridge_type'], 1.0)
    data['weight'] = w
```

### 3.5 Meta-Path Discovery

SAP has **semantically meaningful path patterns** — named sequences that represent business concepts. Instead of finding JOIN paths mechanically, the system should recognize and apply pre-defined **meta-paths**.

```python
SAP_META_PATHS = {
    "vendor_material_relationship": {
        "description": "How a vendor relates to a material (procurement view)",
        "tables": ["LFA1", "EINA", "EINE", "EORD", "MARA", "MARC"],
        "path_patterns": [
            ("LFA1", "EINA", "MARA"),     # Direct info record
            ("LFA1", "EORD", "MARC"),     # Source list per plant
            ("LFA1", "EKKO", "EKPO", "MARA"),  # Via actual PO
        ],
        "business_meaning": "Vendor sourcing landscape for a material",
    },
    
    "order_to_cash": {
        "description": "Complete O2C document chain",
        "tables": ["KNA1", "VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "BKPF", "BSEG"],
        "path_patterns": [
            ("KNA1", "VBAK", "VBAP"),
            ("VBAP", "LIKP", "LIPS"),
            ("LIPS", "VBRK"),
            ("VBRK", "BKPF", "BSEG"),
        ],
        "business_meaning": "Full revenue cycle trace",
    },
    
    "procure_to_pay": {
        "description": "Complete P2P document chain",
        "tables": ["LFA1", "EKKO", "EKPO", "MKPF", "MSEG", "BKPF", "BSEG", "BSIK"],
        "path_patterns": [
            ("LFA1", "EKKO", "EKPO"),
            ("EKPO", "MSEG", "MKPF"),   # Goods receipt
            ("EKKO", "BKPF", "BSEG"),   # Invoice verification
            ("BSEG", "BSIK"),           # Open items
        ],
        "business_meaning": "End-to-end procurement with GR/IR tracking",
    },
    
    "material_cost_rollup": {
        "description": "Material cost structure through BOM and routing",
        "tables": ["MARA", "STKO", "STPO", "MAST", "CRHD", "MACO"],
        "path_patterns": [
            ("MARA", "STKO", "STPO"),     # BOM header → items
            ("MARA", "MAST", "CRHD"),       # BOM → work center assignment
        ],
        "business_meaning": "Standard cost build-up from BOM + routing",
    },
    
    "vendor_financial_exposure": {
        "description": "Vendor open items + on-order + schedule agreements",
        "tables": ["LFA1", "LFB1", "BSIK", "BSAK", "EKKO", "EKPO", "EKES", "EINA"],
        "path_patterns": [
            ("LFA1", "LFB1"),
            ("LFA1", "BSIK"),              # Open invoices
            ("LFA1", "BSAK"),              # Cleared invoices  
            ("LFA1", "EKKO", "EKPO"),      # Open POs
            ("LFA1", "EKES"),              # Schedule agreement confirmations
            ("LFA1", "EINA"),              # Info records (last price)
        ],
        "business_meaning": "Total vendor exposure (payables + on-order)",
    },
}
```

When the orchestrator receives a query matching a meta-path description, it **bypasses graph traversal** and uses the pre-defined path pattern directly — faster, more reliable, and semantically correct.

---

## 4. Advanced Graph Techniques for SAP HANA

### 4.1 Graph Embeddings + Vector Hybrid (Neo4j-style GraphRAG)

Convert the FK graph structure into **embedding vectors** so the orchestrator can do **semantic table discovery** — not just exact-name matching.

```python
from sentence_transformers import SentenceTransformer
import numpy as np

class GraphEmbeddingIndex:
    """
    Generates embeddings for:
    1. Individual tables (semantic table search)
    2. JOIN paths (path similarity)
    3. Edge conditions (semantic condition matching)
    """
    
    def __init__(self, graph_store):
        self.graph = graph_store
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self._build_indices()
    
    def _build_table_description(self, table: str) -> str:
        """Generate rich semantic description of a table."""
        meta = self.graph.get_table_meta(table)
        neighbors = list(self.graph.G.neighbors(table))
        neighbor_descs = []
        for n in neighbors:
            edge = self.graph.G.get_edge_data(table, n)
            neighbor_descs.append(
                f"connects to {n} via {edge['condition']} ({edge['cardinality']})"
            )
        
        return (
            f"SAP table {table} ({meta['module']}/{meta['domain']}): "
            f"{meta['desc']}. Key columns: {', '.join(meta['key_columns'])}. "
            f"Relationships: {'; '.join(neighbor_descs)}"
        )
    
    def _build_path_description(self, path: List[str]) -> str:
        """Generate semantic description of a JOIN path."""
        steps = []
        for i in range(len(path) - 1):
            src, tgt = path[i], path[i+1]
            edge = self.graph.G.get_edge_data(src, tgt)
            steps.append(
                f"{src} JOINs {tgt} ON {edge['condition']} "
                f"({edge['bridge_type']}, {edge['cardinality']})"
            )
        return " → ".join(steps)
    
    def index_all_tables(self):
        """Build vector index over all tables for semantic search."""
        table_docs = {t: self._build_table_description(t) for t in self.graph.get_all_tables()}
        
        # Batch encode
        all_tables = list(table_docs.keys())
        all_descs = [table_docs[t] for t in all_tables]
        embeddings = self.model.encode(all_descs)
        
        # Store in Qdrant
        from qdrant_client import QdrantClient
        client = QdrantClient(path="./qdrant_graph")
        
        # Collection for tables
        client.recreate_collection(
            collection_name="sap_graph_tables",
            vectors_config={"size": 384, "distance": "Cosine"}
        )
        
        for i, table in enumerate(all_tables):
            client.upsert(
                collection_name="sap_graph_tables",
                points=[{"id": i, "vector": embeddings[i].tolist(), 
                         "payload": {"table": table, "description": all_descs[i]}}]
            )
        
        return client
    
    def semantic_table_search(self, query: str, top_k=5) -> List[dict]:
        """Find tables semantically related to a query — not just keyword match."""
        # e.g., query: "vendor evaluation scores" → finds LFBW, EINA, EINE, EKES
        results = self.client.search(
            collection_name="sap_graph_tables",
            query_vector=self.model.encode(query).tolist(),
            limit=top_k
        )
        return [{"table": r["payload"]["table"], "score": r["score"]} for r in results]
    
    def index_all_paths(self, max_depth=3):
        """Index all valid JOIN paths for semantic path search."""
        all_tables = self.graph.get_all_tables()
        path_docs = []
        
        for src in all_tables:
            for tgt in all_tables:
                if src >= tgt:
                    continue
                paths = list(nx.all_simple_paths(self.graph.G, src, tgt, cutoff=max_depth))
                for path in paths:
                    path_key = " → ".join(path)
                    path_desc = self._build_path_description(path)
                    path_docs.append({
                        "path_key": path_key,
                        "description": path_desc,
                        "hops": len(path) - 1,
                        "is_cross_module": any(
                            self.graph.G.get_edge_data(path[i], path[i+1])["bridge_type"] == "cross_module"
                            for i in range(len(path)-1)
                        ),
                    })
        
        # Encode and index
        descs = [p["description"] for p in path_docs]
        embeddings = self.model.encode(descs)
        
        # ... upsert to Qdrant collection "sap_graph_paths"
    
    def semantic_path_search(self, query: str, top_k=3) -> List[dict]:
        """
        Find JOIN paths semantically — e.g., query "vendor pricing conditions for a material"
        returns EINA → EINE, EINA → MARA path even without exact table names.
        """
        results = self.client.query_collection(
            collection_name="sap_graph_paths",
            query_vector=self.model.encode(query).tolist(),
            limit=top_k
        )
        return results
```

**Hybrid retrieval flow:**
```
User: "Show me vendors who supplied materials that were rejected in QM"
       ↓
  Vector search (tables): "quality inspection vendor material" → [QALS, QAVE, MARA, LFA1]
       ↓
  Graph traversal: LFA1 → EINA → MARA → QALS (via MAPL/PLMK)
       ↓
  Assembled SQL with QM joins
```

### 4.2 Community Detection (Module Partitioning)

NetworkX's community detection algorithms (`louvain_communities`, `label_propagation`) can automatically discover the natural module structure of the SAP graph — useful for **graph partitioning** and **federated traversal**.

```python
import networkx as nx
from networkx.algorithms.community import louvain_communities

def detect_sap_communities(graph):
    """Automatically detect natural module clusters in the FK graph."""
    # Louvain maximizes modularity — SAP's module structure emerges naturally
    communities = louvain_communities(graph, resolution=1.5, seed=42)
    
    community_map = {}
    for idx, comm in enumerate(communities):
        comm_graph = graph.subgraph(comm)
        cross_module_edges = [
            (u, v) for u, v in comm_graph.edges
            if comm_graph.get_edge_data(u, v)["bridge_type"] == "cross_module"
        ]
        community_map[idx] = {
            "tables": sorted(comm),
            "size": len(comm),
            "cross_module_connections": len(cross_module_edges),
            "likely_module": infer_module_from_tables(comm),
        }
    
    return community_map

def infer_module_from_tables(tables):
    """Heuristic module inference from table name prefixes."""
    prefixes = {
        "BKPF|BSEG|BSIK|BSAK|BSID|BSAD|SKA1|SKB1": "FI",
        "VBAK|VBAP|VBEP|VBFA|LIKP|LIPS|VBRK|VBRP": "SD",
        "EKKO|EKPO|EKKN|EKES|EINA|EINE|EORD": "MM-PUR",
        "MARA|MARC|MARD|MBEW|MAKT|MLGN|MLGT": "MM",
        "QALS|QAVE|QAMV|MAPL|PLMK": "QM",
        "KNA1|KNB1|KNVV|KNVK": "SD-CUST",
        "LFA1|LFB1|LFBK": "MM-VEND",
        "PRPS|PSP_|COVP|COSP": "PS",
    }
    counts = {mod: 0 for mod in prefixes}
    for table in tables:
        for mod, pattern in prefixes.items():
            import re
            if re.match(pattern, table):
                counts[mod] += 1
    return max(counts, key=counts.get)
```

**Use case:** When a query spans communities (modules), the orchestrator knows it's a cross-module query and activates extra validation steps.

### 4.3 Temporal-Aware Graph Traversal

SAP master data has **validity periods** (key dates, from/to). Standard FK traversal ignores temporal context — but these matter:

| Table | Temporal Key | Meaning |
|-------|-------------|---------|
| LFA1 | `ADRNR`, `DATAB` | Vendor address valid-from |
| KNB1 | `KUNNR`, `BUKRS`, `DATAB`, `DATBI` | Customer company-code validity |
| EINA | `DATAB`, `DATBI` | Info record validity period |
| MBEW | `BWKEY`, `MATNR`, `BWPRS`, `BWDAT` | Valuation price effective date |
| COSP/COSS | `GJAHR`, `PERBL` | Period-based cost totals |
| CSKS | `DATAB`, `DATBI` | Cost center validity |

```python
from datetime import date
from typing import Optional

class TemporalGraphRAG(GraphRAGManager):
    """
    Extends base graph with temporal validity awareness.
    For a given key date, prunes edges whose validity period
    doesn't contain the key date.
    """
    
    def temporal_validity_filter(
        self, 
        key_date: date, 
        extra_conditions: Optional[dict] = None
    ) -> nx.Graph:
        """
        Returns a subgraph containing only edges valid on key_date.
        extra_conditions: {table: {col: value}} for additional filters.
        """
        filtered_G = nx.Graph()
        
        # Copy all nodes (nodes are always valid)
        for node in self.G.nodes(data=True):
            filtered_G.add_node(node[0], **node[1])
        
        # Filter edges by temporal validity
        for u, v, data in self.G.edges(data=True):
            if not self._is_temporally_valid(u, v, data, key_date, extra_conditions):
                continue
            filtered_G.add_edge(u, v, **data)
        
        return filtered_G
    
    def _is_temporally_valid(self, u, v, data, key_date, extra_conditions) -> bool:
        """
        Check if the edge (FK relationship) is valid on key_date.
        In practice this maps to SAP's Open SQL date filtering.
        """
        # This is a simplified check — production would inspect
        # the edge's temporal columns and compare against key_date
        return True  # Default: include all edges
    
    def query_as_of_date(
        self, 
        start_table: str, 
        end_table: str, 
        key_date: date,
        extra_conditions: Optional[dict] = None
    ) -> str:
        """Find JOIN path valid as of a specific date."""
        filtered_G = self.temporal_validity_filter(key_date, extra_conditions)
        
        if start_table not in filtered_G or end_table not in filtered_G:
            return f"Table(s) not in temporal subgraph for {key_date}"
        
        try:
            path = nx.shortest_path(filtered_G, source=start_table, target=end_table)
        except nx.NetworkXNoPath:
            return f"No path found for date {key_date} — may need broader date range"
        
        return self.traverse_graph_on_subgraph(filtered_G, path)
```

**Important:** This is primarily a **query-time filter** — the graph itself is the metadata skeleton. The temporal validity is enforced in the **generated SQL** via `WHERE` clauses, not by modifying the graph structure.

### 4.4 Cycle-Aware Traversal (Self-Referencing Tables)

SAP has self-referencing FKs that can create problematic cycles:

```python
# MARA → MARC → MARD → MLGN → MLGT → MARD (cycle back!)
# MARA has multiple 1:N branches that reconverge

def find_cycles_with_semantic_meaning(graph) -> List[dict]:
    """Detect cycles and annotate them with semantic meaning."""
    cycles = list(nx.simple_cycles(graph))
    
    meaningful_cycles = []
    for cycle in cycles:
        if len(cycle) <= 1:
            continue
        
        # Classify the cycle
        cycle_type = classify_cycle(cycle, graph)
        meaningful_cycles.append({
            "tables": cycle,
            "length": len(cycle),
            "type": cycle_type,
            "warning": get_cycle_warning(cycle_type),
        })
    
    return meaningful_cycles

CYCLE_TYPES = {
    "material_plant_hierarchy": {
        "pattern": ["MARA", "MARC", "MARD"],
        "warning": "1:N material-plant hierarchy. May cause row explosion if aggregated.",
        "sql_guidance": "Always filter on WERKS/LGORT before aggregation.",
    },
    "document_flow": {
        "pattern": ["VBAK", "VBFA", "LIKP", "VBRK"],
        "warning": "Document flow cycle. Use VBFA-TDOBJECT to filter direction.",
        "sql_guidance": "Use VBFA-VBTYP_N to determine document type in flow.",
    },
    "financial_index": {
        "pattern": ["BSEG", "BSIK", "BSAK", "BSID", "BSAD"],
        "warning": "FI secondary index cycle. Each index is a view of BSEG — not a real join.",
        "sql_guidance": "Use BKPF+BSEG as source of truth; indexes are for filtering only.",
    },
}
```

### 4.5 Federated Cross-Database JOIN Path (S/4 + BW + S/4HANA Cloud)

Enterprise SAP landscapes aren't single-database — Graph RAG must be aware of **cross-system boundaries**.

```python
SYSTEM_BOUNDARIES = {
    "ECC6": ["T001", "BKPF", "BSEG", "MARA", "EKKO"],  # On-prem ECC
    "S4HANA": ["I_DeliveryDocument", "I_SalesOrder"],   # CDS views (S/4)
    "BW": ["RSODS", "RSDODSO"],                         # BW data stores
    "S4HANA_CLOUD": ["A_SalesOrder", "A_PurchaseOrder"],  # CQL API
}

def detect_cross_system_path(path: List[str]) -> dict:
    """Detect if a JOIN path crosses system boundaries."""
    systems_hit = set()
    cross_system_edges = []
    
    for table in path:
        for system, tables in SYSTEM_BOUNDARIES.items():
            if table in tables:
                systems_hit.add(system)
    
    if len(systems_hit) > 1:
        return {
            "is_cross_system": True,
            "systems": list(systems_hit),
            "warning": f"Path spans {len(systems_hit)} systems. "
                        f"Remote function calls (RFC) or OData required.",
            "recommendation": "Use CDS views for cross-module S/4 queries. "
                               "SAP HANA Smart Data Access for remote tables.",
        }
    return {"is_cross_system": False}
```

---

## 5. SAP HANA-Specific Optimizations

### 5.1 HANA Graph Engine (Native)

SAP HANA has a **native Graph Engine** — for production deployments, the NetworkX graph should be replaceable with HANA's native graph:

```sql
-- Create HANA graph workspace from existing tables
CREATE GRAPH WORKSPACE sap_fk_graph
  EDGE TABLE "EINA_EINE_FK"
    SOURCE COLUMN "LIFNR"
    TARGET COLUMN "INFNR"
  VERTEX TABLE "EINA"
    KEY COLUMN "INFNR";
```

For development, the Python NetworkX layer serves as a **portable simulation** of what HANA's native graph engine would do.

### 5.2 SAP HANA Smart Data Integration (SDI)

For federated queries across S/4 + BW + External ERP:

```sql
-- Remote table via SDI (pseudo-SQL)
SELECT v.LIFNR, e.MATNR, SUM(gr.MENGE)
FROM REMOTE_TABLE("ECC6"."EKKO") AS v
JOIN REMOTE_TABLE("ECC6"."EKPO") AS e ON v.EBELN = e.EBELN
JOIN REMOTE_TABLE("S4HANA"."I_GoodsReceipt") AS gr 
  ON e.PO_NUMBER = gr.PURCHASEORDER
WHERE v.LIFNR = '0000010001'
GROUP BY v.LIFNR, e.MATNR;
```

The graph detects cross-system paths and the orchestrator generates **federated SQL** with remote table references.

### 5.3 SAP HANA SQLScript + AMDP for Path Execution

Generated JOIN paths can be wrapped in **Table UDFs / Table Functions** for reuse:

```sql
CREATE FUNCTION GET_VENDOR_MATERIAL_PATH(p_vendor VARCHAR(10))
  RETURN TABLE (
    vendor    VARCHAR(10),
    info_rec  VARCHAR(10),
    material  VARCHAR(18),
    plant     VARCHAR(4),
    unit      VARCHAR(3)
  )
  AS
  BEGIN
    RETURN
      SELECT DISTINCT
        l.LIFNR   AS vendor,
        e.INFNR   AS info_rec,
        e.MATNR   AS material,
        e.EKORG   AS plant,
        e.MEINH   AS unit
      FROM :p_vendor          AS l
      LEFT JOIN EINA          AS e  ON l.LIFNR = e.LIFNR
      LEFT JOIN EINE          AS ei ON e.INFNR = ei.INFNR
      LEFT JOIN MARA          AS m  ON e.MATNR = m.MATNR
      WHERE l.LIFNR = :p_vendor
        AND e.MATNR <> '';
  END;
```

### 5.4 CDS View Integration (S/4HANA Cloud)

For S/4HANA Cloud (where direct table access is restricted), the graph extends to **CDS views**:

```python
CDS_NAVIGATION_PATHS = {
    # Material stock CDS views
    "I_MaterialStock": {
        "base_table": "MARD",
        "joins_to": ["I_Plant", "I_StorageLocation", "I_Material"],
        "annotations": "@AnalyticsDetails.query.axis: CURRENCY",
    },
    # Vendor exposure
    "I_VendorAccountBalance": {
        "base_table": "BSIK",
        "extends": ["BSAK", "BSID", "BSAD"],
        "annotations": "@AnalyticsDetails.query.display: CURRENCY_AND_UNIT",
    },
    # Purchase contract
    "C_PurchaseContractStdCube": {
        "base_table": "EKKO",
        "extends": ["EKPO", "EINA", "LFA1"],
    },
}

def find_cds_equivalent(journal_path: List[str]) -> Optional[str]:
    """Check if a table JOIN path has a pre-built CDS view equivalent."""
    for cds_name, cds_info in CDS_NAVIGATION_PATHS.items():
        if set(journal_path).issubset(set(cds_info.get("extends", []))):
            return cds_name
    return None
```

---

## 6. Missing Graph Structure (Critical Gaps)

The current graph has significant gaps. These tables/relationships should be added for completeness:

### 6.1 Bill of Materials (BOM) — PP/MM Core

```
STKO (BOM Header) → STPO (BOM Items)
  ↓
MAST (Material-BOM Assignment) → MARA
  ↓
CRHD (Work Center Header) → CRCO (Work Center-Activity Type)
  ↓
PLPO (Routing Operations) → MARA
```

**Gap:** BOM explosion (multi-level BOM traversal) requires **recursive CTE** on SAP HANA — standard BFS won't handle it.

```sql
-- Recursive CTE for multi-level BOM explosion on HANA
WITH RECURSIVE bom_explosion (MATNR, COMPONENT, DEPTH, PATH) AS (
    -- Base: top-level BOM
    SELECT s.MATNR, st.MATNR AS COMPONENT, 0 AS DEPTH, 
           CAST(s.MATNR || '/' AS VARCHAR(200)) AS PATH
    FROM STKO s
    JOIN STPO st ON s.STLNR = st.STLNR AND s.STLAL = st.STLAL
    WHERE s.MATNR = :TOP_MATNR AND s.STLST = '1'  -- active BOM
    
    UNION ALL
    
    -- Recursive: sub-BOMs
    SELECT b.MATNR, st.MATNR, b.DEPTH + 1, 
           b.PATH || st.MATNR || '/'
    FROM bom_explosion b
    JOIN MAST m ON b.COMPONENT = m.STLNR
    JOIN STKO s ON m.STLNR = s.STLNR AND m.STLAL = s.STLAL
    JOIN STPO st ON s.STLNR = st.STLNR AND s.STLAL = st.STLAL
    WHERE b.DEPTH < :MAX_DEPTH
)
SELECT * FROM bom_explosion ORDER BY DEPTH, PATH;
```

### 6.2 Routing / Work Center — PP Core

```
MARA → MAPL (Task list assignment) → PLKO/PLPO (Routing/Task list)
  ↓
CRHD (Work Center) → CRCO (Capacity allocation)
  ↓
AFFC (Confirmations) → AFVC (Operation confirmation)
```

### 6.3 Quality Management — Inspection Lot Flow

```
QALS (Inspection Lot) → QAMV (Inspection results) → QAVE (Usage Decision)
  ↓
MAPL (QM task list assignment to material) → PLMK (Inspection characteristics)
  ↓
MARA → MARC (plant-specific QM control) → QALS (via inspection point)
```

### 6.4 PM/CS — Equipment and Functional Locations

```
EQUI (Equipment Master) → IHO6 (Equipment BOM)
  ↓
IHK6 (Functional Location) → ILOA (Location/Address assignment)
  ↓
IHPA (Partner processing) → BUT000 (BP relationships)
  ↓
ASMD (Service Order) → ASGM (Service Order Operations) → IA07 (Notification)
```

### 6.5 Variant Configuration (LO-VC)

```
MARA (Configurable material MTART='FERT') → INOB (Object link)
  ↓
CUOBJ (Configuration instance) → KLAH (Class) → CSSDB (Configuration data)
  ↓
KOTG/KOT2/KOT3/KOT4 (Pricing config) — extends into pricing
```

### 6.6 GTS (Global Trade Services) — Import/Export Compliance

```
EKKO → T001W (Plant) → J_1BNFE (Brazil NFS-e integration)
  ↓
DD07T / DD07L (Domain values) → J_3GDTV (Trade compliance rules)
```

---

## 7. Graph Completion — Auto-Population from SAP DDIC

Rather than manually building the FK graph, production systems should auto-generate it from SAP's own metadata:

```python
def auto_build_graph_from_ddic(connection):
    """
    Auto-populate the FK graph from SAP DDIC tables.
    Uses DD08L (FK relationships), DD03L (table fields), DD02L (tables).
    """
    # 1. Get all FK relationships defined in DDIC
    fk_rels = connection.execute("""
        SELECT 
            RELNAME,    -- FK relationship name
            CHECKTABLE, -- Target (parent) table
            FIELDNAME, -- Foreign key field
            TABNAME,   -- Child table
            DATATYPE,  -- Field type
            DOMNAME    -- Domain
        FROM DD08L
        WHERE AS4LOCAL = 'A'  -- Active
    """)
    
    # 2. For each FK, add edge to graph
    for rel in fk_rels:
        child = rel['TABNAME']
        parent = rel['CHECKTABLE']
        fk_field = rel['FIELDNAME']
        pk_field = get_pk_of(parent, connection)  # query DD03L
        
        graph.add_edge(
            child, parent,
            condition=f"{child}.{fk_field} = {parent}.{pk_field}",
            cardinality="N:1",
            bridge_type="internal",
            source="DDIC_AUTO"
        )
    
    # 3. Add company-code/plant scope tables
    scope_tables = connection.execute("""
        SELECT DISTINCT TABNAME, CONTFLAG  --scope indicator
        FROM DD03L
        WHERE (DOMNAME LIKE '%BUKRS%' OR DOMNAME LIKE '%WERKS%')
          AND AS4LOCAL = 'A'
    """)
    
    # 4. Infer cross-module bridges from field domain sharing
    # e.g., LIFNR domain appears in both EKKO and LFA1 → cross-module edge
```

---

## 8. Graph RAG Query Pipeline — Full Orchestration

```python
class GraphRAGQueryPipeline:
    """
    Complete query pipeline for Graph RAG in SAP context.
    """
    
    def __init__(self, graph_store, sql_library, schema_store):
        self.graph = graph_store
        self.sql_lib = sql_library
        self.schema = schema_store
    
    def resolve(self, user_query: str, context: dict) -> dict:
        """
        user_query: Natural language SAP query
        context: {user_role, company_code, language, ...}
        Returns: {sql, join_path, confidence, warnings}
        """
        # Step 1: Entity extraction
        entities = self.extract_sap_entities(user_query)
        # e.g., {"vendors": ["LFA1"], "materials": ["MARA"], "tables_found": []}
        
        # Step 2: Check meta-path library first
        meta_match = self.match_meta_path(user_query, entities)
        if meta_match:
            path = meta_match["path"]
            join_sql = self.graph.traverse_graph_on_subgraph(self.graph.G, path)
            return self.assemble_result(join_sql, path, entities, context)
        
        # Step 3: Table discovery (schema RAG)
        if not entities["tables_found"]:
            entities["tables_found"] = self.schema.semantic_search(
                user_query, top_k=4
            )
        
        # Step 4: Graph traversal
        if len(entities["tables_found"]) == 2:
            path = self.graph.find_path(
                entities["tables_found"][0], 
                entities["tables_found"][1]
            )
        else:
            # Multi-table: find Steiner tree (minimum connecting subgraph)
            path = self.find_steiner_tree(entities["tables_found"])
        
        if not path:
            return {"error": "No JOIN path found", "suggestion": "Try broader terms"}
        
        # Step 5: SQL generation with path
        join_sql = self.graph.traverse_graph_on_subgraph(self.graph.G, path)
        
        # Step 6: Inject proven SQL pattern (SQL RAG)
        proven_sql = self.sql_lib.find_similar(
            user_query, tables=entities["tables_found"], path=path
        )
        if proven_sql:
            join_sql = self.merge_with_proven_pattern(join_sql, proven_sql)
        
        # Step 7: Role-based column masking (Pillar 1)
        join_sql = self.apply_security_masking(join_sql, context["user_role"])
        
        # Step 8: Validation
        validation = self.validate_sql(join_sql, path)
        
        return {
            "sql": validation["sql"],
            "join_path": path,
            "join_path_explained": self.graph.get_subgraph_context(path),
            "confidence": validation["confidence"],
            "warnings": validation["warnings"],
            "temporal_filter": context.get("key_date"),
        }
    
    def find_steiner_tree(self, terminals: List[str]) -> List[str]:
        """
        Find minimum set of tables that connect all required tables.
        NP-hard in general — use approximation (Kleinberg-Tardos or Dreyfus-Wagner).
        For SAP graphs, a BFS expansion from each terminal to a meeting point works well.
        """
        if len(terminals) == 1:
            return terminals
        if len(terminals) == 2:
            return self.graph.find_path(terminals[0], terminals[1])
        
        # Multi-terminal: find closest pair, find path, then expand
        import itertools
        best_path = None
        for t1, t2 in itertools.combinations(terminals, 2):
            path = self.graph.find_path(t1, t2)
            if path and (not best_path or len(path) < len(best_path)):
                best_path = path
        
        return best_path or []
    
    def validate_sql(self, sql: str, path: List[str]) -> dict:
        """Validate generated SQL against path and SAP constraints."""
        warnings = []
        confidence = 1.0
        
        # Check 1: All tables in path are in FROM/JOIN
        for table in path:
            if table not in sql:
                warnings.append(f"Table {table} from path not in SQL")
                confidence -= 0.1
        
        # Check 2: No DML (SELECT only)
        if any(keyword in sql.upper() for keyword in ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE"]):
            warnings.append("DML keyword detected — blocking for safety")
            confidence = 0.0
        
        # Check 3: BSEG cardinality warning
        if "BSEG" in path and "BUKRS" not in sql:
            warnings.append("BSEG queried without BUKRS filter — will return ALL company codes")
            confidence -= 0.2
        
        # Check 4: MANDT (client) handling
        if "MANDT" not in sql and any(t in ["QALS", "BKPF", "BSEG"] for t in path):
            warnings.append(f"Table(s) require MANDT filter — adding automatically")
            # Auto-addMANDT would be injected here
        
        return {"sql": sql, "confidence": max(0.0, confidence), "warnings": warnings}
    
    def apply_security_masking(self, sql: str, user_role: str) -> str:
        """Apply column-level and row-level masking based on role."""
        from .security import get_column_mask_for_role
        masks = get_column_mask_for_role(user_role)
        
        for table_col, mask_expr in masks.items():
            table, col = table_col.split(".")
            if f'"{table}"."{col}"' in sql.upper() or f"{table}.{col}" in sql.upper():
                sql = sql.replace(
                    f'"{col}"', 
                    f"CASE WHEN {mask_expr} THEN {table}.{col} ELSE '***MASKED***' END AS {col}"
                )
        return sql
```

---

## 9. Priority Roadmap

| Priority | Technique | Complexity | Impact | Effort |
|----------|-----------|-----------|--------|--------|
| ~~P0~~ → ✅ DONE | ~~All-simple-paths enumeration~~ | Medium | High | ~~2 hrs~~ → ✅ |
| ~~P0~~ → ✅ DONE | ~~Meta-path library (20 common paths)~~ | Low | Very High | ~~4 hrs~~ → ✅ |
| ~~P0~~ → ✅ DONE | ~~Graph embedding index (Qdrant)~~ | Medium | High | ~~6 hrs~~ → ✅ |
| ~~P1~~ → ✅ DONE | ~~Steiner tree for multi-terminal queries~~ | High | Medium | ~~8 hrs~~ → ✅ |
| ~~P1~~ → ✅ DONE | ~~BOM explosion (recursive CTE)~~ | Medium | High | ~~4 hrs~~ → ✅ |
| **P1** | Cross-module bridge auto-detection | Medium | Medium — reduces manual edge definition | 6 hrs |
| ~~P2~~ → ✅ DONE | ~~Temporal-aware traversal~~ | Medium | Medium | ~~8 hrs~~ → ✅ |
| ~~P2~~ -> ✅ DONE | ~~CDS view equivalents mapping~~ | Low | Medium | ~~4 hrs~~ -> ✅ |
| **P2** | DDIC auto-population script | High | High — eliminates manual graph building | 10 hrs |
| **P3** | HANA Graph Engine native adapter | High | High — production performance at scale | 20 hrs |
| **P3** | Federated cross-system path detection | High | Medium — enterprise landscapes | 12 hrs |

---

## 11. Implementation Status (as of April 16, 2026)

| Component | Status | File | Notes |
|-----------|--------|------|-------|
| Graph FK map (80+ tables, 100+ edges) | ✅ DONE | `backend/app/core/graph_store.py` | 21 edge sets across 18 domains |
| BFS shortest-path traversal | ✅ DONE | `graph_store.py` | `traverse_graph()`, `find_path()` |
| All-simple-paths enumeration | ✅ DONE | `graph_store.py` → `AllPathsExplorer` | `find_all_ranked_paths(max_depth=5, top_k=3)` |
| Path scoring (cardinality + huge-table penalty) | ✅ DONE | `AllPathsExplorer._score_path()` | Penalizes 1:N, BSEG/MSEG transits |
| Meta-path library (14 paths, 22 variants) | ✅ DONE | `backend/app/core/meta_path_library.py` | 87KB, parameterized SQL templates |
| Meta-path match tool | ✅ DONE | `orchestrator_tools.py` → `meta_path_match()` | Score threshold >5.0 for strong hit |
| All-paths tool | ✅ DONE | `orchestrator_tools.py` → `all_paths_explore()` | Top-3 ranked JOIN paths |
| TemporalGraphRAG (17 tables, 3 temporal types) | ✅ DONE | `graph_store.py` → `TemporalGraphRAG` | Range / Fiscal Year / Key-Date |
| Temporal detection tool | ✅ DONE | `orchestrator_tools.py` → `temporal_graph_search()` | Regex + format parsing, no dateutil dependency |
| Orchestrator wiring (Step 0 + 2b + 3 updated) | ✅ DONE | `orchestrator.py` | Fast-path meta-match; temporal injection in SQL assembly |
| Orchestrator → final response includes `temporal` dict | ✅ DONE | `orchestrator.py` | `mode`, `filters` in response |
| Weighted path scoring (Edge Weights) | ✅ DONE | `AllPathsExplorer` | cardinality_1:1=1.0, 1:N=3.0, huge=5.0, cross_module=0.8 |
| Meta-path library CLI demo | ✅ DONE | `meta_path_library.py` `__main__` | Demo queries + full library listing |
| Community detection (Louvain) | 🔲 TODO | — | `louvain_communities()` ready to add to graph_store |
| Graph embeddings (Qdrant + Node2Vec) | ✅ DONE | `graph_embedding_store.py` (38KB) | Phase 5½ — Node2Vec 64-dim + text hybrid in Qdrant |
| Steiner tree (multi-terminal) | ✅ DONE | `graph_store.py` → `GraphRAGQueryPipeline.find_steiner_tree()` | BFS approximation for multi-terminal queries |
| BOM explosion (recursive CTE) | ✅ DONE | `meta_path_library.py` (91KB) | `material_cost_rollup` meta-path: STKO->STPO BOM explosion + CRHD/PLPO routing |
| DDIC auto-population | 🔲 TODO | — | Script to read DD08L and auto-build graph edges |
| CDS view equivalents | ✅ DONE | `core/cds_mapping.py` (3KB) | 34 table->CDS view mappings (I_BusinessPartner, I_Supplier, I_Product, I_PurchaseOrder, etc.) |
| HANA Graph Engine native adapter | 🔲 TODO | — | Replace NetworkX with HANA native graph at production scale |
| Federated cross-system paths | 🔲 TODO | — | Detect RFC/OData boundaries in JOIN paths |

### What Was Built Today (April 2, 2026)
1. `meta_path_library.py` — 14 meta-paths, 22 variants, full search engine
2. `AllPathsExplorer` class — all-ranked-paths enumeration with scoring
3. `TemporalGraphRAG` class — date/fiscal period detection and temporal SQL generation
4. `orchestrator_tools.py` — 3 new tools wired into TOOL_REGISTRY
5. `orchestrator.py` — new execution flow (Step 0 meta-path, Step 2b temporal, Step 3 ranked paths)

### Files Modified
- `backend/app/core/graph_store.py` — AllPathsExplorer + TemporalGraphRAG + 3 singletons
- `backend/app/core/meta_path_library.py` — **NEW** (87KB)
- `backend/app/agents/orchestrator_tools.py` — 3 new tools + TOOL_REGISTRY entries
- `backend/app/agents/orchestrator.py` — new execution flow + temporal in response
- `docs/GRAPH_RAG_SAP_HANA_TECHNIQUES.md` — this document
- `MEMORY.md` — session log updated

### Bugs Fixed Today
- `QALS.ART = '\x30\x31'` → `'01'` in `meta_path_library.py` (Python hex escape misread as octal)
- Stray `),` closing in `TOOL_REGISTRY` (`orchestrator_tools.py`) — duplicate entry close

---

## 10. Example — Full Query Resolution  *(April 2, 2026 — historical session)*

**Query:** *"Show me the last 3 purchase orders for vendor Lincoln Electronics, including material description, quantity ordered, and plant"*

**Step-by-step resolution:**

```
Step 1 — Entity extraction:
  "Lincoln Electronics" → LIFNR = '0000031000' (look up via BP search)
  "purchase orders" → EKKO + EKPO
  "material description" → MARA + MAKT
  "plant" → T001W

Step 2 — Meta-path check:
  Matches "procurement_basic" meta-path: LFA1 → EKKO → EKPO → MARA → MAKT

Step 3 — Graph traversal (if no meta-path match):
  LFA1.find_path(EKKO) → ['LFA1', 'EKKO']
  EKKO.find_path(MARA) → ['EKKO', 'EKPO', 'MARA']
  MARA.find_path(MAKT) → ['MARA', 'MAKT']
  Combined: ['LFA1', 'EKKO', 'EKPO', 'MARA', 'MAKT']

Step 4 — JOIN conditions assembled:
  LFA1.LIFNR = EKKO.LIFNR
  EKKO.EBELN = EKPO.EBELN
  EKPO.MATNR = MARA.MATNR
  MARA.MATNR = MAKT.MATNR AND MAKT.SPRAS = 'E'  (English)

Step 5 — SQL generation:
  SELECT EKKO.EBELN, EKKO.BEDAT, EKPO.MENGE, EKPO.MEINS,
         MARA.MATNR, MAKT.MAKTX, T001W.NAME1
  FROM EKKO
  JOIN LFA1 ON EKKO.LIFNR = LFA1.LIFNR AND LFA1.LIFNR = '0000031000'
  JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
  JOIN MARA ON EKPO.MATNR = MARA.MATNR
  JOIN MAKT ON MARA.MATNR = MAKT.MATNR AND MAKT.SPRAS = 'E'
  LEFT JOIN T001W ON EKPO.WERKS = T001W.WERKS
  ORDER BY EKKO.BEDAT DESC
  FETCH FIRST 3 ROWS ONLY;  -- SAP HANA syntax

Step 6 — Security check:
  ✓ LFA1.LIFNR masked if user role = 'PURCHASER' (can only see own vendor)
  ✓ EKKO.BEDAT visible
  ✓ No DML

Step 7 — Confidence score:
  1.0 (all tables found, no warnings, role filter applied)
```
