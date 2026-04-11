# Know Your SAP Masters — SQL RAG Architecture (Pillar 4)
**Project:** Know_Your_SAP_Masters  
**Date:** 2026-03-24  
**Author:** OpenClaw AI Assistant  

---

## 1. Where SQL RAG Sits in the 5-Pillar Architecture

```
Pillar 1: Role-Aware RAG → Secures and masks the data
Pillar 2: Agentic RAG    → Orchestrates the reasoning and tool selection
Pillar 3: Schema RAG     → Retrieves WHAT tables and columns to use
Pillar 4: SQL RAG        → Retrieves PROVEN SAP SQL PATTERNS as few-shot context
Pillar 5: Graph RAG      → Maps cross-module relationships
```

SQL RAG is fundamentally different from Schema RAG. It doesn't retrieve table metadata — it retrieves **previously validated, working SQL queries** as few-shot examples to guide the generation of new queries across all Master Data domains.

---

## 2. What is SQL RAG?

### The Core Insight
LLMs generate significantly better SQL when shown **similar working SQL** rather than just table schemas. This is the few-shot principle applied to structured query generation.

```
Standard Text-to-SQL:
  User Query + Schema → LLM → SQL (from scratch, high hallucination of SAP idioms)

SQL RAG:
  User Query + Schema + Retrieved Similar SQLs → LLM → SQL
  (grounded in proven SAP patterns, dramatically lower error rate)
```

Instead of embedding table descriptions, SQL RAG builds a **SQL Query Library** — a curated, versioned store of proven queries. At query time, the orchestrator embeds the user's natural language question, retrieves the most similar proven SQL entries, and injects them into the prompt.

---

## 3. Why SQL RAG for SAP Master Data?

SAP HANA SQL is highly idiomatic. Across all modules (MM, SD, FI, QM), there are required patterns the LLM consistently misses without examples:

### 3.1 The MANDT (Client) Filter
```sql
-- WRONG (Standard SQL):
SELECT * FROM MARA WHERE MATNR = '100-100'

-- CORRECT (SAP Idiom):
SELECT MATNR, MTART, MEINS FROM MARA WHERE MANDT = '100' AND MATNR = '100-100'
```

### 3.2 Module-Specific Deletion Flags
Different Master Data domains use different deletion and blocking flags.
*   **Material (MM):** `MARA.LVORM` (Client level), `MARC.LVORM` (Plant level)
*   **Vendor (BP):** `LFA1.LOEVM` (Central), `LFB1.LOEVM` (Company Code)
*   **Sales (SD):** `VBAK.FAKSK` (Billing block), `VBAK.LIFSK` (Delivery block)
SQL RAG ensures the LLM sees and mimics the correct exclusion logic for the domain.

### 3.3 Complex, Non-Obvious Joins
An enterprise query often spans header, item, and status tables.
```sql
-- SD Pricing Pattern (stored in SQL library)
SELECT k.KNUMV, p.KPOSN, p.KSCHL, p.KBETR 
FROM KONV p
INNER JOIN VBAK v ON v.KNUMV = p.KNUMV AND v.MANDT = p.MANDT
WHERE v.MANDT = '100' AND v.VBELN = :sales_order
```

### 3.4 Query Performance & Business Logic
SAP tables like `BSEG` or `MSEG` can hold billions of rows. Queries must use index-supporting fields first (e.g., `BUKRS`, `BELNR`, `GJAHR`). SQL RAG stores performance-validated queries, transferring index awareness to the LLM. Furthermore, business logic (like calculating overdue invoices via `ADD_DAYS(ZFBDT, ZBD3T)`) is captured and reused.

---

## 4. SQL RAG Pipeline

```text
1. INDEXING (Ongoing)
   Curate validated SQL templates -> Embed Natural Language Intent -> Store in Qdrant Vector DB

2. RETRIEVAL (Runtime)
   Embed User Query -> Search Qdrant (Filter by Module) -> Retrieve Top-K SQL Examples

3. GENERATION
   Agentic RAG Prompt = [User Query] + [Schema RAG Metadata] + [SQL RAG Few-Shot Examples] -> LLM

4. EXECUTION & FEEDBACK
   Validate Syntax & Auth -> Execute on HANA -> Log Success -> Auto-promote good queries to Library
```

---

## 5. Master Data SQL Library — Seed Entries

To support the "Know Your SAP Masters" scope, the SQL library is seeded with patterns across multiple domains:

| Domain | Query ID | Intent / Business Question | Core Tables | Priority |
|---|---|---|---|---|
| **Material (MM)** | `MAT-001` | "Show material base details and weight" | `MARA`, `MAKT` | P0 |
| **Material (MM)** | `MAT-002` | "List materials extended to Plant X" | `MARA`, `MARC` | P0 |
| **Material (MM)** | `MAT-003` | "Show current stock for material in plant" | `MARD`, `MARC` | P0 |
| **Sales (SD)** | `SLS-001` | "Show sales order header and status" | `VBAK`, `VBUK` | P0 |
| **Sales (SD)** | `SLS-002` | "List items and pricing for sales order" | `VBAP`, `KONV` | P0 |
| **Finance (FI)** | `FIN-001` | "Show G/L account details for company" | `SKA1`, `SKB1` | P0 |
| **Finance (FI)** | `FIN-002` | "List open vendor items (overdue)" | `BSIK`, `LFA1` | P0 |
| **Finance (FI)** | `FIN-003` | "Cost center hierarchy details" | `CSKS`, `CSKT` | P1 |
| **Purchasing** | `PUR-001` | "Open POs for a specific vendor" | `EKKO`, `EKPO`, `LFA1` | P0 |
| **Purchasing** | `PUR-002` | "Purchasing Info Record details" | `EINA`, `EINE` | P1 |
| **Business P.** | `BP-001` | "Vendor bank and payment terms" | `LFA1`, `LFB1`, `LFBK` | P0 |
| **Quality (QM)** | `QM-001` | "Inspection plan for material" | `MAPL`, `PLKO`, `PLPO` | P2 |
| **Project (PS)** | `PS-001` | "WBS elements under project" | `PROJ`, `PRPS` | P2 |

---

## 6. Implementation Roadmap

1.  **Define Schema:** Create the `SQLLibraryEntry` dataclass to hold the intent, SQL template, module tags, and execution metrics.
2.  **Vector DB Migration:** Ensure the SQL Library is embedded and stored in **Qdrant** alongside the Schema RAG data, using distinct collections (`sap_schemas` vs `sap_sql_patterns`).
3.  **Seed Patterns:** Write and manually validate the seed queries for MM, SD, FI, and BP against a real SAP HANA instance.
4.  **Agent Integration:** Expose a `get_sql_patterns(intent, module)` tool for the Agentic Orchestrator to pull examples before generating code.
5.  **Feedback Loop:** Implement the execution logger to capture dynamically generated, successful queries and stage them for addition to the SQL Library.