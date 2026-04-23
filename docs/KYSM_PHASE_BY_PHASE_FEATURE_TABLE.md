# KYSM Phase-by-Phase Feature Table
**Last Updated:** April 23, 2026 | Project: Know Your SAP Masters (KYSM)

---

## Overview

This document gives a compact phase-by-phase feature map of the KYSM architecture, aligned to:
- `docs/AGENTIC_DESIGN_PATTERNS_KYSM.md`
- `docs/LEVEL5_ROADMAP.md`

It is intended as a fast reference for understanding what each phase adds, why it exists, and what user-visible or system-visible capability it enables.

---

## Core 5-Pillar + Extended Execution Stack

| Phase | Name | What it Adds | Key Capability Enabled | Key Files / Components | Status |
|---|---|---|---|---|---|
| 0 | Meta-Path Match | Precomputed SAP join-path fast path | Template-based instant routing for common enterprise questions | `meta_path_library.py`, `orchestrator_tools.py` | ✅ Complete |
| 1 | Schema RAG | Semantic retrieval over DDIC metadata | Finds relevant SAP tables for the user query | Qdrant schema search, schema lookup tools | ✅ Complete |
| 1.5 | Graph Embedding Search | Node2Vec + text-hybrid graph retrieval | Better table discovery using graph structure + semantics | `graph_embedding_store.py` | ✅ Complete |
| 1.75 | QM Semantic Search | Semantic search over quality notification long text | Deep retrieval for QM / quality workflows | QM semantic search components | ✅ Complete |
| 2 | SQL Pattern RAG | Retrieval of proven SQL templates/patterns | Reuses known-good SAP SQL patterns by domain | SQL pattern store / lookup | ✅ Complete |
| 2b | Temporal Detection | Date/fiscal-time detection and filter generation | Temporal-aware query execution | temporal detection logic | ✅ Complete |
| 2c | Temporal Engine | Business time intelligence (FY, CLV, SPI, cycles) | Time-aware enterprise analysis | temporal engine components | ✅ Complete |
| 2d | Negotiation Briefing | Commercial/negotiation insight layer | CLV, churn, BATNA, PSI-style business guidance | negotiation tools / briefing layer | ✅ Complete |
| 3 | Graph RAG | Join-path search over SAP graph topology | Best-path join assembly across modules | `graph_store.py`, `AllPathsExplorer`, Memgraph/NetworkX stack | ✅ Complete |
| 4 | SQL Assembly | Final SQL composition with constraints | Safe SAP SQL generation with tenant/auth/time filters | orchestrator SQL assembly path | ✅ Complete |
| 5 | Critique Gate | Structured SQL validation rules | Blocks weak/unsafe SQL before execution | critique agent / validation rules | ✅ Complete |
| 5.5 | Validation Harness | Dry-run syntax validation + autonomous fix loop | Detects and fixes SQL failures before execution | validation harness, executor dry-run | ✅ Complete |
| 6 | Self-Healing | Rule-based SQL healing | Repairs failed SQL using known error strategies | self-healer components | ✅ Complete |
| 6b | Memory Compounding | Stores healed SQL back into knowledge store | System learns from successful healing | Qdrant pattern write-back | ✅ Complete |
| 6c | Proactive Threat Sentinel | Threat detection and dynamic auth tightening | Detects risky behavior and blocks/escalates | `security_sentinel.py` | ✅ Complete |
| 7 | Execution | Executes SAP query plan | Returns actual data from executor path | `sql_executor.py` | 🟡 Partial |
| 8 | Result Masking | Role-aware data redaction | Enforces row/column privacy and compliance | AuthContext masking path | ✅ Complete |
| 9 | Frontend Modernization | Rich UI panels and architecture visibility | Confidence, pillar, temporal, negotiation, trace UI | `frontend/app.py` | ✅ Complete |

---

## Advanced Agentic Phases

| Phase | Name | What it Adds | Key Capability Enabled | Key Files / Components | Status |
|---|---|---|---|---|---|
| 10 | Multi-Agent Domain Swarm | Planner + domain agents + synthesis | Parallel specialist reasoning across SAP domains | swarm planner, synthesis agent | ✅ Complete |
| 11 | Meta-Harness Loop | Failure analysis → recommendation → patch loop | Self-improvement workflow for recurring failures | `meta_harness_loop.py`, failure trigger | ✅ Complete |
| 12 | Quality Evaluator | Structured scoring of outputs and trajectories | Measures answer quality and execution adherence | `quality_evaluator.py` | ✅ Complete |
| 13 | Inter-Agent Message Bus | Redis-backed message exchange | Agent-to-agent structured communication | `message_bus.py` | ✅ Complete |
| 13+ | Retrieval Quality Architecture | Retrieval bundle + reranker + critic + retrieval profiles | Higher-quality RAG before generation | retrieval bundle / reranker / critic path | ✅ Complete |
| 13b | Negotiation Protocol | Multi-phase conflict resolution | Resolves conflicting agent assertions | `negotiation_protocol.py` | ✅ Complete |
| 14 | Voting Executor | Multi-path parallel SQL generation | Consensus-based execution planning | Voting Executor path A/B/C/D | ✅ Complete |
| 15 | CIBA Approval Flow | Async approval / denial / override loop | Human-in-the-loop for risky operations | `ciba_approval_store.py`, `ciba.py` | ✅ Complete |
| 16 | Learning & Adaptation | Healed pattern reuse and path-D fast recall | System adapts from prior successful repairs | healed SQL pattern reuse | ✅ Complete |
| 17 | Semantic Answer Validation | Semantic cross-checking of outputs | Verifies results against intended meaning | answer validation layer | ✅ Complete |
| 18 | Exploration & Discovery | Dynamic FK probing + decomposition | Discovery-first planning for unfamiliar requests | exploration engine, hierarchical decomposer | ✅ Complete |
| 19 | Agent-as-Tool Override | Controlled tool-mode suppression of autonomy | Agents can be constrained and invoked like tools | `agent_tool_mode.py` | ✅ Complete |
| 20 | Resource-Aware Cost Router | Cost-aware tier routing and bypass | Optimizes latency/cost vs. quality | `router_cost_tracker.py` | ✅ Complete |
| 21 | Formal Revision Loop | Bounded iterative critique/repair loop | Structured correction with exit conditions | `formal_revision_loop.py` | ✅ Complete |
| 22 | Dynamic Query Prioritization | Urgency/recency/authority queue scoring | Smarter sync/async request ordering | `query_priority_scorer.py` | ✅ Complete |
| 23 | Safety Guardrails (Standalone) | Dedicated layered safety contract | Clean separation of safety policy from execution | `safety_guardrails.py` | ✅ Complete |
| 24 | Episodic Memory Store | Session scratchpad + duplicate-turn + recent results | Better short-horizon continuity | `episodic_memory.py` | ✅ Complete |
| 24+ | Unified Memory Architecture | MemoryContext + policy + orchestration + write-back | Unified short-term / episodic / persistent memory | `memory_context.py`, `memory_orchestrator.py`, `memory_policy.py`, `memory_writeback.py` | ✅ Complete |

