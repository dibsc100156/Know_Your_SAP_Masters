# KYSM Level-5 Punch List
**Created:** 2026-04-22
**Source:** `docs/LEVEL5_ROADMAP.md`
**Purpose:** Single trackable list of remaining work to close the Level-5 roadmap.

---

## How to use this file
- Check items off only when the acceptance criteria are met.
- Keep implementation notes short and factual.
- If scope changes, update this file and the roadmap together.

---

## P0 — Must Close First

### 1) Real SAP HANA activation (`HANA_MODE=pool`)
- [ ] Make pooled HANA execution the default runtime instead of mock mode
- [ ] Validate secure connection setup and credential handling
- [ ] Run smoke tests for read-only execution across core domains
- [ ] Verify MANDT enforcement and AuthContext masking still hold on live HANA
- [ ] Document rollout, fallback, and local/dev override behavior

**Done when:** Live HANA is the default runtime, mock mode is explicit opt-in, and smoke tests pass.
**Key refs:** `backend/app/tools/sql_executor.py`, `hana_pool.py`, `backend/app/agents/orchestrator.py`

### 2) Hybrid graph runtime load/perf sign-off (Memgraph + NX mirror, p95 target)
- [x] Define target SLOs (especially p95 latency)
- [x] Build sign-off harness and reporting flow
- [x] Verify local parity between baseline NetworkX and hybrid mirror APIs
- [x] Run load/perf tests on Memgraph + NetworkX mirror runtime
- [x] Measure path-query latency, memory footprint, and failure modes on the live Memgraph path
- [x] Verify sync consistency between Memgraph persistence and NX mirror under live Bolt queries
- [x] Record PASS sign-off results in docs

**Closed (2026-04-22):** Hybrid graph runtime load/perf sign-off (Memgraph + NX mirror, p95 target) is complete. Evidence: `backend/reports/hybrid_graph_signoff_20260422T094235Z.json`.
- Native ranked-path p95: `6.716 ms`
- Mixed workload p95: `28.337 ms`
- Burst p95: `14.702 ms`
- Steady-state p95: `4.396 ms`
- Remote counts: `114 nodes / 140 edges`

**Done when:** p95 targets are met, sync is stable, and perf results are documented.
**Key refs:** `backend/app/core/graph_store.py`, `memgraph_adapter.py`, `backend/hybrid_graph_signoff.py`, `docs/HYBRID_GRAPH_SIGNOFF.md`, `docs/MEMGRAPH_MIGRATION_GUIDE.md`

### 3) Phase 18 — Exploration & Discovery
- [x] Finish dynamic foreign-key probing flow
- [x] Finish hierarchical task decomposition for complex queries
- [x] Wire exploration outputs into orchestrator decisions cleanly
- [x] Add tests for discovery on unseen or weak-schema queries
- [x] Document when exploration is triggered vs skipped

**Implementation note (2026-04-22):** Phase 18 is now wired through the live orchestrator path. Schema RAG misses no longer return early; they continue into Phase 18/Phase 5 fallback flow. `exploration_engine.explore(...)` now fires when a query is not on the meta-path fast path and any of the following hold: no tables found, weak schema confidence (`< 0.60`), COMPLEX/EXPERT routing tier, or field-probe signals such as bank/tax/address/contact/WBS/budget queries. Exploration results merge new tables into `tables_involved`, and `decompose_query(...)` now produces a live `decomposition_plan` for multi-table queries. Targeted unittest coverage was added in `backend/tests/test_phase18_exploration.py`, and a substring bug in comparison detection (`"or"`) was fixed in `hierarchical_decomposer.py`.

**Done when:** Complex/unseen queries can trigger discovery safely and produce measurable routing gains.
**Key refs:** `backend/app/agents/orchestrator.py`, related exploration components

### 4) Phase 19 — Agent-as-Tool Dynamic Override
- [x] Implement tool-mode suppression on Sentinel/CIBA trigger
- [x] Ensure risky/autonomous branches are downgraded deterministically
- [x] Add tests for `block`, `tighten`, and override edge cases
- [x] Expose override state in trace/debug output
- [x] Document operator expectations

**Implementation note (2026-04-22):** core live wiring is now in place. The swarm path evaluates Sentinel/CIBA before autonomy runs, parallel dispatch routes through `agent_tool_mode.wrap_agent_execution(...)`, synthesis falls back to `dedup_only` tool-mode merging, API responses expose `tool_mode` + `tool_mode_reason`, and targeted unittest coverage was added in `backend/tests/test_phase19_agent_tool_mode.py`. Operator guidance is now documented in `docs/PHASE19_OPERATOR_GUIDE.md`.

