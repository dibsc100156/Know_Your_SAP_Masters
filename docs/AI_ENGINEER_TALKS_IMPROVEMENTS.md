# AI Engineer World's Fair — Video Insights & KYSM Improvement Roadmap

**Compiled:** April 20, 2026
**Source:** 7 talks from AI Engineer World's Fair (July 2025)
| # | Talk | Speaker | Duration | Views | Key Theme |
|---|------|---------|----------|-------|-----------|
| 1 | 3 ingredients for building reliable enterprise agents | Harrison Chase (LangChain) | 20:54 | 54K | Agent reliability equation |
| 2 | Practical GraphRAG | Michael Hunger + Jesús Barrasa + Stephen Chin (Neo4j) | 19:46 | 40K | GraphRAG construction + retrieval |
| 3 | Layering every technique in RAG | David Karam (Pi Labs / ex-Google Search) | 20:22 | 17K | RAG quality engineering layers |
| 4 | Building a Smarter AI Agent with Neural RAG | Will Bryk (Exa.ai) | 18:42 | 19K | Neural search for AI agents |
| 5 | Agentic GraphRAG: AI's Logical Edge | Stephen Chin (Neo4j) | 15:27 | 34K | Agentic GraphRAG integration |
| 6 | Agents vs Workflows: Why Not Both? | Sam Bhagwat (Mastra.ai) | 15:36 | 22K | Agent/workflow composition |
| 7 | Agentic GraphRAG: Simplifying Retrieval | Zach Blumenfeld (Neo4j) | 15:25 | 13K | Entity extraction + graph analytics |

---

## Cross-Talk Themes — The Emerging Consensus

These 7 talks, despite different speakers and companies, converge on a **unified mental model** for production RAG systems:

```
┌─────────────────────────────────────────────────────┐
│  USER QUERY                                          │
│    ↓                                                 │
│  COMPLEXITY ROUTING (TRIVIAL→SIMPLE→COMPLEX→EXPERT)  │  ← Phase L5
│    ↓                                                 │
│  QUALITY ENGINEERING LOOP                             │  ← David's framework
│  loss analysis → which layer is failing?              │
│    ↓                                                 │
│  LAYERED RETRIEVAL                                    │
│  [BM25] → [Vector] → [Graph Traversal] → [Cypher]   │  ← David Karam
│    ↓                                                 │
│  GRAPH CONTEXT (entity extraction + relationships)    │  ← Neo4j (Zach+Stephen)
│    ↓                                                 │
│  AGENTIC REASONING (multi-step, tool use, memory)     │  ← Harrison Chase
│    ↓                                                 │
│  HUMAN-IN-LOOP (reversibility, approval, observability)│  ← Harrison Chase
│    ↓                                                 │
│  ANSWER (explainable, auditable, role-aware)          │
└─────────────────────────────────────────────────────┘
```

**The shared thesis:** No single technique (vector RAG, graph RAG, agents, or workflows) is sufficient alone. The power comes from layering them correctly — and the right layering depends on the query's complexity tier.

---

## Key Video Insights

### Insight 1 — The Agent Reliability Equation (Harrison Chase)

Enterprise agents succeed or fail based on three variables:

> **(Probability of Success × Value When Right) > Cost of Running + Cost When Wrong**

| Variable | How to maximize |
|---|---|
| **Value when right** | Pick high-value verticals; shift from Q&A to long-running ambient agents |
| **Probability of success** | Make agents deterministic (workflows + agents, not pure prompting); invest in observability |
| **Cost when wrong** | Build reversibility (commits, PRs); keep humans in loop for high-stakes actions |

**KYSM relevance:** Our system's value is highest when it handles complex multi-table SAP queries (EXPERT tier) correctly. Cost when wrong is high if wrong SQL reaches SAP. We have reversibility via the CIBA approval flow (Phase 15).

---

### Insight 2 — RAG Quality Engineering Loop (David Karam)

David (ex-Google Search) prescribes a systematic approach:

```
1. Set quality bar (easy/medium/hard query sets)
2. Baseline with simplest approach
3. Loss analysis — what's specifically broken?
4. Only add complexity where it fixes a specific failure
```

**The most underrated technique:** BM25 keyword matching — cheap, fast, handles keyword queries well. Vector search doesn't replace it.

**The biggest conceptual error:** Confusing **relevance** with **ranking**. PageRank is about prominence (corpus structure), not relevance (query match). These are orthogonal signals.

