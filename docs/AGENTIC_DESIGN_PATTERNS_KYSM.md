﻿# Agentic Design Patterns - KYSM Implementation Guide
**Last Updated:** April 23, 2026 | Project: Know Your SAP Masters (KYSM)

---

## Overview

**Status labels used in this guide:** ✅ Complete | 🟡 Partial | 🚧 Planned

Three YouTube videos were analyzed to extract actionable agentic design patterns for KYSM:

| Video | Title | Channel | Views | Likes | Duration | Priority |
|-------|-------|---------|-------|-------|----------|----------|
| V1 | Master ALL 20 Agentic AI Design Patterns | Mark Kashef | 122,947 | 4,168 | 63 min | 🔴 HIGH |
| V2 | AI Agent Design Patterns (Part 1) | Google Cloud / Annie Wang | 329,596 | 11,995 | 8 min | 🔴 HIGH |
| V3 | 3 Advanced AI Agent Design Patterns (Part 2) | Google Cloud / Annie Wang | 63,136 | 2,306 | 8 min | 🔴 HIGH |

**Source basis:** Google engineer material (including the referenced 400-page book) + official Google ADK patterns.

---

## 23 Agentic Design Patterns - KYSM Mapping

### Pattern 1: Prompt Chaining ✅ Complete
**What it is:** Break a larger task into smaller sequential steps, with each handoff validated before the next step proceeds.

**KYSM status:** The orchestrator runs a stable pipeline sequence and Phase 31 Adaptive Replanning allows it to evaluate intermediate findings and dynamically replan. Phase 30 Prompt Chain Controller Architecture allows structured verdicts and dynamic quality gates across steps.

**Gap:** KYSM still lacks first-class per-step quality gates, retry budgets, and stop conditions. A weak intermediate result can travel too far downstream before the system halts or revises.

**Architecture closure plan:**
1. **Introduce a formal `ChainStep` contract** - each step should declare its input shape, output shape, quality gate, retry budget, and stop condition.
2. **Add a dedicated chain controller** - move step execution into a `chain_controller.py` layer that owns handoffs, retries, halts, and recovery decisions.
3. **Make quality gates explicit** - every major step should return a structured verdict (`PASS`, `RETRY`, `HALT`, `ESCALATE`) rather than relying on implicit downstream behavior.
4. **Centralize retry/stop policy** - retry budgets and stop conditions should live in one policy layer, not be scattered across orchestrator branches.
5. **Surface chain trace metadata** - expose `chain_trace` / `step_verdicts` metadata so the API can show where the chain passed, retried, or halted.

**Mini-roadmap - Prompt Chain Controller Architecture:**

**C1.1 - ChainStep Contract**
- **Goal:** Standardize each orchestrator step as a first-class typed unit.
- **Files:** `backend/app/core/chain_types.py`, `backend/app/core/chain_contract.py`
- **Core classes:** `ChainStep`, `ChainInput`, `ChainOutput`, `QualityGate`, `RetryBudget`, `StopCondition`
- **Interface:** `execute_step(step, state, context) -> ChainOutput`

**C1.2 - Chain Controller**
- **Goal:** Own step sequencing, state transitions, and control-flow decisions.
- **Files:** `backend/app/core/chain_controller.py`
- **Core classes:** `ChainController`, `ChainState`, `ChainRunResult`
- **Interface:** `run_chain(plan, context) -> ChainRunResult`

**C1.3 - Quality Gate Engine**
- **Goal:** Evaluate whether a step result is good enough to proceed.
- **Files:** `backend/app/core/chain_quality_gates.py`
- **Core classes:** `QualityGateEngine`, `GateVerdict`, `GateRule`
- **Interface:** `evaluate_step_result(step_output, gate) -> GateVerdict`

**C1.4 - Retry + Stop Policy**
- **Goal:** Make retries and halts explicit, bounded, and explainable.
- **Files:** `backend/app/core/chain_retry_policy.py`
- **Core classes:** `RetryPolicy`, `StopPolicy`, `RetryDecision`
- **Interface:** `next_action(step_state, gate_verdict) -> RetryDecision`

**C1.5 - Chain Trace + API Surfacing**
- **Goal:** Make chain behavior inspectable in API/frontend responses.
- **Files:** `backend/app/api/schemas/chain_trace.py`, `backend/app/api/endpoints/chat.py`
- **Core classes:** `ChainTrace`, `ChainTraceEntry`
- **Interface:** `to_chain_trace(run_result) -> ChainTrace`

**Build order / dependencies:**
- **Step 1:** **C1.1** first - the controller cannot exist without a stable step contract.
- **Step 2:** **C1.2** next - sequencing logic should be centralized before adding richer gates/policies.
- **Step 3:** **C1.3** after C1.1/C1.2 - gates need a stable step/result contract to evaluate against.
- **Step 4:** **C1.5** after C1.2/C1.3 - trace surfacing is most useful once verdicts are explicit.
- **Step 5:** **C1.4** last - retry/stop policy is safest to formalize once controller and gate behavior are already visible.

**Safest-first implementation sequence:**
1. **C1.1 - ChainStep Contract** (low blast radius, high leverage)
2. **C1.2 - Chain Controller** (control flow consolidation)
3. **C1.3 - Quality Gate Engine** (explicit pass/retry/halt semantics)
4. **C1.5 - Chain Trace + API Surfacing** (observability before stricter retry/stop enforcement)
5. **C1.4 - Retry + Stop Policy** (highest behavioral impact because it changes runtime flow)

**What KYSM has:** A reliable sequential pipeline, but not yet a formal chain controller.

---

### Pattern 2: Routing ✅ Complete
**What it is:** Smart triage - direct queries to the right specialist agent or execution path based on query characteristics.

**KYSM status:** Phase L5 (Complexity Router) implements 4-tier routing:
- `TRIVIAL` (< 0.05) → Meta-path fast path only
- `SIMPLE` (0.05-0.30) → Standard orchestrator, skip Graph traversal
- `COMPLEX` (0.30-0.50) → Full orchestrator incl. Graph RAG + Voting Executor
- `EXPERT` (≥ 0.50) → Multi-Agent Domain Swarm

**Note:** Routing is now split across Phase L5 and Phase 18. L5 handles tiering and skip guards, while Phase 18 adds hierarchical task decomposition and surfaced decomposition plans for more exploratory queries.

---

### Pattern 3: Parallelization ✅ Complete
**What it is:** Split work into independent tasks → run concurrently → merge results.

**KYSM status:**
- Voting Executor (Phase 14): PATH_A/B/C/D fire in parallel via ThreadPoolExecutor - ~20ms total vs ~80ms sequential
- Multi-Agent Swarm (Phase 10): domain agents run concurrently, synthesis agent merges at end

