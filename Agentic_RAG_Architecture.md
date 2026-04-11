# Know Your SAP Masters — Agentic RAG Architecture (Pillar 2)
**Project:** Know_Your_SAP_Masters  
**Date:** 2026-03-24  
**Author:** OpenClaw AI Assistant  

---

## 1. The Limitation of Passive Retrieval

Pillars 3, 4, and 5 (Schema, SQL, and Graph RAG) are powerful **retrieval strategies**. They answer the question: *"What context should I give the LLM to write SAP SQL?"*

However, they share a critical limitation: they are **passive, single-shot pipelines**.
`User Query → Retrieve Context → Generate SQL → Execute → Return`

A single-shot pipeline cannot:
*   **Decide** which retrieval strategy to use (Schema vs. Graph).
*   **Decompose** a multi-part business question (e.g., "Find vendors in Germany and show their overdue invoices").
*   **Self-correct** if the generated HANA SQL throws a syntax error.
*   **Acknowledge** Authorization boundaries (Pillar 1) dynamically.

To solve this, we use **Agentic RAG (Pillar 2)** to act as the autonomous brain of the chatbot.

---

## 2. What is Agentic RAG?

Agentic RAG shifts the LLM from a passive code generator to an **active reasoning engine** using the ReAct (Reason + Act) loop.

```text
┌─────────────────────────────────────────────────────┐
│               THE AGENTIC REASONING LOOP            │
│                                                     │
│  User: "Show me the stock levels for Material 100"  │
│                                                     │
│  [THINK]   Intent: Material Stock Lookup.           │
│            I need to find the tables for material   │
│            master and stock quantities.             │
│                                                     │
│  [ACT]     Call Tool: search_schema(module="MM")    │
│                                                     │
│  [OBSERVE] Tool returns MARA and MARD tables.       │
│                                                     │
│  [THINK]   I have the tables. Now I need to write   │
│            HANA SQL to get the stock.               │
│                                                     │
│  [ACT]     Call Tool: execute_hana_sql("SELECT...") │
│                                                     │
│  [OBSERVE] SQL Error: "Invalid column: STOCK"       │
│                                                     │
│  [THINK]   Ah, the column in MARD is LABST.         │
│            I need to rewrite the SQL.               │
│                                                     │
│  [ACT]     Call Tool: execute_hana_sql("SELECT LABST")│
│                                                     │
│  [OBSERVE] Returns: [{LABST: 50, WERKS: 1000}]      │
│                                                     │
│  [ANSWER]  "You have 50 units of Material 100       │
│            in Plant 1000."                          │
└─────────────────────────────────────────────────────┘
```

---

## 3. Tool Ecosystem for Enterprise Master Data

The Agent is equipped with a specific set of tools that map to the other pillars of the architecture. It chooses which tools to use based on the user's intent.

### Core Agent Tools
1.  **`get_auth_context()` (Pillar 1)**
    *   *Purpose:* Fetches the user's allowed Company Codes (`BUKRS`), Plants (`WERKS`), and masked columns. The Agent must pass these as filters into its SQL.
2.  **`search_schema(query, module)` (Pillar 3)**
    *   *Purpose:* Queries Qdrant for flat table metadata. Used for single-domain questions (e.g., "What are the fields in the Customer master?").
3.  **`get_sql_patterns(intent, module)` (Pillar 4)**
    *   *Purpose:* Retrieves proven HANA SQL templates. Used to ensure the Agent uses SAP idioms (like `MANDT` and `LOEVM`).
4.  **`traverse_graph(start_entity, target_entity)` (Pillar 5)**
    *   *Purpose:* Queries NetworkX to find the join path between different modules (e.g., Material `MARA` to Vendor `LFA1`).
5.  **`execute_hana_sql(sql_string)`**
    *   *Purpose:* Runs the generated SQL against the SAP HANA database. Returns results or syntax errors for self-correction.

---

## 4. Multi-Domain Intent Routing

Because "Know Your SAP Masters" covers multiple domains (MM, SD, FI, QM, PS), the Agent's first THINK step is crucial: **Intent Classification**.

When a user asks a question, the Agent evaluates the domain to optimize its tool use:

*   **Intent: Material / Production** → Agent scopes Schema RAG searches to `module="MM"` or `module="PP"`.
*   **Intent: Finance / Costing** → Agent scopes searches to `module="FI"` or `module="CO"`.
*   **Intent: Cross-Module** (e.g., "Which vendors supply the raw materials for Cost Center 1000?") → Agent immediately reaches for the **Graph RAG tool** to map the `MM -> FI -> BP` joins.

---

## 5. The Self-Correction Loop

SAP HANA SQL is unforgiving. Agentic RAG provides resilience through its reflection loop:

1.  **Generation:** Agent writes SQL using Schema + SQL patterns.
2.  **Execution:** Agent calls `execute_hana_sql()`.
3.  **Observation:** HANA returns an error (e.g., `feature not supported: cross join without ON clause`).
4.  **Reflection:** Agent reads the error, reviews the Schema context to find the missing join keys, and rewrites the query.
5.  **Success:** Only when the SQL succeeds does the Agent synthesize the final natural language answer to the user.

---

## 6. Implementation Architecture

We will implement the Agentic Orchestrator using **LangGraph** (or a similar graph-based state machine) rather than a simple LangChain zero-shot agent. This allows us to strictly define the state transitions:

```text
[ START ] ---> [ Intent Analysis ]
                      |
                      v
            [ Context Gathering ] <------ (Loops if more info needed)
             - Schema RAG (P3)      |
             - SQL RAG (P4)         |
             - Graph RAG (P5)       |
                      |-------------|
                      v
               [ SQL Generation ]
                      |
                      v
              [ SQL Validation ] (Checks AuthContext - P1)
                      |
                      v
               [ Execution ]
               /           \
         [ Error ]       [ Success ]
             |               |
       (Self-Correct)        v
                      [ Final Answer ]
```

---

## 7. Next Steps for Implementation

1.  **Define Tool Interfaces:** Create Python functions with rigid type hints and docstrings for `search_schema`, `get_sql_patterns`, and `execute_hana_sql` so the LLM understands how to call them.
2.  **State Definition:** Define the LangGraph `State` object to carry the `User Query`, `AuthContext`, `Gathered Context`, `Generated SQL`, and `Execution Results` between nodes.
3.  **Build the Agent Graph:** Wire the nodes together, implementing the conditional logic for the Self-Correction loop.
4.  **Prompt Engineering:** Write the system prompt that forces the Agent to check the AuthContext (Pillar 1) before generating SQL.