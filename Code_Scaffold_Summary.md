# SAP S/4 HANA Vendor Chatbot — Project Code Structure & Scaffold
**Project:** SAP_HANA_LLM_VendorChatbot  
**Date:** 2026-03-20  
**Author:** OpenClaw AI Assistant  

---

## The 5-Pillar Architecture Scaffold

This document outlines the codebase structure and scaffolding created for the 5-Pillar RAG Architecture (Role-Aware, Agentic, Schema, Graph, SQL). 

The backend is built with FastAPI, Pydantic, NetworkX (Graph RAG), ChromaDB (SQL RAG), and a custom Agentic Orchestrator loop.

---

### Directory Structure

```text
backend/
├── app/
│   ├── main.py                  # FastAPI Application entrypoint
│   ├── api/
│   │   └── routes.py            # POST /api/v1/chat endpoint
│   ├── core/
│   │   ├── security.py          # Pillar 1: Role-Aware RAG (SAPAuthContext)
│   │   ├── schema_store.py      # Pillar 3: Schema RAG (Table metadata)
│   │   ├── graph_store.py       # Pillar 4: Graph RAG (NetworkX SAP relationships)
│   │   ├── sql_library.py       # Pillar 5: SQL RAG (Curated HANA patterns)
│   │   └── sql_vector_store.py  # Pillar 5: SQL RAG (ChromaDB + embeddings)
│   ├── tools/
│   │   ├── schema_retriever.py  # Role-Aware Schema Filter
│   │   ├── graph_retriever.py   # Role-Aware Graph Pruner
│   │   ├── sql_retriever.py     # Role-Aware SQL Template Filter
│   │   └── sql_executor.py      # Safe execution wrapper + Response Masking
│   └── agents/
│       └── orchestrator.py      # Pillar 2: Agentic RAG Loop
├── requirements.txt             # Core dependencies (FastAPI, pydantic, pandas)
├── requirements_sql_rag.txt     # SQL RAG dependencies (sentence-transformers)
├── requirements_graph_rag.txt   # Graph RAG dependencies (networkx)
├── seed_sql_rag.py              # Script to seed ChromaDB with SQL patterns
├── test_security.py             # Script to test Role-Aware execution + masking
├── test_graph_rag.py            # Script to test role-pruned subgraph extraction
└── test_api.py                  # Script to test the full /chat endpoint flow
```

---

### Core Components Written

#### 1. Pillar 1: Role-Aware Security (`app/core/security.py`)
- Defines `SAPAuthContext` via Pydantic.
- Enforces organizational scope (`BUKRS`, `EKORG`), explicit table denials (`denied_tables`), and output masking (`masked_columns`).
- Mocks 4 distinct personas: `AP_CLERK`, `PROCUREMENT_MGR`, `AUDITOR`, `CFO`.

#### 2. Pillar 2: Agentic Orchestrator (`app/agents/orchestrator.py`)
- The `run_agent_loop` function simulates the ReAct flow.
- It sequentially calls: Schema Retriever → Graph Retriever → SQL Retriever → SQL Generator (Mocked) → Safe Executor.
- If any layer returns a security violation, the Orchestrator safely aborts and informs the user.

#### 3. Pillar 3: Schema RAG (`app/core/schema_store.py` & `app/tools/schema_retriever.py`)
- `MOCK_SAP_SCHEMA_STORE` holds table definitions (LFA1, EKKO, EKPO, BSIK, BSAK, BKPF).
- `RoleAwareSchemaRetriever` intercepts the raw metadata and strips out tables/columns the user isn't authorized to see *before* passing context to the LLM.

#### 4. Pillar 4: Graph RAG (`app/core/graph_store.py` & `app/tools/graph_retriever.py`)
- `SAPGraphStore` uses NetworkX to model structural joins (`JOINS_TO`, `POSTS_TO`) and cross-module processes.
- The `extract_subgraph` method performs a 2-hop BFS to find explicit join paths (e.g., `EKKO.EBELN = EKPO.EBELN`).
- `RoleAwareGraphRetriever` prunes unauthorized branches. If a Procurement Manager queries a vendor, the graph will traverse MM tables but *prune* FI tables (BKPF/BSEG) from the subgraph.

#### 5. Pillar 5: SQL RAG (`app/core/sql_library.py` & `app/core/sql_vector_store.py`)
- `SQL_RAG_LIBRARY` contains 4 seed templates (Open POs, Overdue Invoices, Vendor Master, Spend Aggregation) written in SAP HANA SQL idiom (using `MANDT`, `LOEKZ`, `DAYS_BETWEEN`).
- `SQLRAGStore` uses ChromaDB and `all-MiniLM-L6-v2` to embed the *intent* of the query.
- `RoleAwareSQLRetriever` ensures the user doesn't get a template containing unauthorized tables.

#### 6. Execution & Masking (`app/tools/sql_executor.py`)
- `SAPSQLExecutor` acts as the final guardrail.
- It parses the generated SQL for `MANDT` and read-only compliance.
- Post-execution, it iterates over `AuthContext.masked_columns` (e.g., `BANKN`).
  - Standard users see `***RESTRICTED***`.
  - Auditors see partial masks `DE12***...7890`.

---

### Setup and Testing

To run the scaffold locally in your Python environment:

1. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements_sql_rag.txt
   pip install -r requirements_graph_rag.txt
   pip install httpx
   ```

2. **Seed the SQL RAG Database:**
   ```bash
   python seed_sql_rag.py
   ```

3. **Run the Individual Tests:**
   ```bash
   python test_security.py    # Tests execution and response masking
   python test_graph_rag.py   # Tests subgraph extraction and role pruning
   ```

4. **Run the FastAPI Server:**
   ```bash
   uvicorn app.main:app --reload
   ```

5. **Test the Full API Flow:**
   ```bash
   python test_api.py
   ```

*This scaffold provides a complete, runnable foundation demonstrating how the 5-Pillar RAG architecture operates in sequence while enforcing strict SAP S/4 HANA security constraints at every layer.*