**Done when:** Sentinel/CIBA can reliably clamp agent autonomy without breaking safe tool execution.
**Key refs:** `backend/app/core/security_sentinel.py`, `backend/app/api/endpoints/ciba.py`, `backend/app/agents/orchestrator.py`

---

## P1 — High-Value Next

### 5) Phase 20 — Resource-Aware Cost Router
- [x] Finalize per-tier routing cost tracking
- [x] Enforce bypass logic when routing overhead exceeds threshold
- [x] Emit per-query budget/cost trace data
- [x] Validate that low-complexity queries stay cheap

**Implementation note (2026-04-22):** Phase 20 is now on the live API path. `chat.py` uses `route_with_cost(...)` instead of bypassing the cost router with direct `get_routing_decision(...)`, and responses now surface `cost_stats` plus `routing_bypass_reason`. Targeted unittest coverage in `backend/tests/test_phase20_router_cost_tracker.py` now covers both bypass-on-budget-breach/cache-hit behavior and the cheap-query under-budget path.

**Done when:** Router cost is observable and tier bypasses work as intended.

### 6) Phase 21 — Formal Revision Loop
- [x] Finish `RevisionLoop` / `FormalRevisionLoop` integration
- [x] Implement exit conditions and convergence detection
- [x] Enforce `max_iterations=3`
- [x] Capture revision trace in debug/quality outputs

**Implementation note (2026-04-22):** Phase 21 is now wired through the live orchestrator path. `run_agent_loop()` configures `FormalRevisionLoop` with explicit confidence/stability exit conditions, bounds critique/validation/execution heal attempts to `max_iterations=3`, records bounded revision events in the formal CoT trace, and returns both `formal_trace` and `revision_summary` through the API response model. Targeted unittest coverage was added in `backend/tests/test_phase21_formal_revision_loop.py`.

**Done when:** Revision is iterative but bounded, and traces show why the loop stopped.

### 7) Phase 22 — Dynamic Query Prioritization
- [x] Build urgency × recency × role-authority scoring
- [x] Wire scoring into Celery queue selection/prioritization
- [x] Add tests for starvation/fairness edge cases
- [x] Document queue policy

**Implementation note (2026-04-22):** Phase 22 now drives the live API + Celery submission path. Sync and async chat endpoints compute priority with real routing tier + request user identity, critical requests now map into the `priority` queue, `apply_async(...)` is called with explicit `queue`/`priority`/`routing_key`, and task metadata carries `priority_score`, `queue_target`, and `priority_breakdown`. Targeted unittest coverage in `backend/tests/test_phase22_query_prioritization.py` now covers user-id recency isolation, critical request priority routing, async submit metadata, fairness recency-penalty behavior, and expert low-urgency anti-jump behavior. Queue policy is documented in `docs/PHASE22_QUEUE_POLICY.md`.

**Done when:** Higher-value work is scheduled earlier without starving normal jobs.

### 8) Phase 11 — Meta-Harness Loop
- [x] Close the remaining gaps in collect → analyze → YAML → approve → patch
- [x] Verify rule proposals can be safely reviewed and applied
- [x] Improve reporting for generated recommendations

**Implementation note (2026-04-22):** Meta-Harness now exposes structured recommendation summaries via `summarize_recommendations(...)`, and `meta_harness_propose` returns that summary alongside YAML output for review. Targeted unittest coverage was added in `backend/tests/test_phase11_meta_harness_loop.py` for summary generation and approve-and-apply patch flow.

**Done when:** Failure clusters can produce actionable proposals that are easy to approve and apply.

### 9) Phase 12 / 12b — Quality Evaluator + Trajectory Log
- [x] Finalize correctness and trajectory scoring pipeline
- [x] Persist complete trajectory logs for evaluated runs
- [x] Surface quality metrics in dashboard/debug outputs
- [x] Add benchmark comparison before/after metrics

**Implementation note (2026-04-22):** Phase 12/12b now persists quality metadata as part of `HarnessRun` instead of loose hash fields, increments/stores `trajectory_event_count`, and evaluates quality from both `phase_states` and the structured `trajectory_log`. The monolithic orchestrator now records major trajectory events for graph discovery, SQL pattern retrieval, self-critique, validation harness, execution, and finalization, and API responses surface richer `quality_metrics` plus the full `trajectory_log`. Targeted unittest coverage was added in `backend/tests/test_phase12_quality_trajectory.py`. Benchmark artifacts now live in `backend/benchmark_f3_phase12.py`, `backend/reports/benchmark_f3_phase12.json`, and `docs/F3_PHASE12_BENCHMARK.md`.