**Gap:** No explicit **aggregator agent** that synthesizes cross-domain parallel results into a unified response. SynthesisAgent exists but is simplistic - it deduplicates and ranks by cross-domain relevance, but doesn't resolve conflicting field values (e.g., two agents report different PO counts for the same vendor on the same day).

---

### Pattern 4: Reflection / Critique ✅ Complete
**What it is:** Generator produces output → critic evaluates against strict conditions → loops back if conditions not met.

**KYSM status:** Voting Executor PATH_B uses `critique_agent.critique()` for structured SQL review, and Phase 21 now formalizes the revision loop on the live orchestrator/API path with bounded retries (`max_iterations=3`), explicit exit conditions, and surfaced `formal_trace` / `revision_summary` metadata.

**Note:** The core reflection loop is now in place. Future improvements are more about widening coverage and tuning than about missing architecture.

---

### Pattern 5: Tool Use ✅ Complete
**What it is:** Agent discovers, authorizes, executes tools, and falls back cleanly when a tool path is unavailable.

**KYSM status:** T1-T5 fully implemented and wired into the orchestrator as of April 23, 2026:
- **T1 (tool_audit_logger.py):** Thread-safe structured JSONL audit to `logs/tool_audit/{date}.jsonl` + Redis pub/sub. `ToolAuditRecord` logs tool selection, execution, fallback, and sentinel events with full redaction of sensitive fields (bankn, stcd1, sql).
- **T2 (Tool dataclass extension):** `allowed_roles`, `denied_roles`, `required_tables`, `compliance_level`, `fallback_tools`, `timeout_ms` added to the `Tool` dataclass in `orchestrator_tools.py`. All 13 tools annotated.
- **T3 (tool_router.py):** `ToolRouter.evaluate()` - role allowlisting gate, pre-execution audit, delegates to `FallbackChain`.
- **T4 (tool_fallback_chain.py):** `FallbackChain` executes primary tool first; on ERROR/timeout, iterates `fallback_tools` in order. Returns first success with `fallback_used` annotation. Supports `FAILFAST`, `BEST_EFFORT`, `CONSENSUS`, `HIERARCHICAL` policies.
- **T5 (Sentinel + Router integration):** SecuritySentinel verdict attached to tool audit record at evaluation time.
- **Orchestrator integration:** All 12 `call_tool()` invocations replaced with `router.evaluate()`; `router = get_tool_router(sentinel)` initialized in `run_agent_loop`. Safe fallback via `TOOL_ROUTER_ENABLED=false` env var.
- **Key files:** `backend/app/core/tool_audit_logger.py`, `backend/app/core/tool_fallback_chain.py`, `backend/app/core/tool_router.py`, `backend/app/agents/orchestrator_tools.py` (Tool dataclass), `backend/app/agents/orchestrator.py` (router wiring)
- **Documentation:** `docs/PATTERN5_TOOL_USE_ARCHITECTURE.md`

**Gap closed:** Role-aware allowlisting ✅ · Clear fallback strategy ✅ · Strong audit logging ✅

---

### Pattern 6: Planning ✅ Complete
**What it is:** Lay out milestones, dependencies, and constraints before execution begins, then adapt the plan when new evidence appears.

**KYSM status:** Phase 31 is live. KYSM builds a dynamic `ExecutionPlan` from the start, applies cost and dependency models, and actively runs an Adaptive Replanner to evaluate intermediate findings and adjust the sequence mid-flight.

**Architecture closure plan:**
1. **Introduce a formal `ExecutionPlan` contract** - planning should produce a first-class plan object with ordered steps, dependencies, assumptions, and revision state.
2. **Add a replanning engine** - intermediate findings (for example, schema surprises, low-confidence retrieval, or graph expansion) should be able to trigger explicit plan revision rather than just flowing through a fixed path.
3. **Model dependency and cost tradeoffs** - replanning should weigh latency, confidence gain, and execution cost before changing the next step order.
4. **Centralize replan policy** - thresholds for when to revise, skip, expand, or halt should live in one policy layer instead of being scattered across orchestrator branches.
5. **Surface plan trace metadata** - expose `plan_trace` / `replan_events` metadata so the API can show when and why the execution plan changed.

**Mini-roadmap - Adaptive Replanning Architecture:**

**P6.1 - ExecutionPlan Contract**
- **Goal:** Standardize initial plans and revised plans as first-class objects.
- **Files:** `backend/app/core/planning_types.py`, `backend/app/core/planning_contract.py`
- **Core classes:** `ExecutionPlan`, `PlanStep`, `PlanDependency`, `PlanRevision`
- **Interface:** `build_initial_plan(query, context) -> ExecutionPlan`

**P6.2 - Replanning Engine**
- **Goal:** Let new evidence revise the remaining plan instead of forcing a fixed sequence.
- **Files:** `backend/app/core/replanner.py`
- **Core classes:** `Replanner`, `PlanningState`, `ReplanTrigger`
- **Interface:** `revise_plan(plan, findings, context) -> ExecutionPlan`

**P6.3 - Dependency + Cost Model**
- **Goal:** Score whether a replan is worth the latency and complexity it introduces.
- **Files:** `backend/app/core/plan_cost_model.py`, `backend/app/core/plan_dependencies.py`
- **Core classes:** `DependencyGraph`, `CostEstimate`, `BenefitScore`
- **Interface:** `score_replan(plan, findings) -> BenefitScore`

**P6.4 - Replan Policy Layer**
- **Goal:** Make replan triggers and guardrails explicit and explainable.
- **Files:** `backend/app/core/plan_policy.py`
- **Core classes:** `ReplanPolicy`, `TriggerThreshold`, `PlanGuardrail`
- **Interface:** `should_replan(plan, findings, score) -> bool`

**P6.5 - Plan Trace + API Surfacing**
- **Goal:** Make planning and replanning visible in API/frontend responses.
- **Files:** `backend/app/api/schemas/plan_trace.py`, `backend/app/api/endpoints/chat.py`
- **Core classes:** `PlanTrace`, `ReplanEvent`
- **Interface:** `to_plan_trace(plan) -> PlanTrace`

**Build order / dependencies:**
- **Step 1:** **P6.1** first - replanning cannot be formalized until the system has a stable plan object.
- **Step 2:** **P6.2** next - revision logic should exist before cost/policy refinement is layered on top.
- **Step 3:** **P6.5** after P6.1/P6.2 - trace surfacing is safest once the system can emit real plan revisions.
- **Step 4:** **P6.3** after P6.2 - cost/dependency scoring is most useful once replans actually exist.
- **Step 5:** **P6.4** last - policy thresholds should be tuned only after plan revision behavior is observable.