---

## Architecture Follow-Through Phases

| Phase | Name | What it Adds | Key Capability Enabled | Key Files / Components | Status |
|---|---|---|---|---|---|
| 1+ | Prompt Chain Controller Architecture | Formal chain steps, quality gates, retry/stop policy, chain trace | Explicit prompt-chain orchestration | `chain_types.py`, `chain_controller.py`, `chain_quality_gates.py`, `chain_retry_policy.py` | ✅ Complete |
| 31 | Adaptive Replanning Architecture | ExecutionPlan + replanner + revision tracking | Mid-flight plan adaptation based on findings | planning contracts, replanner, plan trace | ✅ Complete |
| 32 | Per-Query Goal State Architecture | QueryGoal + goal tracker + drift detection | Tracks whether execution stays aligned to intent | `query_goal.py`, `goal_tracker.py`, `goal_drift_detector.py` | ✅ Complete |
| 33 | Recovery Escalation Architecture | RecoveryCase + orchestrated escalation lanes | Graceful fallback instead of hard failure | `recovery_case.py`, `recovery_orchestrator.py`, `recovery_router.py` | ✅ Complete |
| 34 | Reasoning Trace Architecture | Structured reasoning runtime + policy + trace surfacing | Explainable step-by-step decision flow | `reasoning_runtime.py`, `reasoning_trace.py`, `reasoning_policy.py` | ✅ Complete |
| 35 | Automated Golden-Set Regression | Eval runner + change-impact + regression gate | Automated quality protection against regressions | eval runner / regression gate stack | ✅ Complete |
| 36 | Delivery Foundation | Delivery envelope + idempotency model | Reliable structured agent result delivery | delivery envelope schema | ✅ Complete |
| 37 | Message Reliability | ACK/NACK, replay, DLQ, sweeper | Durable message delivery and recovery | message reliability layer | ✅ Complete |
| 38 | Consumer Group Bus | Redis Streams consumer-group implementation | Real queue semantics for inter-agent messaging | `XREADGROUP`, `XACK`, `XAUTOCLAIM`, DLQ flow | ✅ Complete |

---

## Pattern-to-Phase Crosswalk

| Pattern Area | Primary Phases |
|---|---|
| Prompt Chaining | 1+, 31, 21 |
| Routing | L5, 18, 20 |
| Parallelization | 10, 14 |
| Reflection / Critique | 5, 5.5, 21 |
| Tool Use | T1-T5 |
| Planning | 31 |
| Multi-Agent Collaboration | 10, 13, 13b, 38 |
| Memory | 24, 24+ |
| Learning & Adaptation | 6b, 16 |
| Goal Monitoring | 32 |
| Recovery | 33 |
| Human-in-the-Loop | 15 |
| Retrieval Quality | 1, 1.5, 2, 3, 13+ |
| Inter-Agent Communication | 13, 36, 37, 38 |
| Resource Awareness | 20 |
| Reasoning | 34 |
| Evaluation & Monitoring | 12, 35 |
| Guardrails & Safety | 6c, 23 |
| Prioritization | 22 |
| Exploration & Discovery | 18 |
| Agent-as-Tool | 19 |

---

## Current Executive Readout

- **Fully documented architectural coverage:** 23/23 design patterns complete
- **Execution backbone:** Built from Meta-Path → Retrieval → Graph → SQL → Validation → Healing → Execution → Masking
- **Agentic extensions:** Swarm, voting, human approval, memory, reasoning, recovery, prioritization, exploration, evaluation
- **Main remaining functional gap:** Phase 7 execution is still marked **partial** because the real SAP HANA runtime path is not yet the default production execution mode everywhere

---

## Suggested Uses of This Document

Use this document when you need to:
- explain KYSM architecture to leadership quickly
- map a feature request to the responsible phase
- identify which files are likely impacted by a given enhancement
- onboard new engineers into the KYSM architecture
- cross-check roadmap progress against implementation layers