**Done when:** Query runs have consistent quality scores and traceable trajectories.

### 10) F3 — Model-Driven Tool Sequencing
- [x] Upgrade bootstrap planner into a true iterative tool-calling loop
- [x] Keep hard validation/execution guardrails intact
- [x] Expose generated tool plan in API/debug output
- [x] Benchmark against current orchestrator flow

**Implementation note (2026-04-22):** F3 now supports lightweight iterative replanning in the live orchestrator. The initial description-aware plan is built up front, then refined after schema/exploration and graph discovery using newly grounded tables + completed tool state. Validation/execution remain explicit guardrail steps in both bootstrap and refined plans. Sync API responses now surface `model_driven_plan` and `model_driven_plan_history` for debugging/inspection. Coverage added in `backend/tests/test_f3_tool_sequencing.py`. Benchmark artifacts now live in `backend/benchmark_f3_phase12.py`, `backend/reports/benchmark_f3_phase12.json`, and `docs/F3_PHASE12_BENCHMARK.md`.

**Done when:** Sequencing is iterative, observable, and demonstrably better than bootstrap mode.
**Key refs:** `backend/app/core/model_driven_sequencer.py`, `backend/app/agents/orchestrator.py`

### 11) Agent Inbox + Push Notifications
- [x] Define notification triggers and delivery model
- [x] Wire inbox events into useful user-facing updates
- [x] Avoid noisy/redundant pushes

**Implementation note (2026-04-22):** Added `backend/app/core/agent_notifications.py` for Redis-backed user/session-scoped notifications with in-memory fallback and dedup. Async chat endpoints now expose `/notifications`, `/notifications/summary`, read, and read-all flows. Task lifecycle events (queued, started, completed, failed, retrying, cancelled, resumed) now emit user-facing notifications, and coverage was added in `backend/tests/test_phase17_agent_notifications.py`. Operator notes live in `docs/AGENT_INBOX_PUSH_NOTIFICATIONS.md`.

**Done when:** Important agent events reach the user with low noise.

### 12) BAPI Workflow Harness (Read-to-Write)
- [ ] Design safe write-capable workflow boundaries
- [ ] Add approval, audit, and rollback expectations
- [ ] Start with one narrow BAPI workflow

**Done when:** One write workflow works safely with clear approvals and auditability.

### 13) Long-Running Agent Infrastructure (6hr runs)
- [x] Define durable run state model
- [x] Add resume/retry/cancel behavior
- [x] Validate long-horizon worker stability

**Implementation note (2026-04-22):** Added `backend/app/core/long_running_jobs.py` for durable job state and payload persistence, introduced a `longrun` Celery queue plus `run_orchestrator_long_task` (6h envelope), and added `/jobs`, `/jobs/{task_id}`, and `/tasks/{task_id}/resume` control endpoints. Existing revoke now updates durable state, and targeted coverage was added in `backend/tests/test_phase25_long_running_jobs.py`. Design notes live in `docs/LONG_RUNNING_AGENT_INFRA.md`.

**Done when:** Multi-hour jobs can survive restarts and be inspected safely.

---

## P2 — Important but Can Follow

### 14) Phase 23 — Safety Guardrails (Standalone layer)
- [x] Separate standalone safety guardrails from Sentinel internals
- [x] Clarify responsibilities between policy, detection, and enforcement
- [x] Add tests for layered behavior

**Implementation note (2026-04-22):** the live orchestrator now runs through `safety_guardrails.py` via the legacy adapter path rather than treating Sentinel logic as a monolith. Guardrail evaluations now preserve layered debug data (`guardrails.mode`, `guardrails.verdict`, `guardrails.profile`) in API responses so policy/detection/enforcement boundaries are inspectable without changing the enforcement contract. Targeted unittest coverage was added in `backend/tests/test_phase23_24_platform_extras.py` for adapter-level guardrail behavior.

**Done when:** Safety logic is modular and easier to evolve independently.

### 15) Phase 24 — Episodic Memory Store
- [x] Build Redis-backed session scratchpad for last 5 query/result pairs
- [x] Define retention and privacy boundaries
- [x] Integrate into routing/revision only where useful