**KYSM relevance:** We skip BM25 entirely. Our Schema RAG goes straight from text query to vector similarity — but for keyword queries like `"vendor for company code 1000"`, BM25 would be faster and more precise. BM25 is a free win.

---

### Insight 3 — GraphRAG Construction = 3 Phases (Neo4j / Michael Hunger)

GraphRAG has two sides:
1. **Build:** Lexical graph → Entity extraction (LLM) → Graph enrichment (community detection)
2. **Search:** Entry point discovery → Graph traversal → Return subgraph context

**The cross-document intelligence unlock:** Community detection across documents reveals topics that span multiple documents — without any document explicitly mentioning all of them. This is impossible with flat vector RAG.

**KYSM relevance:** Our Meta-Path Library is the SAP-domain equivalent of community detection. We already have 14 meta-paths covering cross-module JOINs. But we could add **cross-document topic clustering** across SAP note categories, message types, and transaction codes.

---

### Insight 4 — Neural Search for AI Agents (Will Bryk / Exa.ai)

Search engines were built for **slow, lazy humans** who type short keyword queries. AI agents are the opposite:

| Human | AI Agent |
|---|---|
| Simple keyword queries | Paragraph-long context-rich queries |
| Wants a few links to click | Wants comprehensive results (all matches, not top-10) |
| Can't process 10,000 results | Processes thousands in parallel |
| Needs UI/UX | Needs precise, controllable information |

**The inevitable pairing:** LLM + Search. LLMs physically cannot store the web in their weights. The web is also constantly updating. Search is forever necessary.

**KYSM relevance:** SAP master data is our "web." Our agents need to search across 18 domains, 100+ tables, and millions of rows. We need the agentic search paradigm — not the human search paradigm.

---

### Insight 5 — Agentic GraphRAG Reduces Hallucinations (Stephen Chin)

Hallucinations are the #1 agentic failure mode — and they're compounded by reasoning chains that look plausible but are wrong.

**The solution:** Give the LLM structured graph context instead of text chunks. The reasoning chain becomes auditable:
- Why did you include this table? → "Because it's connected to the vendor node via the purchasing org relationship"
- What other tables did you consider? → "I traversed 2 hops from LFA1 and found EKKO, EKPO, but excluded BSEG because..."

**MCP as the integration layer:** Model Context Protocol standardizes how agents connect to graph databases. Neo4j has MCP servers for Cypher generation and memory.

**KYSM relevance:** We have the architecture for this already (security context as graph, schema as graph). The gap: our LLM answers don't cite the exact graph traversal path they used. Adding graph provenance to answers would dramatically reduce hallucinations.

---

### Insight 6 — Agents vs Workflows Composition (Sam Bhagwat / Mastra)

The framework war (LangChain vs LangGraph, agent vs workflow) is a **distraction**. The real power is in composition:

```
Agents have tools
Workflows have steps

An agent CAN be a step in a workflow
A workflow CAN be a tool an agent uses
An agent CAN be a tool another agent uses
```

**Fluent APIs beat graph-node APIs:** Don't force your team to learn graph theory to write workflows. Readable code is a team sport.

**KYSM relevance:** Our orchestrator mixes agentic loops (STEP 6 self-critique, STEP 8 QM semantic) with deterministic steps (STEP 4 SQL assembly). We should formalize which parts are workflow (deterministic SQL assembly) vs agent (schema discovery, self-healing) and make the boundary explicit.

---

### Insight 7 — Entity Extraction from Documents (Zach Blumenfeld)

Pure document embeddings fail on analytics because they can't do aggregation, precise filtering, or relationship finding.

**The pipeline:**
1. Define schema (Person, Skill, Accomplishment, Domain)
2. LLM extracts entities + relationships from text → JSON
3. Load into graph
4. Agent generates Cypher queries against schema

**Graph beats RDBMS for schema evolution:** Adding new relationship types (e.g., collaboration data) doesn't require schema migration — just new edges.

**KYSM relevance:** Our DDIC metadata is already structured. But we could apply entity extraction to:
- SAP error messages → map to known root causes
- Transaction code descriptions → enrich our schema with business context
- SAP notes and OSS messages → build a cross-document knowledge graph

---

## Recommended Improvements for KYSM (✅ All 10 Completed)

### ✅ Priority 1 — Fix Complexity Router (TRIVIAL over-triggering)

**Problem:** All test queries land in TRIVIAL (score 0.0). Nine skip steps fire for queries that should be SIMPLE or COMPLEX.

