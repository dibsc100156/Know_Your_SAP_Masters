# Know Your SAP Masters — Graph RAG Architecture (Pillar 5)
**Project:** Know_Your_SAP_Masters  
**Date:** 2026-03-24  
**Author:** OpenClaw AI Assistant  

---

## 1. The Limitation of Schema RAG

Schema RAG (Pillar 3) is excellent at retrieving flat table metadata when the domain is known (e.g., retrieving `MARA` and `MARC` for a Material query). 

However, enterprise questions rarely stay within one module. Consider the query:
*"Which vendors supply the raw materials that are currently sitting in Quality Inspection for Plant 1000?"*

To answer this, the SQL must join across four different SAP modules:
1.  **Quality (QM):** `QALS` (Inspection Lot)
2.  **Material (MM):** `MARA` (Material Master)
3.  **Purchasing (MM-PUR):** `EINA` (Purchasing Info Record)
4.  **Business Partner (BP):** `LFA1` (Vendor Master)

Schema RAG cannot reliably predict this join path because the vector similarity between "vendor" and "quality inspection" is low. We need a system that understands the **structural relationships** between SAP modules. That is Graph RAG.

---

## 2. What is Graph RAG in this Context?

Graph RAG (Pillar 5) represents the SAP Data Dictionary not as isolated documents, but as a **Network Graph**:
*   **Nodes:** SAP Tables (e.g., `LFA1`, `MARA`, `CSKS`).
*   **Edges:** Foreign Key Relationships / Join Conditions (e.g., `MATNR`, `LIFNR`).
*   **Properties:** Cardinality, SAP Module, Business Description.

When the Agentic Orchestrator (Pillar 2) detects a cross-module question, it uses Graph RAG to find the shortest path between the entities.

```text
Query: "Vendors (LFA1) for Material (MARA)"

Graph Traversal (Shortest Path):
LFA1 (Vendor) <---[LIFNR]---> EINA (Info Record) <---[MATNR]---> MARA (Material)
```

The Orchestrator then uses this path to construct the `INNER JOIN` sequence for the HANA SQL.

---

## 3. NetworkX Implementation

We use **NetworkX** (a Python graph library) to build and traverse the in-memory graph, rather than a heavy, dedicated Graph Database like Neo4j. This keeps the architecture lightweight and fast.

### 3.1 Graph Construction
The graph is built by extracting foreign key relationships (`DD08L` table in SAP) and mapping them as edges:

```python
import networkx as nx

G = nx.Graph()

# Add Nodes (Tables)
G.add_node("LFA1", module="BP", desc="Vendor Master")
G.add_node("EINA", module="MM", desc="Purchasing Info Record")
G.add_node("MARA", module="MM", desc="Material Master")
G.add_node("CSKS", module="FI", desc="Cost Center Master")

# Add Edges (Join Paths)
G.add_edge("LFA1", "EINA", condition="LFA1.LIFNR = EINA.LIFNR")
G.add_edge("EINA", "MARA", condition="EINA.MATNR = MARA.MATNR")
```

### 3.2 Graph Traversal (The Tool)
The Agent uses a specialized tool to query the graph:

```python
def traverse_graph(start_table: str, end_table: str) -> str:
    """Finds the shortest join path between two SAP tables."""
    try:
        path = nx.shortest_path(G, source=start_table, target=end_table)
        
        # Reconstruct the JOIN string
        join_string = ""
        for i in range(len(path) - 1):
            edge_data = G.get_edge_data(path[i], path[i+1])
            join_string += f"JOIN {path[i+1]} ON {edge_data['condition']} \n"
            
        return join_string
    except nx.NetworkXNoPath:
        return "No direct join path found."
```

---

## 4. Cross-Module Master Data Paths

The "Know Your SAP Masters" graph will explicitly map the integration points between the siloed domains:

| Integration Point | Module A | Module B | Bridge Tables / Join Path |
| :--- | :--- | :--- | :--- |
| **Procurement** | Material (`MARA`) | Vendor (`LFA1`) | `EINA` (Info Record) or `EKPO` (PO Item) |
| **Sales** | Material (`MARA`) | Customer (`KNA1`) | `KNMT` (Customer-Material Info) |
| **Costing** | Material (`MARA`) | Cost Center (`CSKS`) | `MARC` -> `MBEW` -> `CKMLHD` |
| **Quality** | Material (`MARA`) | Inspection (`PLMK`) | `MAPL` (Material to Task List) |
| **Project** | Material (`MARA`) | WBS (`PRPS`) | `RESB` (Reservations/Dependent Reqs) |
| **Finance** | Vendor (`LFA1`) | G/L Account (`SKA1`) | `BSIK` (Open Items) -> `HKONT` |

---

## 5. Integration with the Agent

1.  **User Query:** *"Which cost centers are consuming material RM-100?"*
2.  **Agent (Pillar 2):** Identifies entities: Cost Center (`CSKS`) and Material (`MARA`).
3.  **Agent Action:** Calls `traverse_graph("MARA", "CSKS")`.
4.  **Graph RAG (Pillar 5):** Returns the multi-hop join path: `MARA -> MARC -> MSEG -> CSKS`.
5.  **Agent Action:** Uses the path to write the SQL query.
6.  **Agent Action:** Executes SQL and returns the result.

---

## 6. Next Steps for Implementation

1.  **Graph Data Generation:** Write `extract_foreign_keys.py` to pull the `DD08L` (Foreign Keys) data from SAP for the core master data tables across MM, SD, FI, PS, and QM.
2.  **Build NetworkX Store:** Update `update_graph_store.py` to ingest the foreign keys and serialize the NetworkX graph to disk (e.g., using `pickle` or a GraphML file) for fast loading at runtime.
3.  **Tool Wrapping:** Expose the `traverse_graph` function as a callable tool for the LangGraph agent.
4.  **Fallback Logic:** Implement fallback logic so if `NetworkXNoPath` occurs, the Agent is instructed to try a different bridge table or ask the user for clarification.