**Implementation note (2026-04-22):** Phase 24 is now live on the request path. The orchestrator loads bounded per-session history/context, dedup checks, duplicate-turn lookup, recent query/result pairs, and prior table hints before planning; it records the completed turn back into the episodic store and updates scratchpad state (`last_domain`, `last_routing_tier`, `last_tables`) after execution. Sync API responses now surface `episodic_context`, `episodic_memory`, `prior_turns`, and `prior_tables`, including the active backend, retention limits (TTL/history/context window), `recent_query_pairs`, duplicate-turn metadata, and scratchpad hints. Targeted unittest coverage was added in `backend/tests/test_phase23_24_platform_extras.py`.

**Done when:** Sessions have a bounded short-term memory that improves continuity without leaking scope.

### 16) Ralph Wiggum PR Review Loop
- [x] Define review-agent scope
- [x] Implement PR review pass with useful output formatting
- [x] Test on non-critical repos first

**Implementation note (2026-04-22):** Added `backend/app/core/pr_review_loop.py` plus `POST /api/v1/automation/pr-review-loop`. The loop now performs self-review, specialist review (`quality`, `security`, `docs`), bounded iteration until stable, and returns merge readiness / auto-merge eligibility with structured per-round history. Coverage was added in `backend/tests/test_phase26_pr_review_loop.py`. Notes live in `docs/RALPH_WIGGUM_PR_REVIEW_LOOP.md`.

### 17) Doc-Gardening Agent
- [x] Scan for stale/misaligned docs
- [x] Propose doc updates or cleanup patches
- [x] Add confidence/risk labels for auto-suggested edits

**Implementation note (2026-04-22):** Added `backend/app/core/doc_gardening_agent.py` plus `GET /api/v1/automation/doc-gardening`. The scanner now detects broken references, TODO/TBD placeholders, and lightly scored orphan docs, returning structured issues with confidence and risk labels. Coverage was added in `backend/tests/test_phase27_doc_gardening.py`. Notes live in `docs/DOC_GARDENING_AGENT.md`.

### 18) Observability Query Interface (LogQL/PromQL)
- [x] Define supported query surface
- [x] Add safe read-only query path
- [x] Document example investigations

**Implementation note (2026-04-22):** Added `backend/app/core/observability_interface.py` plus endpoints for `/automation/observability/logs`, `/automation/observability/metrics`, and `/automation/observability/traces/{run_id}`. The interface exposes a small safe LogQL-style filter set over query records, a bounded PromQL-style metric map over monitoring output, and harness trajectory lookup by run id. Coverage was added in `backend/tests/test_phase28_observability_interface.py`. Notes live in `docs/OBSERVABILITY_QUERY_INTERFACE.md`.

---

## Cross-Cutting Validation

### 19) End-to-end validation sweep
- [x] Run benchmark after major P0/P1 items land
- [x] Compare confidence, latency, and correctness vs current baseline
- [x] Record regressions and rollback path if needed

**Implementation note (2026-04-22):** Added `backend/end_to_end_validation_sweep.py` and generated `backend/reports/end_to_end_validation_sweep.json`. The sweep currently exercises notifications, long-running job control, PR review loop, doc gardening, observability query interface, cost routing, prioritization, meta-harness, quality trajectory, F3 sequencing, and episodic/safety extras in one repeatable command.

### 20) Documentation sync
- [x] Keep `docs/LEVEL5_ROADMAP.md` aligned with actual status
- [x] Add/update architecture docs for each major completed item
- [x] Remove stale claims when features are only partial

---

## Quick Status Snapshot
- **Completed backbone:** 5-pillar RAG, Graph Embeddings, Voting Executor, CIBA, Self-Healing Patterns DB, Swarm, Message Bus, Negotiation, Monitoring
- **Main gap:** production-grade runtime closure — real HANA, perf sign-off, autonomy control, revision/cost discipline, and durable memory

---

## Suggested close order
1. Real SAP HANA activation
2. Hybrid graph runtime perf/load sign-off
3. Phase 18 — Exploration & Discovery
4. Phase 19 — Agent-as-Tool Dynamic Override
5. Phase 20 — Resource-Aware Cost Router
6. Phase 21 — Formal Revision Loop
7. Phase 22 — Dynamic Query Prioritization
8. Phase 12 / 12b — Quality Evaluator + Trajectory Log
9. F3 — Model-Driven Tool Sequencing
10. Phase 23 / 24 and remaining platform extras