**Safest-first implementation sequence:**
1. **P6.1 - ExecutionPlan Contract** (low blast radius, high leverage)
2. **P6.2 - Replanning Engine** (core adaptive behavior)
3. **P6.5 - Plan Trace + API Surfacing** (observability before aggressive tuning)
4. **P6.3 - Dependency + Cost Model** (smarter replan scoring)
5. **P6.4 - Replan Policy Layer** (highest behavioral impact because it governs when plan changes are allowed)

---

### Pattern 7: Multi-Agent Collaboration ✅ Complete
**What it is:** Manager + roles + shared memory across agents.

**KYSM status:**
- Phase 10: Planner Agent → domain agents → Synthesis Agent
- Phase 13: Message Bus (Redis pub/sub + streams, 6 message types)
- Phase 13b: Negotiation Protocol (4-phase ASSERTING→CHALLENGING→NEGOTIATING→COMMITTED)

**Gap:** Agent collaboration is synchronous at call time. There is no persistent shared memory layer between agents across different queries. Agents reset state after each query. Long-running collaborative workflows (e.g., "analyze this vendor's risk profile across 5 dimensions over the next hour") are not supported.

---

### Pattern 8: Memory Management ✅ Complete
**What it is:** Coordinate short-term session state, episodic conversational recall, and long-term learned memory as one coherent system.

**KYSM status:** Phase 24+ (Unified Memory Architecture) is live. KYSM ties together `MemoryContext` across episodic, session, and persistent stores, with unified write-back policies and memory traces injected into the orchestrator loop.
- **Episodic:** Duplicate-turn lookup, recent query/result pairs, scratchpad-aware prompt context, and surfaced episodic metadata are now live in the orchestrator path

**Gap:** Memory is materially better, but still not unified. Short-term state, episodic recall, and long-term learned patterns now cooperate more closely without yet forming one clean, end-to-end memory architecture.

**Architecture closure plan:**
1. **Introduce a unified `MemoryContext` contract** - every query should receive one composed memory object instead of stitching together session scratchpad, episodic lookups, and learned patterns ad hoc.
2. **Add a memory orchestration layer** - a `memory_orchestrator.py` / `memory_manager.py` should decide what to read from session, episodic, and long-term stores; rank it; deduplicate it; and enforce a prompt/token budget.
3. **Define explicit write-back rules** - decide what gets written to session memory, episodic memory, and long-term learned memory after success, failure, healing, approval, or user correction.
4. **Separate memory from policy** - retention, privacy, auditability, and role-based visibility rules should live in a memory-policy layer rather than being scattered across individual memory stores.
5. **Surface memory trace metadata** - expose lightweight `memory_trace` / `memory_sources` metadata in API responses so the system can explain which memory layers influenced a result.

**Mini-roadmap - Unified Memory Architecture:**

**M8.1 - MemoryContext Contract**
- **Goal:** Standardize how memory reaches the orchestrator.
- **Files:** `backend/app/core/memory_context.py`, `backend/app/core/memory_types.py`
- **Core classes:** `MemoryContext`, `MemorySlice`, `MemorySource`, `MemoryBudget`
- **Interface:** `compose_memory_context(session_id, query, auth_context, limits) -> MemoryContext`

**M8.2 - Memory Orchestrator**
- **Goal:** Read across session, episodic, and long-term stores and assemble the final prompt-ready memory bundle.
- **Files:** `backend/app/core/memory_orchestrator.py`, `backend/app/core/memory_ranker.py`
- **Core classes:** `MemoryOrchestrator`, `MemoryRanker`, `MemoryDeduper`
- **Interface:** `build_context(query, session_id, auth_context) -> MemoryContext`

**M8.3 - Memory Write-Back Router**
- **Goal:** Make memory persistence event-driven and explicit.
- **Files:** `backend/app/core/memory_writeback.py`
- **Core classes:** `MemoryWriteRouter`, `MemoryEvent`, `MemoryWriteDecision`
- **Interface:** `record_query(...)`, `record_result(...)`, `record_feedback(...)`, `record_heal(...)`

**M8.4 - Memory Policy Layer**
- **Goal:** Centralize retention, privacy, auditability, and role-aware visibility rules.
- **Files:** `backend/app/core/memory_policy.py`
- **Core classes:** `MemoryPolicy`, `RetentionRule`, `VisibilityRule`, `MemoryRedactionPolicy`
- **Interface:** `filter_memory_for_role(...)`, `retention_for(event_type)`, `redact_memory_slice(...)`

**M8.5 - Memory Trace + API Surfacing**
- **Goal:** Make memory usage inspectable in API and frontend output.
- **Files:** `backend/app/api/schemas/memory_trace.py`, `backend/app/api/endpoints/chat.py`
- **Core classes:** `MemoryTrace`, `MemoryTraceEntry`
- **Interface:** `to_memory_trace(context) -> MemoryTrace`

**Build order / dependencies:**
- **Step 1:** **M8.1** first - everything else depends on a stable `MemoryContext` contract.
- **Step 2:** **M8.2** next - the orchestrator can only compose memory cleanly once the contract exists.
- **Step 3:** **M8.4** after M8.1/M8.2 - policy should shape memory filtering before write paths get more complex.
- **Step 4:** **M8.5** after M8.2 - trace surfacing is safest once the read/composition path is stable.
- **Step 5:** **M8.3** last - write-back is the riskiest change because it affects persistence semantics across all memory layers.

**Safest-first implementation sequence:**
1. **M8.1 - MemoryContext Contract** (low blast radius, high leverage)
2. **M8.2 - Memory Orchestrator** (read-path consolidation)
3. **M8.5 - Memory Trace + API Surfacing** (observability before more writes)
4. **M8.4 - Memory Policy Layer** (tighten retention/visibility rules centrally)
5. **M8.3 - Memory Write-Back Router** (most sensitive because it changes persistence behavior)

**Recommended LEVEL5_ROADMAP.md wording:**
- Add a follow-on row after Phase 24 in **Priority Build Order**.
- Suggested item: **Unified Memory Architecture Follow-Through - `MemoryContext` + orchestrator + policy + write-back + trace**.
- Suggested phase label: **24+ / M8.1-M8.5**.
- Suggested status: **🟡 Partial** - design defined, Phase 24 live, broader memory unification still pending.

---

### Pattern 9: Learning & Adaptation ✅ Complete
**What it is:** Feedback → prompts/policies/tests updated automatically.

**KYSM status:** Phase 16 stores healed SQL patterns in Qdrant. PATH_D in Voting Executor applies prior healed patterns as a 4th vote path. Reuse counter tracks how often each pattern is applied.

