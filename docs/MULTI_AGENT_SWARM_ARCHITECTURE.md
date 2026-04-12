# Multi-Agent Domain Swarm Architecture
## SAP Masters â Phase: PLANNED

---

## Overview

The current architecture uses a **single monolithic orchestrator** (`run_agent_loop`) that sequentially executes 8 steps for every query. This works well for single-domain queries but becomes a bottleneck for cross-module enterprise questions.

The **Multi-Agent Domain Swarm** replaces the monolith with a collaborative, multi-agent system where specialized domain agents work in parallel, negotiate with each other, and synthesize their findings into a unified response.

---

## Architecture Diagram

```
User Query
    â
    â¼
âââââââââââââââââââââââââââââââââââââââââââââââââââââââ
â              PLANNER AGENT                          â
â  âââââââââââââââââââââââââââââââââââââââââââââââââââ â
â  â 1. ANALYZE â Query complexity scoring            â â
â  â 2. ROUTE  â Decide routing strategy              â â
â  â 3. DISPATCH â Assign tasks to agents             â â
â  â 4. MONITOR â Track progress, handle timeouts    â â
â  âââââââââââââââââââââââââââââââââââââââââââââââââââ â
ââââââââââââââââââââ¬âââââââââââââââââââââââââââââââââââ
                   â
       âââââââââââââ¼âââââââââââââ
       â¼           â¼            â¼
 ââââââââââââ ââââââââââââ ââââââââââââ
 â  BP      â â   MM     â â  PUR     â  â Domain Agents
 â  Agent   â â  Agent   â â  Agent   â    (parallel)
 â  (vendor â â (materialâ â  (PO     â
 â   + cust)â â  master) â â  +sched) â
 ââââââ¬ââââââ ââââââ¬ââââââ ââââââ¬ââââââ
      â            â            â
      â   ââââââââââ´âââââââââ   â
      â   â  SYNTHESIS      ââ'âââ
      â   â  AGENT         ââ'ââââââââ QM/WM/SD Agents (as needed)
      â   â                 â
      â   â 1. MERGE recordsâ
      â   â 2. DEDUPLICATE â
      â   â 3. RANK by rel. â
      â   â 4. RESOLVE      â
      â   â    conflicts   â
      â   â 5. ANSWER       â
      â   âââââââââââââââââââ
      ââââââââââââââââââââââââº Unified Response
```

---

## Core Components

### 1. Planner Agent (`swarm/planner_agent.py`)

The Planner is the **intelligent routing layer**. Every query goes through the Planner first.

**Decision Tree:**
```
query
  ââ SINGLE (confidence â¥ 0.85 from one agent)
  â     âââ Domain Agent â Synthesis â Response
  ââ PARALLEL (2+ agents, score â¥ 0.5, no JOIN needed)
  â     âââ Domain Agents [parallel] â Synthesis â Response
  ââ CROSS-MODULE (multi-domain JOIN detected)
  â     âââ CROSS_AGENT + relevant domains â Synthesis â Response
  ââ NEGOTIATION (contains negotiation/QM keywords)
  â     âââ Specialist Agent(s) â Synthesis â Response
  ââ ESCALATE (complexity â¥ 0.6)
        âââ Monolithic Orchestrator (fallback)
```

**Complexity Scoring (0.0â1.0):**
| Dimension | Weight | Indicators |
|---|---|---|
| Multi-entity | 15% | vendor AND customer, both...and |
| Aggregation | 10% | total, sum, by month, trend |
| Comparison | 10% | compare, vs, top 5, rank |
| Temporal | 15% | last year, FY2024, during crisis |
| Cross-module JOIN | 25% | vendorâmaterial, POâinvoice |
| Negotiation | 10% | negotiate, contract renewal, BATNA |
| QM Long-text | 15% | defect history, quality notification |

---

### 2. Domain Agents (`domain_agents.py` â already implemented)

