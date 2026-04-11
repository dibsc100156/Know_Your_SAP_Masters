# Know Your SAP Masters — Schema RAG Architecture (Pillar 3)
**Project:** Know_Your_SAP_Masters  
**Date:** 2026-03-24  
**Author:** OpenClaw AI Assistant  

---

## 1. Executive Summary

SAP S/4 HANA contains over 90,000 tables with semantically opaque names (e.g., `MARA`, `LFA1`, `VBAK`, `CSKS`). A natural language query like *"Show me the pricing conditions for our new raw materials"* must be translated into correct, executable HANA SQL. 

**Schema RAG (Pillar 3)** bridges the gap between natural language and SAP's proprietary data dictionary. Instead of embedding data rows, Schema RAG embeds **table metadata, column definitions, and join conditions**. When the Agentic Orchestrator (Pillar 2) determines a user is asking a flat or isolated Master Data question, it calls the Schema RAG tool to retrieve the exact tables required to write the SQL.

---

## 2. Why Schema RAG?

Stuffing 90,000 SAP tables into an LLM's context window is impossible. Fine-tuning a model on SAP schemas is brittle because every SAP implementation has custom Z-tables (`ZMARA`, `ZLFA1`) and appended fields.

Schema RAG provides:
1. **Dynamic Scope:** Automatically includes custom Z-tables and customer-specific fields without retraining.
2. **Context Efficiency:** Only retrieves the top-K relevant schemas (e.g., 3-5 tables) to keep the LLM prompt lean and focused.
3. **High Accuracy:** By searching over business descriptions rather than just technical names, the LLM finds the right tables (e.g., finding `KONP` when the user asks for "pricing conditions").

---

## 3. The Extraction Pipeline: DDIC to Vector Store

To build the Schema Vector Database, we extract metadata directly from the SAP Data Dictionary (DDIC) and Core Data Services (CDS).

### 3.1 Source Tables (Extraction)
A Python pipeline (via PyRFC or OData) extracts metadata from standard SAP dictionary tables:
*   `DD02L` (SAP Tables) & `DD02T` (Table Texts)
*   `DD03L` (Table Fields) & `DD03M` (Field Texts)
*   `DD08L` (Foreign Key Relationships for Join paths)

### 3.2 Document Enrichment
Raw SAP metadata is too sparse. The pipeline enriches the metadata into a JSON document optimized for vector embedding:

```json
{
  "table_name": "MARA",
  "domain": "Material Master",
  "module": "MM",
  "short_text": "General Material Data",
  "business_description": "Core master table containing global data for all materials, products, and services. Includes material type, industry sector, base unit of measure, and weight.",
  "key_columns": [
    {"field": "MATNR", "type": "CHAR(18)", "description": "Material Number"},
    {"field": "MTART", "type": "CHAR(4)", "description": "Material Type (e.g., ROH, FERT)"},
    {"field": "MEINS", "type": "UNIT(3)", "description": "Base Unit of Measure"}
  ],
  "common_joins": [
    {"target": "MARC", "condition": "MARA.MATNR = MARC.MATNR", "purpose": "Plant Data"},
    {"target": "MBEW", "condition": "MARA.MATNR = MBEW.MATNR", "purpose": "Valuation Data"}
  ]
}
```

### 3.3 Vector Database (Qdrant)
The enriched JSON documents are embedded (e.g., using `text-embedding-3-large`) and stored in **Qdrant**. Qdrant was selected for its robust payload filtering capabilities, which are essential for narrowing searches by SAP Module or Domain.

---

## 4. Multi-Domain Master Data Landscape

As an Enterprise Master Data Chatbot, the Schema RAG must cover multiple domains. Qdrant payload filters allow the Agentic Orchestrator to restrict the vector search to specific modules if the user's intent is known.

| Domain | Key Schema Targets Embedded in Qdrant |
| :--- | :--- |
| **Material (MM)** | `MARA`, `MARC`, `MARD`, `MBEW`, `MVKE` |
| **Business Partner** | `BUT000`, `LFA1`, `KNA1`, `ADRC`, `BUT100` |
| **Purchasing (MM-PUR)** | `EINA`, `EINE`, `EORD`, `EKKO`, `EKPO` |
| **Sales (SD)** | `VBAK`, `VBAP`, `KONV`, `KNVV`, `TVRO` |
| **Finance (FI/CO)** | `SKA1`, `SKB1`, `CSKS`, `CEPC`, `ANLA` |
| **Quality (QM)** | `QMAT`, `QPAC`, `PLMK`, `MAPL` |
| **Project System (PS)** | `PROJ`, `PRPS`, `AFVC` |

*Note: CDS Views (e.g., `I_Material`, `I_Supplier`, `I_CostCenter`) are prioritized over raw tables when available, as they provide pre-joined, business-ready abstractions.*

---

## 5. Integration with the 5-Pillar Architecture

1.  **Agentic RAG (Pillar 2)** receives the user query: *"List all raw materials in Plant 1000."*
2.  The Agent identifies the intent as Material Master retrieval.
3.  The Agent queries the **Schema RAG (Pillar 3)**: `search_schema(query="raw materials plant", module="MM", top_k=3)`
4.  Schema RAG queries Qdrant and returns the payloads for `MARA` (Material General) and `MARC` (Material Plant).
5.  The Agent optionally queries **SQL RAG (Pillar 4)** for known good SQL patterns joining MARA and MARC.
6.  The LLM generates the final HANA SQL.
7.  **Role-Aware RAG (Pillar 1)** validates that the user is authorized to view Plant 1000 data before execution.

---

## 6. Next Steps for Schema RAG Implementation

1.  **Refactor Extraction Script:** Update `generate_schemas.py` to pull from DD02L/DD03L across the expanded list of modules (MM, SD, FI, etc.) instead of just Vendor tables.
2.  **Migrate to Qdrant:** Update `update_vector_store.py` to use Qdrant instead of ChromaDB, implementing payload filtering by `SAP_Module`.
3.  **Implement CDS View Fallbacks:** Add logic to index S/4 HANA standard CDS Views alongside raw DDIC tables.
4.  **Agent Tool Binding:** Create the Python tool wrapper `get_sap_schema(query, module)` for the LangChain/Autogen orchestrator.