**Gap:** The learning loop is one-directional (heal → store → reuse). There is no mechanism to **unlearn** bad patterns (e.g., a pattern that was healed but later found to produce incorrect results for edge cases). The reuse counter never decrements.

---

### Pattern 10: Goal Setting & Monitoring ✅ Complete
**What it is:** Define success targets, detect drift, and course-correct while work is still in flight.

**KYSM status:** Phase 32 is live. KYSM establishes a `QueryGoal` upfront, tracks goal state per stage, detects goal drift through `GoalDriftDetector`, and applies structured correction strategies dynamically.

**Gap:** Monitoring is still much stronger after the fact than during execution. KYSM does not yet maintain a clear per-query goal state that can drive mid-flight correction.

**Architecture closure plan:**
1. **Introduce a formal `QueryGoal` contract** - each request should carry explicit success targets, constraints, and failure thresholds instead of relying only on post-hoc metrics.
2. **Add a goal-state tracker** - execution should maintain live goal state across planning, retrieval, generation, validation, and masking.
3. **Add drift detection + correction hooks** - when the system drifts away from the goal (for example, low result density, wrong table mix, weak confidence, or incomplete coverage), it should trigger a corrective action rather than merely logging the miss.
4. **Centralize goal policy** - success criteria, thresholds, and escalation rules should live in one policy layer rather than being embedded across individual phases.
5. **Surface goal trace metadata** - expose `goal_state` / `goal_trace` metadata so the API can explain what the system was trying to achieve and when it corrected course.

**Mini-roadmap - Per-Query Goal State Architecture:**

**G10.1 - QueryGoal Contract**
- **Goal:** Represent intent, success targets, and constraints as a first-class runtime object.
- **Files:** `backend/app/core/query_goal.py`, `backend/app/core/goal_types.py`
- **Core classes:** `QueryGoal`, `GoalConstraint`, `GoalTarget`, `GoalThreshold`
- **Interface:** `build_query_goal(query, auth_context, session_context) -> QueryGoal`

**G10.2 - Goal State Tracker**
- **Goal:** Maintain live goal progress through the execution pipeline.
- **Files:** `backend/app/core/goal_tracker.py`
- **Core classes:** `GoalTracker`, `GoalState`, `GoalCheckpoint`
- **Interface:** `update_goal_state(goal_state, phase_event) -> GoalState`

**G10.3 - Drift Detection + Correction Hooks**
- **Goal:** Detect when execution diverges from the goal and trigger corrective action.
- **Files:** `backend/app/core/goal_drift_detector.py`
- **Core classes:** `GoalDriftDetector`, `DriftSignal`, `CorrectionAction`
- **Interface:** `detect_drift(goal_state, execution_state) -> list[DriftSignal]`

**G10.4 - Goal Policy Layer**
- **Goal:** Centralize success criteria, tolerances, and escalation thresholds.
- **Files:** `backend/app/core/goal_policy.py`
- **Core classes:** `GoalPolicy`, `GoalRule`, `EscalationThreshold`
- **Interface:** `evaluate_goal_policy(goal_state, drift_signals) -> CorrectionAction`

**G10.5 - Goal Trace + API Surfacing**
- **Goal:** Make live goal tracking visible in API/frontend responses.
- **Files:** `backend/app/api/schemas/goal_trace.py`, `backend/app/api/endpoints/chat.py`
- **Core classes:** `GoalTrace`, `GoalTraceEntry`
- **Interface:** `to_goal_trace(goal_state) -> GoalTrace`

**Build order / dependencies:**
- **Step 1:** **G10.1** first - there is no goal tracking without a stable goal contract.
- **Step 2:** **G10.2** next - execution needs a live goal state before drift or correction can be meaningful.
- **Step 3:** **G10.5** after G10.1/G10.2 - trace surfacing is safest once real goal-state transitions exist.
- **Step 4:** **G10.3** after G10.2 - drift detection should evaluate a live tracked state, not static metrics.
- **Step 5:** **G10.4** last - policy thresholds are safest to tune once goal-state and drift behavior are observable.

**Safest-first implementation sequence:**
1. **G10.1 - QueryGoal Contract** (low blast radius, high leverage)
2. **G10.2 - Goal State Tracker** (core runtime visibility)
3. **G10.5 - Goal Trace + API Surfacing** (observability before stronger correction behavior)
4. **G10.3 - Drift Detection + Correction Hooks** (introduces active course correction)
5. **G10.4 - Goal Policy Layer** (highest behavioral impact because it decides when and how to intervene)

---

### Pattern 11: Exception Handling & Recovery ✅ Complete
**What it is:** Classify failures, apply recovery logic, and fall back safely when the first path breaks.

**KYSM status:** Phase 33 is live. KYSM wraps failures in a `RecoveryCase` and routes them to fallback policy lanes (RETRY, PARTIAL, FALLBACK, HUMAN_REVIEW, HALT) instead of a hard crash.

**Architecture closure plan:**
1. **Introduce a formal `RecoveryCase` contract** - failures should be represented as structured recovery cases with error class, severity, attempted repairs, and escalation options.
2. **Add a recovery orchestrator** - after self-heal exhaustion, a dedicated layer should choose between retry, fallback, narrow-scope execution, human review, or graceful partial response.
3. **Add escalation routing** - the system should route unresolved cases into the right recovery lane instead of collapsing everything into failure or block.
4. **Centralize recovery policy** - retry limits, escalation thresholds, and fallback priorities should live in one policy layer rather than being scattered across exception handlers.
5. **Surface recovery trace metadata** - expose `recovery_trace` / `recovery_path` metadata so the API can explain what failed, what was attempted, and why the final escalation path was chosen.

**Mini-roadmap - Recovery Escalation Architecture:**

**E11.1 - RecoveryCase Contract**
- **Goal:** Standardize how execution failures are represented after validation or self-heal.
- **Files:** `backend/app/core/recovery_case.py`, `backend/app/core/recovery_types.py`
- **Core classes:** `RecoveryCase`, `RecoveryAttempt`, `RecoverySeverity`, `RecoveryOption`
- **Interface:** `build_recovery_case(error, context, attempts) -> RecoveryCase`

**E11.2 - Recovery Orchestrator**
- **Goal:** Choose the next recovery path once simple healing is no longer enough.
- **Files:** `backend/app/core/recovery_orchestrator.py`
- **Core classes:** `RecoveryOrchestrator`, `RecoveryState`, `RecoveryResult`
- **Interface:** `resolve_recovery(case, context) -> RecoveryResult`

**E11.3 - Escalation Router**
- **Goal:** Route unresolved failures into retry, fallback, partial answer, human review, or hard stop.
- **Files:** `backend/app/core/recovery_router.py`
- **Core classes:** `EscalationRouter`, `EscalationLane`, `RecoveryDecision`
- **Interface:** `route_recovery(case, policy) -> RecoveryDecision`

