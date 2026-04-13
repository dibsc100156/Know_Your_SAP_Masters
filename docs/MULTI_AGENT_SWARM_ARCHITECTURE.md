# Multi-Agent Domain Swarm Architecture
## SAP Masters — Phase 10 — ✅ LIVE (April 12, 2026)

---

## Overview

The current architecture uses a **single monolithic orchestrator** (`run_agent_loop`) that sequentially executes 8 steps for every query. This works well for single-domain queries but becomes a bottleneck for cross-module enterprise questions.

The **Multi-Agent Domain Swarm** replaces the monolith with a collaborative, multi-agent system where specialized domain agents work in parallel, negotiate with each other, and synthesize their findings into a unified response.

> **Status (April 13, 2026):** All components below are IMPLEMENTED and LIVE on port 8001 (backend) + port 8501 (frontend).

---

## Architecture Diagram

```
User Query
    |
    ▼
┌──────────────────────────────────────────────────────────────┐
│                    PLANNER AGENT                             │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 1. ANALYZE — Query complexity scoring (7 dimensions)    │ │
│  │ 2. ROUTE  — Decide routing strategy                     │ │
│  │ 3. DISPATCH — Assign tasks to agents                    │ │
│  │ 4. MONITOR — Track progress, handle timeouts            │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
                   │
       ┌───────────┼────────────┐
       ▼           ▼            ▼
┌─────────┐ ┌─────────┐ ┌─────────┐
│   BP    │ │   MM    │ │   PUR   │  ← Domain Agents (parallel)
│  Agent  │ │  Agent  │ │  Agent  │
│ (vendor │ │(material│ │  (PO    │
│  +cust) │ │ master) │ │ +sched) │
└────┬────┘────┬────┘────┬────┘
     │          │          │
     │    ┌─────┴─────┐    │
     │    │ SYNTHESIS │◄────┤
     │    │   AGENT   │     │
     │    │           │◄────┴──── QM/WM/SD Agents (as needed)
     │    │1.MERGE    │
     │    │2.DEDUP    │
     │    │3.RANK     │
     │    │4.RESOLVE  │
     │    │5.ANSWER   │
     │    └─────┬─────┘
     └──────────┼──────────────► Unified Response
```

---

## Core Components

### 1. Planner Agent (`swarm/planner_agent.py`)

The Planner is the **intelligent routing layer**. Every query goes through the Planner first.

**Decision Tree:**
```
query
  ├── SINGLE (confidence ≥ 0.85 from one agent)
  │     └──→ Domain Agent → Synthesis → Response
  ├── PARALLEL (2+ agents, score ≥ 0.5, no JOIN needed)
  │     └──→ Domain Agents [parallel] → Synthesis → Response
  ├── CROSS-MODULE (multi-domain JOIN detected)
  │     └──→ CROSS_AGENT + relevant domains → Synthesis → Response
  ├── NEGOTIATION (contains negotiation/QM keywords)
  │     └──→ Specialist Agent(s) → Synthesis → Response
  └── ESCALATE (complexity ≥ 0.6)
        └──→ Monolithic Orchestrator (fallback)
```

**Complexity Scoring (0.0–1.0):**
| Dimension | Weight | Indicators |
|---|---|---|
| Multi-entity | 15% | vendor AND customer, both...and |
| Aggregation | 10% | total, sum, by month, trend |
| Comparison | 10% | compare, vs, top 5, rank |
| Temporal | 15% | last year, FY2024, during crisis |
| Cross-module JOIN | 25% | vendor→material, PO→invoice |
| Negotiation | 10% | negotiate, contract renewal, BATNA |
| QM Long-text | 15% | defect history, quality notification |

---

### 2. Domain Agents (`domain_agents.py` — ✅ IMPLEMENTED)

Each domain agent is a **self-contained specialist** with:

- **Trigger keywords** — What queries it can handle
- **Primary tables** — Its core SAP table expertise
- **Related domains** — Who it can collaborate with
- **Own pipeline** — Schema RAG → SQL Pattern RAG → Execution

| Agent | Domain | Primary Tables | Triggers |
|---|---|---|---|
| `bp_agent` | Business Partner | LFA1, KNA1, BUT000, ADRC | vendor, customer, credit limit |
| `mm_agent` | Material Master | MARA, MARC, MARD, MBEW, MSKA | material, stock, valuation |
| `pur_agent` | Purchasing | EKKO, EKPO, EINA, EINE, EORD | purchase order, open PO, contract |
| `sd_agent` | Sales & Distribution | VBAK, VBAP, LIKP, KONV | sales order, delivery, billing |
| `qm_agent` | Quality Management | QALS, QMEL, MAPL, QAMV | inspection, quality notification, defect |
| `wm_agent` | Warehouse Management | LAGP, LQUA, VEKP, MLGT | warehouse, storage bin, handling unit |
| `cross_agent` | Cross-Module | Dynamic via Graph RAG | spend analysis, P2P, O2C, vendor performance |

---

### 3. Synthesis Agent (`swarm/synthesis_agent.py` — ✅ IMPLEMENTED)

The Synthesis Agent **merges and reconciles** results from multiple domain agents.