**Root cause:** COMPLEXITY_INDICATORS patterns are too conservative. Keywords like "vendor", "payment", "material" trigger no dimension score.

**Fix:**
```
# Add to COMPLEXITY_INDICATORS:
'multi_entity':         ['vendor.*customer', 'material.*plant', 'supplier.*material', ...]
'cross_module_join':    ['join.*with', 'link.*to', 'relationship.*between', ...]
'aggregation':         ['total.*of', 'sum.*of', 'count.*of', 'average.*of', ...]
'temporal':            ['last.*year', 'this.*quarter', 'ytd', 'fy2024', ...]
```

**Verification:** After fix, expected distribution:
- `"vendor payment terms"` → SIMPLE (0.25)
- `"open POs above 50k"` → SIMPLE (0.35)
- `"vendor performance with quality + delivery"` → COMPLEX (0.55)
- `"analyze vendor-customer relationships with revenue trend"` → EXPERT (0.75)

---

### ✅ Priority 2 — Add BM25 Keyword Retrieval (free precision win)

**Problem:** Schema RAG goes straight from natural language to vector similarity. Keyword queries (e.g., `"LFA1 vendor"`, `"company code 1000"`) are handled by semantic similarity — slower and less precise than BM25.

**Fix:** Add BM25 as a first-pass filter before vector search:

```
Query
  ↓
[Is this a keyword query?] → YES → BM25 retrieval → return top-K
  ↓ NO
[Vector similarity search] → return top-K
  ↓
[Both results → rerank by fused score]
```

**Expected improvement:** 15-30% precision improvement on keyword-heavy queries. BM25 is O(n) where n = vocabulary size, vs O(d) for embedding + cosine.

---

### ✅ Priority 3 — Add Per-Tier Quality Metrics Dashboard

**Problem:** We track overall query success rate but not breakdown by complexity tier. TRIVIAL queries should auto-pass at near-100%. EXPERT queries need the full pipeline.

**New monitoring fields to add:**

| Metric | Description |
|---|---|
| `tier_distribution` | Count of queries per tier per day |
| `skip_step_coverage` | % of STEP 1/1.5/3 skips that are intentional (routed correctly) vs accidental (broke something) |
| `voting_threshold_adopted` | % of queries using tier-adaptive threshold vs fixed 0.70 |
| `avg_confidence_by_tier` | Mean confidence score per tier — should decrease monotonically TRIVIAL→EXPERT |
| `schema_rag_hit_rate_by_tier` | % of queries that skip Schema RAG vs use it |

---

### ✅ Priority 4 — Graph Provenance in Answers (explainability)

**Problem:** Answers cite SQL but don't explain the graph traversal path that produced the table selection.

**Fix:** Add a `graph_provenance` field to answers:

```python
result_dict["graph_provenance"] = {
    "primary_table": "LFA1",
    "traversal_path": ["LFA1", "LFB1", "EKKO"],
    "join_reason": "LFA1 → LFB1 (company code) → EKKO (PO history)",
    "tables_explored": ["LFA1", "LFB1", "LFBK", "EKKO", "EKPO"],
    "tables_excluded": ["BSEG", "MKTF"],  # didn't need AP/AR side
    "confidence_reason": "3-hop path with high centrality scores"
}
```

**Expected impact:** Reduces hallucination surface area — agent can be questioned on each step of the traversal.

---

### ✅ Priority 5 — CIBA Tier Configuration (human-in-loop by routing tier)

**Current:** CIBA approval fires on Sentinel block/tighten verdicts — query-agnostic.

**Improved:** Make CIBA behavior routing-tier-aware:

| Tier | CIBA behavior |
|---|---|
| TRIVIAL | Auto-proceed (0 approval needed) |
| SIMPLE | Soft warning in response header |
| COMPLEX | CIBA pending if Sentinel fires block |
| EXPERT | Always require CIBA approval before execution |

---

### ✅ Priority 6 — MCP Server for KYSM (tool exposure standard)

**Opportunity:** Expose KYSM's core capabilities via MCP so any MCP-compatible agent (ADK, LangGraph, Mastra, etc.) can use KYSM as a tool.

**MCP endpoints to expose:**
1. **schema_lookup** — natural language → Cypher for SAP DDIC
2. **sql_pattern_match** — query → proven SQL template
3. **graph_traverse** — multi-hop table discovery
4. **auth_context_filter** — role → row/column mask

This turns KYSM into a **tool that other enterprise agents can call** — not just an API endpoint for Streamlit.