**E11.4 - Recovery Policy Layer**
- **Goal:** Make escalation thresholds and fallback ordering explicit and tunable.
- **Files:** `backend/app/core/recovery_policy.py`
- **Core classes:** `RecoveryPolicy`, `FallbackRule`, `EscalationThreshold`
- **Interface:** `evaluate_recovery_policy(case, state) -> RecoveryDecision`

**E11.5 - Recovery Trace + API Surfacing**
- **Goal:** Make recovery behavior inspectable in API/frontend responses.
- **Files:** `backend/app/api/schemas/recovery_trace.py`, `backend/app/api/endpoints/chat.py`
- **Core classes:** `RecoveryTrace`, `RecoveryTraceEntry`
- **Interface:** `to_recovery_trace(recovery_result) -> RecoveryTrace`

**Build order / dependencies:**
- **Step 1:** **E11.1** first - recovery routing needs a stable case model.
- **Step 2:** **E11.2** next - orchestration logic should exist before richer routing/policy layers are added.
- **Step 3:** **E11.5** after E11.1/E11.2 - trace surfacing is safest once real recovery outcomes exist.
- **Step 4:** **E11.3** after E11.2 - escalation routing should operate on a live orchestrated recovery state.
- **Step 5:** **E11.4** last - policy tuning is safest once recovery paths are visible and testable.

**Safest-first implementation sequence:**
1. **E11.1 - RecoveryCase Contract** (low blast radius, high leverage)
2. **E11.2 - Recovery Orchestrator** (core graceful-escalation behavior)
3. **E11.5 - Recovery Trace + API Surfacing** (observability before stricter routing)
4. **E11.3 - Escalation Router** (introduces explicit recovery lanes)
5. **E11.4 - Recovery Policy Layer** (highest behavioral impact because it governs escalation thresholds and fallback ordering)

---

### Pattern 12: Human-in-the-Loop ✅ Complete
**What it is:** Put a human review surface around higher-risk operations instead of forcing fully autonomous execution.

**KYSM status:** Phase 15+ Conditional CIBA is live. CIBA supports async approval gating, repeat-query memory, and supervisor review. Crucially, supervisors can now return edited_sql, apply conditional_constraints (e.g., forced column masking or row limits), or trigger a REVISE loop with natural language feedback that kicks the request back into the agent workflow.

---

### Pattern 13: Retrieval (RAG) ✅ Complete
**What it is:** Parse, embed, retrieve, and then rerank so the strongest context reaches the generation path.

**KYSM status:** Phase 13+ (Retrieval Quality Architecture) is live. KYSM applies a `RetrievalBundle`, multi-signal reranking, and a dedicated retrieval critic to enforce quality profiles before generating answers.

**Architecture closure plan:**
1. **Introduce a unified `RetrievalBundle` contract** - retrieval should hand one structured candidate bundle to downstream logic instead of passing around loosely ranked hits from separate stores.
2. **Add a dedicated reranker layer** - run a stronger reranker over the merged candidate set before prompt assembly so final context quality is not determined by raw cosine similarity alone.
3. **Add a retrieval critic** - evaluate the reranked set for coverage, relevance, diversity, and missing-context risk before it reaches generation.
4. **Make retrieval query-aware** - use intent/domain-aware retrieval profiles so schema, SQL pattern, graph, and QM retrieval do not all behave like a single generic search path.
5. **Surface retrieval trace metadata** - expose `retrieval_trace` / `retrieval_critic` metadata in API responses so context selection is inspectable and debuggable.

**Mini-roadmap - Retrieval Quality Architecture:**

**R13.1 - RetrievalBundle Contract**
- **Goal:** Standardize the retrieval handoff into one composed candidate set.
- **Files:** `backend/app/core/retrieval_bundle.py`, `backend/app/core/retrieval_types.py`
- **Core classes:** `RetrievalBundle`, `RetrievalCandidate`, `RetrievalScore`
- **Interface:** `collect_candidates(query, auth_context, limits) -> RetrievalBundle`

**R13.2 - Reranker Layer**
- **Goal:** Reorder the merged candidate set with a stronger relevance model.
- **Files:** `backend/app/core/retrieval_reranker.py`
- **Core classes:** `RetrievalReranker`, `CrossEncoderReranker`
- **Interface:** `rerank(bundle, query, top_k) -> RetrievalBundle`

**R13.3 - Retrieval Critic**
- **Goal:** Score the final retrieval set for coverage quality before generation.
- **Files:** `backend/app/core/retrieval_critic.py`
- **Core classes:** `RetrievalCritic`, `CriticVerdict`, `CoverageGap`
- **Interface:** `critique_retrieval(bundle, query, intent) -> CriticVerdict`

**R13.4 - Query-Aware Retrieval Profiles**
- **Goal:** Route different query shapes through different retrieval mixes and thresholds.
- **Files:** `backend/app/core/retrieval_profiles.py`
- **Core classes:** `RetrievalProfile`, `RetrievalProfileRouter`
- **Interface:** `select_retrieval_profile(query, intent, domain) -> RetrievalProfile`

**R13.5 - Retrieval Trace + API Surfacing**
- **Goal:** Make retrieval decisions inspectable in API/frontend responses.
- **Files:** `backend/app/api/schemas/retrieval_trace.py`, `backend/app/api/endpoints/chat.py`
- **Core classes:** `RetrievalTrace`, `RetrievalTraceEntry`
- **Interface:** `to_retrieval_trace(bundle, critic_verdict) -> RetrievalTrace`

**Build order / dependencies:**
- **Step 1:** **R13.1** first - all later reranking and critique logic depends on a stable retrieval handoff.
- **Step 2:** **R13.2** next - reranking should improve the read path before more policy/critic complexity is added.
- **Step 3:** **R13.5** after R13.2 - add observability early so reranker behavior is inspectable.
- **Step 4:** **R13.3** after R13.1/R13.2 - the critic should evaluate the reranked bundle, not the raw candidate list.
- **Step 5:** **R13.4** last - profile routing is safest once the bundle, reranker, and critic contracts are already stable.

**Safest-first implementation sequence:**
1. **R13.1 - RetrievalBundle Contract** (low blast radius, high leverage)
2. **R13.2 - Reranker Layer** (improves quality on the read path)
3. **R13.5 - Retrieval Trace + API Surfacing** (observability before heavier routing logic)
4. **R13.3 - Retrieval Critic** (quality gating once ranking is stable)
5. **R13.4 - Query-Aware Retrieval Profiles** (highest coordination cost across retrieval subsystems)

---