Each domain agent is a **self-contained specialist** with:

- **Trigger keywords** â What queries it can handle
- **Primary tables** â Its core SAP table expertise
- **Related domains** â Who it can collaborate with
- **Own pipeline** â Schema RAG â SQL Pattern RAG â Execution

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

### 3. Synthesis Agent (`swarm/synthesis_agent.py`)

The Synthesis Agent **merges and reconciles** results from multiple domain agents.

**What it does:**
1. **MERGE** â Combines result sets using a deterministic merge key (entity_id + doc_type + date)
2. **DEDUPLICATE** â Same entity from 2 agents = merge, keep both source agents in tags
3. **RANK** â Score by query relevance + cross-domain bonus (records from 2+ agents rank higher)
4. **CONFLICT RESOLUTION** â Same entity, different value across agents â flag + resolve (use highest)
5. **MASKING** â Apply AuthContext field masking post-merge
6. **ANSWER** â Generate natural language synthesis with per-agent attribution

---

## Swarm Execution Flows

### Flow 1: Single Domain (e.g., "Show my open POs")
```
Query â Planner (SINGLE) â PUR_AGENT [sequential]
                              ââ Synthesis (pass-through)
                                  ââ Response
```

### Flow 2: Parallel Domains (e.g., "Compare vendor vs customer overdue invoices")
```
Query â Planner (PARALLEL)
            ââ BP_AGENT [parallel] ââ
            ââ PUR_AGENT [parallel]ââ¼â Synthesis (merge)
                                       ââ Response
```

### Flow 3: Cross-Module (e.g., "Vendor delivery performance vs quality")
```
Query â Planner (CROSS_MODULE)
            ââ BP_AGENT [parallel] ââ
            ââ PUR_AGENT [parallel] ââ¤
            ââ CROSS_AGENT (graph traversal)
                                       ââ Synthesis (merge + rank)
                                              ââ Response
```

### Flow 4: Negotiation (e.g., "Brief me for vendor contract renewal")
```
Query â Planner (NEGOTIATION)
            ââ Specialist path:
                 ââ BP_AGENT (CLV calculation)
                 ââ PUR_AGENT (PSI scorecard)
                 ââ SDAgent (market data)
                        ââ Synthesis (negotiation brief)
                               ââ Response
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
- Threat Sentinel evaluates the * Planner's decision*, not individual agents (single evaluation point)
- `cross_agent` has elevated graph traversal â monitored by Threat Sentinel for hop depth

### 4. Timeout & Graceful Degradation
- Each domain agent has a 30-second timeout
- If an agent times out, Synthesis proceeds with available results
- Error results from agents are logged but don't block synthesis
- Fallback to monolithic orchestrator if ALL agents fail

---

## Files Reference

| File | Purpose |
|---|---|
| `swarm/planner_agent.py` | Planner Agent + Routing + Complexity Analyzer |
| `swarm/synthesis_agent.py` | Synthesis Agent + Merge + Conflict Resolution |
| `swarm/__init__.py` | `run_swarm()` convenience entry point |
| `domain_agents.py` | Domain Agent base class + 7 concrete agents |
| `orchestrator.py` | `use_swarm=True/False` flag gates swarm entry |

---

## Status

| Component | Status |
|---|---|
| Domain Agents (`domain_agents.py`) | â Implemented |
| Planner Agent (`swarm/planner_agent.py`) | â **NEW â IMPLEMENTED** |
| Synthesis Agent (`swarm/synthesis_agent.py`) | â **NEW â IMPLEMENTED** |
| Swarm entry point (`swarm/__init__.py`) | â **NEW â IMPLEMENTED** |
| Orchestrator `use_swarm` flag | â **NEW â IMPLEMENTED** |
| Inter-Agent Message Bus | ð§ Planned |
| Agent-to-Agent Negotiation Protocol | ð§ Planned |
| Swarm Autoscaling (Celery workers) | ð§ Planned |