**What it does:**
1. **MERGE** — Combines result sets using a deterministic merge key (entity_id + doc_type + date)
2. **DEDUPLICATE** — Same entity from 2 agents = merge, keep both source agents in tags
3. **RANK** — Score by query relevance + cross-domain bonus (records from 2+ agents rank higher)
4. **CONFLICT RESOLUTION** — Same entity, different value across agents → flag + resolve (use highest)
5. **MASKING** — Apply AuthContext field masking post-merge
6. **ANSWER** — Generate natural language synthesis with per-agent attribution

---

## Swarm Execution Flows

### Flow 1: Single Domain (e.g., "Show my open POs")
```
Query → Planner (SINGLE) → PUR_AGENT [sequential]
                              └──→ Synthesis (pass-through)
                                  └──→ Response
```

### Flow 2: Parallel Domains (e.g., "Compare vendor vs customer overdue invoices")
```
Query → Planner (PARALLEL)
            ├──→ BP_AGENT [parallel] ─┐
            └──→ PUR_AGENT [parallel] ─┴──→ Synthesis (merge)
                                              └──→ Response
```

### Flow 3: Cross-Module (e.g., "Vendor delivery performance vs quality")
```
Query → Planner (CROSS_MODULE)
            ├──→ BP_AGENT [parallel] ─┐
            ├──→ PUR_AGENT [parallel] ─┤
            └──→ CROSS_AGENT (graph traversal)
                                              └──→ Synthesis (merge + rank)
                                                     └──→ Response
```

### Flow 4: Negotiation (e.g., "Brief me for vendor contract renewal")
```
Query → Planner (NEGOTIATION)
            └──→ Specialist path:
                 ├──→ BP_AGENT (CLV calculation)
                 ├──→ PUR_AGENT (PSI scorecard)
                 └──→ SD_AGENT (market data)
                        └──→ Synthesis (negotiation brief)
                               └──→ Response
```

---

## Key Design Decisions

### 1. Swarm vs Monolith: When to Use Which?

| Scenario | Mode | Reason |
|---|---|---|
| Simple single-domain query | Monolith | Lower latency, no coordination overhead |
| Multi-domain enterprise query | Swarm | Parallel execution, better results |
| Cross-module JOIN-heavy query | Swarm | Graph RAG + Synthesis gives better JOINs |
| Time-sensitive single entity | Monolith | Swarm overhead not justified |
| Unknown domain / ambiguous query | Swarm | Planner picks best agents automatically |

**API Usage:**
```python
# Use swarm (multi-agent)
result = run_agent_loop(query, auth, use_swarm=True)

# Use monolith (single orchestrator)
result = run_agent_loop(query, auth, use_swarm=False)
```

### 2. Inter-Agent Communication
Domain agents currently communicate only through the Synthesis Agent (star topology). Future enhancement: direct agent-to-agent negotiation via a shared message bus.

### 3. Security in Swarm Mode
- Each domain agent receives the `SAPAuthContext`
- Synthesis Agent re-applies masking after merge (agents may miss fields)
- Threat Sentinel evaluates the **Planner's decision**, not individual agents (single evaluation point)
- `cross_agent` has elevated graph traversal — monitored by Threat Sentinel for hop depth

### 4. Timeout & Graceful Degradation
- Each domain agent has a 30-second timeout
- If an agent times out, Synthesis proceeds with available results
- Error results from agents are logged but don't block synthesis
- Fallback to monolithic orchestrator if ALL agents fail

---

## Implementation Status

| Component | File | Status |
|---|---|---|
| Domain Agents (7 specialists) | `domain_agents.py` | ✅ Working |
| Planner Agent + Complexity Analyzer | `swarm/planner_agent.py` (19KB) | ✅ **LIVE** |
| Synthesis Agent (merge + rank + conflicts) | `swarm/synthesis_agent.py` (16KB) | ✅ **LIVE** |
| Swarm entry point | `swarm/__init__.py` (2KB) | ✅ **LIVE** |
| Orchestrator `use_swarm` flag + API wiring | `orchestrator.py`, `api/endpoints/chat.py` | ✅ **LIVE** |
| Frontend default `use_swarm=True` + swarm UI | `frontend/app.py` | ✅ **LIVE** |
| Bug: `tables_involved` early init | `orchestrator.py` | ✅ Fixed |
| Bug: `cross_agent` empty guard | `domain_agents.py` | ✅ Fixed |
| Bug: `abs(min(vals), 0.01)` syntax | `synthesis_agent.py` | ✅ Fixed |
| Inter-Agent Message Bus | — | 🚧 Planned |
| Agent-to-Agent Negotiation Protocol | — | 🚧 Planned |
| Swarm Autoscaling (Celery workers) | — | 🚧 Planned |

---

## Files Reference

| File | Purpose |
|---|---|
| `swarm/planner_agent.py` | Planner Agent + Routing + Complexity Analyzer |
| `swarm/synthesis_agent.py` | Synthesis Agent + Merge + Conflict Resolution |
| `swarm/__init__.py` | `run_swarm()` convenience entry point |
| `domain_agents.py` | Domain Agent base class + 7 concrete agents |
| `orchestrator.py` | `use_swarm=True/False` flag gates swarm entry |