### Pattern 14: Inter-Agent Communication ✅ Complete
**What it is:** Give agents a structured way to exchange requests, assertions, challenges, and results.

**KYSM status:** Phase 38 is live. The Redis-backed MessageBus uses proper consumer groups (`XREADGROUP`), delivery envelopes, idempotency tracking, explicit `XACK`, stale claim `XAUTOCLAIM`, and Dead Letter Queues (DLQ).

---

### Pattern 15: Resource-Aware Optimization ✅ Complete
**What it is:** Route by cost/complexity - cheap models for simple tasks, expensive models for complex ones. Track routing cost vs. query execution savings.

**KYSM status:** Phase 20 is live on the API path. `chat.py` uses `route_with_cost(...)`, the router enforces per-tier budgets (TRIVIAL=5ms, SIMPLE=15ms, COMPLEX=50ms, EXPERT=âˆž), adaptive bypass is active, and `cost_stats` / `routing_bypass_reason` are surfaced for inspection. See `backend/app/core/router_cost_tracker.py`.

**Note:** The core optimization pattern is now implemented; remaining work is operational tuning, not foundational wiring.

---

### Pattern 16: Reasoning Techniques (CoT/ToT) ✅ Complete
**What it is:** Chain-of-Thought, Tree-of-Thoughts, self-consistency, agent debate.

**KYSM status:** Phase 34 is live. The `ReasoningRuntime` generates formal explicit step-by-step reasoning checkmarks (from planning through execution), filtered through a `ReasoningPolicy`, and returns them structurally to the API.

**Recommendation:** Add optional CoT mode via a `reasoning_depth` parameter in the API - when `reasoning_depth=detailed`, the orchestrator generates a step-by-step trace stored in the result dict and visible in the frontend.

**Architecture closure plan:**
1. **Introduce a formal `ReasoningTrace` contract** - reasoning output should be represented as a structured trace rather than ad hoc explanation text.
2. **Add a reasoning runtime layer** - the orchestrator should be able to emit step-by-step reasoning checkpoints during planning, retrieval, SQL assembly, validation, and response synthesis.
3. **Separate reasoning depth from execution depth** - lightweight runs should stay cheap, while detailed runs can opt into richer trace capture without changing the core execution path.
4. **Add reasoning policy controls** - govern when detailed traces are allowed, how much detail is surfaced, and what must stay redacted for safety/compliance.
5. **Surface reasoning trace metadata** - expose `reasoning_trace` / `reasoning_summary` fields in API responses so the frontend can render step-by-step decision flow.

**Mini-roadmap - Reasoning Trace Architecture:**

**T16.1 - ReasoningTrace Contract**
- **Goal:** Standardize how reasoning steps are represented and returned.
- **Files:** `backend/app/core/reasoning_trace.py`, `backend/app/core/reasoning_types.py`
- **Core classes:** `ReasoningTrace`, `ReasoningStep`, `ReasoningSummary`, `ReasoningDepth`
- **Interface:** `build_reasoning_trace(run_state) -> ReasoningTrace`

**T16.2 - Reasoning Runtime Hooks**
- **Goal:** Capture step-by-step reasoning checkpoints across the orchestrator path.
- **Files:** `backend/app/core/reasoning_runtime.py`
- **Core classes:** `ReasoningRuntime`, `ReasoningCheckpoint`, `ReasoningCapture`
- **Interface:** `record_reasoning_step(phase, decision, evidence) -> None`

**T16.3 - Reasoning Policy Layer**
- **Goal:** Control which traces can be captured and surfaced at each reasoning depth.
- **Files:** `backend/app/core/reasoning_policy.py`
- **Core classes:** `ReasoningPolicy`, `ReasoningRule`, `TraceRedactionRule`
- **Interface:** `filter_reasoning_trace(trace, policy) -> ReasoningTrace`

**T16.4 - Result Dict + API Surfacing**
- **Goal:** Store reasoning output in the result dict and return it cleanly through API/frontend layers.
- **Files:** `backend/app/api/schemas/reasoning_trace.py`, `backend/app/api/endpoints/chat.py`
- **Core classes:** `ReasoningTraceResponse`, `ReasoningTraceEntry`
- **Interface:** `attach_reasoning_trace(result_dict, trace) -> dict`

**T16.5 - Frontend Reasoning Viewer**
- **Goal:** Make reasoning traces visible and readable in the frontend.
- **Files:** `frontend/app.py`, `frontend/components/reasoning_trace.py`
- **Core classes:** `ReasoningTracePanel`, `ReasoningTraceRow`
- **Interface:** `render_reasoning_trace(trace) -> UI`

**Build order / dependencies:**
- **Step 1:** **T16.1** first - reasoning capture needs a stable trace schema.
- **Step 2:** **T16.2** next - runtime hooks should exist before policy or UI layering is added.
- **Step 3:** **T16.4** after T16.1/T16.2 - result-dict/API surfacing is safest once real traces exist.
- **Step 4:** **T16.3** after T16.2 - policy should filter an actual trace, not speculative output.
- **Step 5:** **T16.5** last - frontend rendering is easiest once trace shape and API surfacing are stable.

**Safest-first implementation sequence:**
1. **T16.1 - ReasoningTrace Contract** (low blast radius, high leverage)
2. **T16.2 - Reasoning Runtime Hooks** (core trace capture)
3. **T16.4 - Result Dict + API Surfacing** (makes traces inspectable quickly)
4. **T16.3 - Reasoning Policy Layer** (controls detail and redaction)
5. **T16.5 - Frontend Reasoning Viewer** (user-facing visualization once the backend trace is stable)

---

### Pattern 17: Evaluation & Monitoring ✅ Complete
**What it is:** Use golden sets, SLA tracking, and drift detection to continuously validate behavior.

**KYSM status:** Phase 35 is live. KYSM has automated Golden-Set regression evaluating impact thresholds depending on file change scope (`ChangeImpactDetector`) running through a dynamic `RegressionGate`.

**Architecture closure plan:**
1. **Introduce a formal `GoldenSet` contract** - evaluation datasets should be versioned, typed, and mapped to the capabilities they are meant to protect.
2. **Add an automated evaluation runner** - meaningful code/config changes should trigger targeted golden-set execution automatically rather than relying on manual benchmark runs.
3. **Add change-impact detection** - the system should decide which golden sets to run based on what actually changed (routing, retrieval, graph, safety, frontend, etc.).
4. **Centralize regression gate policy** - pass/fail thresholds, tolerance bands, and block/warn behavior should live in one policy layer.
5. **Surface evaluation trace metadata** - expose `eval_gate`, `golden_set_results`, and regression summaries so failures are inspectable in CI and runtime dashboards.

**Mini-roadmap - Automated Golden-Set Regression Architecture:**

