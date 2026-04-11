# Know Your SAP Masters — Role-Aware RAG Architecture (Pillar 1)
**Project:** Know_Your_SAP_Masters  
**Date:** 2026-03-24  
**Author:** OpenClaw AI Assistant  

---

## 1. Executive Summary

In an enterprise SAP S/4 HANA environment, answering a question correctly is only half the battle. The other half is ensuring the user is legally and operationally allowed to see the answer. 

**Role-Aware RAG (Pillar 1)** is the foundation of the 5-Pillar Architecture. It is not a retrieval strategy for finding data; it is a security perimeter that intercepts every request to ensure that the chatbot respects SAP's granular, object-based authorization model (e.g., Company Code, Plant, Purchasing Org restrictions).

```text
Without Pillar 1: 
"Show me all executive payroll postings." -> *Returns highly sensitive data.*

With Pillar 1:
"Show me all executive payroll postings." -> *Error: User lacks BUKRS/AuthGroup access.*
```

---

## 2. The Multi-Layer Security Mesh

Because Large Language Models (LLMs) cannot be inherently trusted to filter data, Role-Aware RAG enforces security at three distinct layers:

### Layer 1: Prompt/Context Injection (Pre-Generation)
When the Agentic Orchestrator (Pillar 2) receives a query, it first calls the `get_auth_context(user_id)` tool. This tool fetches the user's SAP Authorization Profile (via RFC or cached identity provider) and creates a hardcoded string of allowed values.

```python
# AuthContext injected into the LLM System Prompt:
"""
You are writing HANA SQL for user: SANJEEV.
SECURITY CONSTRAINTS:
- You MUST include a WHERE clause for Company Code (BUKRS). 
- The user is ONLY authorized for BUKRS IN ('1000', '2000').
- The user is ONLY authorized for Plant (WERKS) IN ('1010').
- You MUST NOT select the column LFBK.BANKN (Bank Account).
"""
```

### Layer 2: SQL Validation (Post-Generation, Pre-Execution)
LLMs hallucinate. If the LLM forgets to include the `WHERE BUKRS = '1000'` filter, executing the query would cause a massive data leak.

Before any SQL is sent to HANA, a deterministic Python parser (e.g., `sqlglot`) intercepts the string and verifies:
1.  **Read-Only:** Ensure no `INSERT`, `UPDATE`, `DELETE`, `DROP`.
2.  **Auth Enforcement:** Ensure the required `WHERE` conditions for `BUKRS`, `WERKS`, or `EKORG` are present in the AST (Abstract Syntax Tree).
3.  **Column Checks:** Ensure restricted columns (like Bank Account or SSN) are not in the `SELECT` statement.

### Layer 3: Response Masking (Post-Execution)
If a query legitimately returns a dataset that includes a mix of public and sensitive fields, the final Python layer redacts the sensitive fields before returning the markdown to the user.

---

## 3. SAP Master Data Authorization Objects

To support the "Know Your SAP Masters" multi-domain scope, Pillar 1 must handle the standard authorization objects for each domain. The Python backend maps these SAP objects to database columns:

| Domain | Key SAP Auth Object | Description | Maps to HANA Column |
| :--- | :--- | :--- | :--- |
| **Finance (FI)** | `F_BKPF_BUK` | Accounting Document: Company Code | `BUKRS` |
| **Material (MM)** | `M_MATE_WRK` | Material Master: Plant | `WERKS` |
| **Purchasing (MM)** | `M_BEST_EKO` | Purchasing Organization | `EKORG` |
| **Sales (SD)** | `V_VBAK_VKO` | Sales Organization | `VKORG` |
| **Business Partner** | `F_LFA1_BUK` | Vendor: Company Code | `BUKRS` |
| **Business Partner** | `F_KNA1_BUK` | Customer: Company Code | `BUKRS` |

---

## 4. The Immutable Audit Ledger

Enterprise chatbots require strict auditability. Every interaction managed by the Agentic Orchestrator is logged to an immutable ledger (e.g., a secure Postgres table or Splunk).

**Audit Log Schema:**
```json
{
  "timestamp": "2026-03-24T15:00:00Z",
  "user_id": "SANJEEV",
  "intent": "Material Master Stock Lookup",
  "natural_language_query": "What is the stock of RM-100 in Plant 1010?",
  "auth_context_applied": {"WERKS": ["1010"]},
  "generated_sql": "SELECT LABST FROM MARD WHERE MATNR='RM-100' AND WERKS='1010'",
  "sql_validation_status": "PASSED",
  "rows_returned": 1,
  "execution_time_ms": 142
}
```
*If an LLM attempts to bypass the AuthContext, the `sql_validation_status` will flag `FAILED_AUTH_CHECK`, the query will be blocked, and the Security team can review the log.*

---

## 5. Next Steps for Implementation

1.  **Mock Auth Service:** Build `auth_service.py` to simulate SAP role profiles (returning JSON objects of allowed `BUKRS`, `WERKS`, etc., for different test users).
2.  **SQL Validator Tool:** Implement the `validate_sql(sql_string, auth_context)` function using `sqlglot` to parse the LLM's output and verify the `WHERE` clauses exist before execution.
3.  **Agent Tool Binding:** Integrate `get_auth_context()` as the mandatory first step in the LangGraph Agentic Orchestrator (Pillar 2).