---

### ✅ Priority 7 — BM25 Scoring for Schema RAG (relevance signal)

**Current:** Schema RAG uses only vector cosine similarity for table ranking.

**Fix:** Add BM25 as a second signal:

```
table_score = α × cosine_similarity(query_embed, table_embed)
           + β × BM25_score(query, table_description)
           + γ × centrality_score(table)      # graph structure signal
```

**Why this matters:** David Karam's insight — relevance ≠ similarity. BM25 captures exact keyword matches (e.g., "quality inspection" should exactly match QALS). Cosine similarity captures semantic relatedness. Combining both is strictly better.

---

### ✅ Priority 8 — SAP Note / OSS Message Knowledge Graph

**Opportunity:** Use LLM entity extraction on raw SAP note text, OSS messages, and error codes to build a cross-document knowledge graph.

**Architecture:**
```
SAP Note #2345678
  → LLM extracts:
    - Error code: RAISE 033
    - Module: FI (Financial Accounting)
    - Symptom: "Company code not found"
    - Root cause: "Missing T001 entry"
    - Solution: "Create company code in T001"
  → Stored as graph nodes + relationships
  → Agent queries graph when user asks about an error code
```

This enables question-answering over SAP operational knowledge — a separate but complementary knowledge base to our DDIC graph.

---

### ✅ Priority 9 — Dynamic Tool Injection by Tier

**Problem:** Agents given too many tools perform worse (Sam Bhagwat / Mastra finding).

**Fix:** Tier-based tool set:

| Tier | Tools enabled |
|---|---|
| TRIVIAL | `sql_pattern_match` + `execute_sql` (2 tools) |
| SIMPLE | + `schema_lookup` + `mask_results` |
| COMPLEX | + `graph_traverse` + `all_paths_explore` + `self_critique` |
| EXPERT | All 12 tools + `qm_semantic` + `temporal_engine` + `negotiation_brief` |

**Implementation:** `ComplexityRouter` already has `skip_steps`. Extend to `enabled_tools` mapping per tier.

---

### ✅ Priority 10 — Fluent Orchestrator Syntax (readability)

**Current problem (per Sam Bhagwat):** Graph-node/edge APIs force developers to think in graph terms. Our orchestrator's `run_agent_loop()` is readable but the tool registration uses declarative dict structures that are opaque.

**Fix:** Introduce fluent step notation:

```python
orchestrator = (
    OrchestratorBuilder()
    .step("schema_discovery", if_tier_not("trivial"))
    .step("graph_enhanced_schema", if_tier_in("simple", "complex", "expert"))
    .step("sql_pattern_match", always)
    .step("graph_traversal", if_tier_in("complex", "expert"))
    .step("sql_assembly", always)
    .step("self_critique", if_confidence_below(0.70))
    .step("execute", always)
    .build()
)
```

This makes the orchestration flow visible at a glance — critical for a team of developers maintaining the system.

---

## Summary — Impact Matrix

| Improvement | Status | Alignment with Talks |
|---|---|---|
| Fix Complexity Router | ✅ Completed | David Karam — loss analysis |
| Add BM25 Keyword Retrieval | ✅ Completed | David Karam — layered retrieval |
| Per-Tier Quality Metrics | ✅ Completed | Harrison Chase — observability |
| Graph Provenance in Answers | ✅ Completed | Stephen Chin — explainability |
| CIBA Tier Configuration | ✅ Completed | Harrison Chase — cost when wrong |
| MCP Server for KYSM | ✅ Completed | Stephen Chin — MCP standard |
| BM25 Schema Scoring | ✅ Completed | David Karam — relevance ≠ similarity |
| SAP Note Knowledge Graph | ✅ Completed | Zach Blumenfeld — entity extraction |
| Dynamic Tool Injection by Tier | ✅ Completed | Sam Bhagwat — tool overload |
| Fluent Orchestrator Syntax | ✅ Completed | Sam Bhagwat — readable code |

**Total: 10 improvements across 4 effort tiers fully implemented!** The codebase is now deeply aligned with state-of-the-art agentic engineering principles as presented at the AI Engineer World's Fair.

---

*Compiled from 7 AI Engineer World's Fair talks. Speaker credits: Harrison Chase (LangChain), Michael Hunger + Jesús Barrasa + Stephen Chin (Neo4j), David Karam (Pi Labs), Will Bryk (Exa.ai), Sam Bhagwat (Mastra.ai), Zach Blumenfeld (Neo4j).*