**V17.1 - GoldenSet Contract**
- **Goal:** Standardize evaluation corpora, expected outcomes, and coverage tags.
- **Files:** `backend/app/evals/golden_set.py`, `backend/app/evals/golden_types.py`
- **Core classes:** `GoldenSet`, `GoldenCase`, `ExpectedOutcome`, `CoverageTag`
- **Interface:** `load_golden_set(name) -> GoldenSet`

**V17.2 - Evaluation Runner**
- **Goal:** Execute golden sets automatically and collect structured results.
- **Files:** `backend/app/evals/eval_runner.py`
- **Core classes:** `EvalRunner`, `EvalRun`, `EvalResult`
- **Interface:** `run_golden_set(golden_set, scope) -> EvalRun`

**V17.3 - Change-Impact Detector**
- **Goal:** Select the smallest meaningful eval scope based on what changed.
- **Files:** `backend/app/evals/change_impact.py`
- **Core classes:** `ChangeImpactDetector`, `ImpactArea`, `EvalScope`
- **Interface:** `detect_eval_scope(changed_files, changed_components) -> EvalScope`

**V17.4 - Regression Gate Policy**
- **Goal:** Decide whether a change passes, warns, or blocks based on golden-set outcomes.
- **Files:** `backend/app/evals/regression_gate.py`
- **Core classes:** `RegressionGate`, `GateThreshold`, `RegressionVerdict`
- **Interface:** `evaluate_regression_gate(eval_run, policy) -> RegressionVerdict`

**V17.5 - Eval Trace + CI Surfacing**
- **Goal:** Make golden-set execution visible in CI, API metadata, and monitoring panels.
- **Files:** `backend/app/evals/eval_trace.py`, `backend/app/api/schemas/eval_gate.py`, `.github/workflows/ci.yml`
- **Core classes:** `EvalTrace`, `EvalGateSummary`
- **Interface:** `to_eval_gate_summary(eval_run, verdict) -> EvalGateSummary`

**Build order / dependencies:**
- **Step 1:** **V17.1** first - automated regression needs a stable evaluation corpus contract.
- **Step 2:** **V17.2** next - golden-set execution must exist before gating or impact-based selection matters.
- **Step 3:** **V17.5** after V17.1/V17.2 - trace surfacing is safest once real eval runs exist.
- **Step 4:** **V17.3** after V17.2 - change-impact selection should optimize an existing eval runner, not replace it.
- **Step 5:** **V17.4** last - regression thresholds are safest to enforce once results and traces are observable.

**Safest-first implementation sequence:**
1. **V17.1 - GoldenSet Contract** (low blast radius, high leverage)
2. **V17.2 - Evaluation Runner** (core automation path)
3. **V17.5 - Eval Trace + CI Surfacing** (observability before hard gating)
4. **V17.3 - Change-Impact Detector** (keeps regression runs targeted and affordable)
5. **V17.4 - Regression Gate Policy** (highest operational impact because it can block changes)

---

### Pattern 18: Guardrails & Safety ✅ Complete
**What it is:** PII detection, prompt injection prevention, sandboxing.

**KYSM status:**
- Phase 6c: Proactive Threat Sentinel (6 threat engines)
- Phase 23: `safety_guardrails.py` now owns the live layered safety contract behind the sentinel adapter, with guardrail verdict/profile surfaced in API responses
- Phase 5: Critique Gate (7-point SQL validation)
- AuthContext column-level masking (Pillar 1)

**Note:** The architectural split that was previously missing is now in place. Further work here is about policy tuning and coverage expansion, not structural separation.

---

### Pattern 19: Prioritization ✅ Complete
**What it is:** Value Ã— effort Ã— urgency Ã— risk - dynamically reorder the work queue.

**KYSM status:**
- Phase 22 provides live sync/async query prioritization with urgency Ã— recency Ã— role_authority scoring
- Celery task priority 0-10 is mapped from score bands
- Fairness tests and queue policy documentation are in place (`docs/PHASE22_QUEUE_POLICY.md`, `backend/tests/test_phase22_query_prioritization.py`)
- File: `backend/app/core/query_priority_scorer.py`

**Note:** The prioritization pattern is now wired through the live path; follow-on work is about policy refinement, not missing implementation.

---

### Pattern 20: Exploration & Discovery ✅ Complete
**What it is:** Map the problem space, cluster related entities, probe unknowns before committing to a solution path.

**KYSM status:** Phase 18 is now live with dynamic FK probing, hierarchical task decomposition, live orchestrator merge, and surfaced decomposition planning. KYSM still maintains its graph foundations, but the discovery path is no longer just a roadmap concept.

**Note:** The exploration pattern is now implemented. The next layer of improvement is breadth and schema-growth sophistication, not basic discovery wiring.

---

## Advanced Patterns from Google ADK (Annie Wang)

### ADK Pattern A1: Loop (Review & Critique) ✅ Complete
See Pattern 4 above. KYSM now has a formal live revision loop with bounded retries, explicit exit conditions, and surfaced trace metadata.

### ADK Pattern A2: Coordinator (Router) ✅ Complete
KYSM now covers both halves of the coordinator pattern: Phase L5 handles tiering and skip guards, while Phase 18 adds hierarchical task decomposition, live orchestrator merge, and surfaced decomposition plans.

### ADK Pattern A3: Agent as Tool ✅ Complete
Phase 19 is now live: Sentinel/CIBA can trigger pre-swarm override behavior, dispatch agents in tool mode, and use tool-mode synthesis when autonomy should be suppressed.

---

## Phases 18-24 Alignment Snapshot

These phases are now tracked as **✅ Complete** in `LEVEL5_ROADMAP.md`; the notes below summarize the live implementation and the main hardening opportunities that remain.

| Phase | Name | Source | Priority | Status |
|-------|------|--------|----------|--------|
| **18** | **Exploration & Discovery (Dynamic Schema Mapping)** | V1 P20 + V3 Coordinator | 🔴 HIGH | ✅ Complete |
| **19** | **Agent-as-Tool Dynamic Override Mode** | V3 Pattern A3 | 🔴 HIGH | ✅ Complete |
| **20** | **Resource-Aware Cost/Complexity Router** | V1 P15 + V3 Coordinator | 🟡 MED | ✅ Complete |
| **21** | **Formal Revision Loop with Exit Conditions** | V3 Loop Pattern | 🟡 MED | ✅ Complete |
| **22** | **Dynamic Query Prioritization Engine** | V1 P19 | 🟡 MED | ✅ Complete |
| **23** | **Safety Guardrails (Standalone Layer)** | V1 P18 | 🟢 LOW | ✅ Complete |
| **24** | **Episodic Memory Store (Session Scratchpad)** | V2 P8 Memory | 🟢 LOW | ✅ Complete |

### Phase 18: Exploration & Discovery (Priority: 🔴 HIGH)
- **Current state:** Live. Dynamic FK probing and hierarchical task decomposition are now merged into the orchestrator path and surfaced in the decomposition plan.
- **Hardening opportunity:** Expand schema-growth breadth and improve coverage for newly introduced SAP modules.
- **Key files:** `backend/app/core/exploration_engine.py`, `backend/app/core/hierarchical_decomposer.py`

### Phase 19: Agent-as-Tool Dynamic Override (Priority: 🔴 HIGH)
- **Current state:** Live. Sentinel/CIBA can trigger pre-swarm override behavior, tool-mode dispatch, and constrained synthesis.
- **Hardening opportunity:** Refine operator ergonomics and widen test coverage for edge-case enforcement paths.
- **Key files:** `backend/app/agents/swarm/agent_tool_mode.py`, `docs/PHASE19_OPERATOR_GUIDE.md`

### Phase 20: Resource-Aware Cost Router (Priority: 🟡 MED)
- **Current state:** Live. `route_with_cost(...)` is on the API path, with tier budgets, adaptive bypass, and surfaced cost metadata.
- **Hardening opportunity:** Continue tuning thresholds and cache policy under real workload.
- **Key file:** `backend/app/core/router_cost_tracker.py`

### Phase 21: Formal Revision Loop (Priority: 🟡 MED)
- **Current state:** Live. Bounded critique/validation/execution revision attempts honor `max_iterations=3`, explicit exit conditions, and surfaced `formal_trace` / `revision_summary`.
- **Hardening opportunity:** Broaden trace consumers and extend targeted tests around edge-case stability heuristics.
- **Key files:** `backend/app/core/revision_loop.py`, `backend/tests/test_phase21_formal_revision_loop.py`

### Phase 22: Dynamic Query Prioritization (Priority: 🟡 MED)
- **Current state:** Live. Sync/async queue prioritization, fairness coverage, and queue policy docs are all wired.
- **Hardening opportunity:** Refine policy weights as production traffic patterns become clearer.
- **Key files:** `backend/app/core/query_priority_scorer.py`, `docs/PHASE22_QUEUE_POLICY.md`

### Phase 23: Safety Guardrails (Standalone Layer) (Priority: 🟢 LOW)
- **Current state:** Live. `safety_guardrails.py` owns the layered safety contract behind the sentinel adapter, with guardrail verdict/profile surfaced in API responses.
- **Hardening opportunity:** Expand policy coverage and make operator-facing diagnostics even clearer.
- **Key file:** `backend/app/core/safety_guardrails.py`

### Phase 24: Episodic Memory (Session Scratchpad) (Priority: 🟢 LOW)
- **Current state:** Live. Duplicate-turn lookup, recent query/result pairs, scratchpad-aware prompt context, and episodic metadata are wired into the orchestrator path.
- **Hardening opportunity:** Keep refining how episodic memory composes with broader memory policies and retention rules.
- **Key file:** `backend/app/core/episodic_memory.py`

---

## KYSM Pattern Coverage Scorecard

This scorecard is intentionally strict: if a pattern is present but still has meaningful operational gaps, it stays **🟡 Partial**.

| Pattern | Name | KYSM Status | Phase |
|---------|------|-------------|-------|
| 1 | Prompt Chaining | ✅ Complete | 30 / 31 |
| 2 | Routing | ✅ Complete | L5 |
| 3 | Parallelization | ✅ Complete | 14 / 10 |
| 4 | Reflection / Critique | ✅ Complete | 14 / 21 |
| 5 | Tool Use | ✅ Complete | T1-T5 |
| 6 | Planning | ✅ Complete | 31 |
| 7 | Multi-Agent Collaboration | ✅ Complete | 10 / 13 |
| 8 | Memory Management | ✅ Complete | 24+ |
| 9 | Learning & Adaptation | ✅ Complete | 16 |
| 10 | Goal Setting & Monitoring | ✅ Complete | 32 |
| 11 | Exception Handling & Recovery | ✅ Complete | 33 |
| 12 | Human-in-the-Loop | ✅ Complete | 15+ |
| 13 | Retrieval (RAG) | ✅ Complete | 13+ |
| 14 | Inter-Agent Communication | ✅ Complete | 36 / 37 / 38 |
| 15 | Resource-Aware Optimization | ✅ Complete | 20 |
| 16 | Reasoning Techniques (CoT/ToT) | ✅ Complete | 34 |
| 17 | Evaluation & Monitoring | ✅ Complete | 35 |
| 18 | Guardrails & Safety | ✅ Complete | 6c / 23 |
| 19 | Prioritization | ✅ Complete | 22 |
| 20 | Exploration & Discovery | ✅ Complete | 18 |
| A1 | Loop (Review & Critique) | ✅ Complete | 14 / 21 |
| A2 | Coordinator (Router) | ✅ Complete | L5 / 18 |
| A3 | Agent as Tool | ✅ Complete | 19 |

**Coverage:** 23/23 ✅ Complete — 0/23 🟡 Partial — 0/23 🚧 Planned

---

## Key Quotes to Keep in Mind

From Annie Wang (ADK Part 2, Loop Pattern):
> *"We need to be really careful designing this exit condition, which can add complexity to our system."*

From Annie Wang (ADK Part 1, Sequential Agent):
> *"This rigid predefined structure can't adapt to dynamic situations."* - KYSM's orchestrator is sequential by design; Phase L5 adds adaptive skip guards but the structure is still rigid.

From Annie Wang (ADK Part 2, Coordinator Pattern):
> *"Extra model calls for routing - higher latency and cost."* - KYSM's Phase L5 router computes on every query; Phase 20 should measure and optimize this.

From Mark Kashef (Pattern 4 - Reflection):
> *"At some point you're either adding too much or you're basically pushing it to the limit where it starts hallucinating on something it wouldn't have hallucinated before. It starts to overthink."* - KYSM's maximum self-heal iterations should be capped explicitly (Phase 21).

---

## References

- [Mark Kashef - 20 Agentic Design Patterns (YouTube)](https://youtu.be/e2zIr_2JMbE)
- [Google Cloud - AI Agent Design Patterns Part 1 (YouTube)](https://youtu.be/GDm_uH6VxPY)
- [Google Cloud - 3 Advanced AI Agent Design Patterns Part 2 (YouTube)](https://youtu.be/89KKm_a4M7A)
- [Google ADK Documentation](https://goo.gle/40ACYEw)
- [Google Multi-Agent Patterns Blog](https://goo.gle/multiagentpattern)
- [Google Agentic Pattern Lab](https://goo.gle/agenticpattern)

