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
- [ ] Finish dynamic foreign-key probing flow
- [ ] Finish hierarchical task decomposition for complex queries
- [ ] Wire exploration outputs into orchestrator decisions cleanly
- [ ] Add tests for discovery on unseen or weak-schema queries
- [ ] Document when exploration is triggered vs skipped

**Done when:** Complex/unseen queries can trigger discovery safely and produce measurable routing gains.
**Key refs:** `backend/app/agents/orchestrator.py`, related exploration components

### 4) Phase 19 — Agent-as-Tool Dynamic Override
- [ ] Implement tool-mode suppression on Sentinel/CIBA trigger
- [ ] Ensure risky/autonomous branches are downgraded deterministically
- [ ] Add tests for `block`, `tighten`, and override edge cases
- [ ] Expose override state in trace/debug output
- [ ] Document operator expectations

**Done when:** Sentinel/CIBA can reliably clamp agent autonomy without breaking safe tool execution.
**Key refs:** `backend/app/core/security_sentinel.py`, `backend/app/api/endpoints/ciba.py`, `backend/app/agents/orchestrator.py`

---

## P1 — High-Value Next

### 5) Phase 20 — Resource-Aware Cost Router
- [ ] Finalize per-tier routing cost tracking
- [ ] Enforce bypass logic when routing overhead exceeds threshold
- [ ] Emit per-query budget/cost trace data
- [ ] Validate that low-complexity queries stay cheap

**Done when:** Router cost is observable and tier bypasses work as intended.

### 6) Phase 21 — Formal Revision Loop
- [ ] Finish `RevisionLoop` / `FormalRevisionLoop` integration
- [ ] Implement exit conditions and convergence detection
- [ ] Enforce `max_iterations=3`
- [ ] Capture revision trace in debug/quality outputs

**Done when:** Revision is iterative but bounded, and traces show why the loop stopped.

### 7) Phase 22 — Dynamic Query Prioritization
- [ ] Build urgency × recency × role-authority scoring
- [ ] Wire scoring into Celery queue selection/prioritization
- [ ] Add tests for starvation/fairness edge cases
- [ ] Document queue policy

**Done when:** Higher-value work is scheduled earlier without starving normal jobs.

### 8) Phase 11 — Meta-Harness Loop
- [ ] Close the remaining gaps in collect → analyze → YAML → approve → patch
- [ ] Verify rule proposals can be safely reviewed and applied
- [ ] Improve reporting for generated recommendations

**Done when:** Failure clusters can produce actionable proposals that are easy to approve and apply.

### 9) Phase 12 / 12b — Quality Evaluator + Trajectory Log
- [ ] Finalize correctness and trajectory scoring pipeline
- [ ] Persist complete trajectory logs for evaluated runs
- [ ] Surface quality metrics in dashboard/debug outputs
- [ ] Add benchmark comparison before/after metrics

**Done when:** Query runs have consistent quality scores and traceable trajectories.

### 10) F3 — Model-Driven Tool Sequencing
- [ ] Upgrade bootstrap planner into a true iterative tool-calling loop
- [ ] Keep hard validation/execution guardrails intact
- [ ] Expose generated tool plan in API/debug output
- [ ] Benchmark against current orchestrator flow

**Done when:** Sequencing is iterative, observable, and demonstrably better than bootstrap mode.
**Key refs:** `backend/app/core/model_driven_sequencer.py`, `backend/app/agents/orchestrator.py`

### 11) Agent Inbox + Push Notifications
- [ ] Define notification triggers and delivery model
- [ ] Wire inbox events into useful user-facing updates
- [ ] Avoid noisy/redundant pushes

**Done when:** Important agent events reach the user with low noise.

### 12) BAPI Workflow Harness (Read-to-Write)
- [ ] Design safe write-capable workflow boundaries
- [ ] Add approval, audit, and rollback expectations
- [ ] Start with one narrow BAPI workflow

**Done when:** One write workflow works safely with clear approvals and auditability.

### 13) Long-Running Agent Infrastructure (6hr runs)
- [ ] Define durable run state model
- [ ] Add resume/retry/cancel behavior
- [ ] Validate long-horizon worker stability

**Done when:** Multi-hour jobs can survive restarts and be inspected safely.

---

## P2 — Important but Can Follow

### 14) Phase 23 — Safety Guardrails (Standalone layer)
- [ ] Separate standalone safety guardrails from Sentinel internals
- [ ] Clarify responsibilities between policy, detection, and enforcement
- [ ] Add tests for layered behavior

**Done when:** Safety logic is modular and easier to evolve independently.

### 15) Phase 24 — Episodic Memory Store
- [ ] Build Redis-backed session scratchpad for last 5 query/result pairs
- [ ] Define retention and privacy boundaries
- [ ] Integrate into routing/revision only where useful

**Done when:** Sessions have a bounded short-term memory that improves continuity without leaking scope.

### 16) Ralph Wiggum PR Review Loop
- [ ] Define review-agent scope
- [ ] Implement PR review pass with useful output formatting
- [ ] Test on non-critical repos first

### 17) Doc-Gardening Agent
- [ ] Scan for stale/misaligned docs
- [ ] Propose doc updates or cleanup patches
- [ ] Add confidence/risk labels for auto-suggested edits

### 18) Observability Query Interface (LogQL/PromQL)
- [ ] Define supported query surface
- [ ] Add safe read-only query path
- [ ] Document example investigations

---

## Cross-Cutting Validation

### 19) End-to-end validation sweep
- [ ] Run benchmark after major P0/P1 items land
- [ ] Compare confidence, latency, and correctness vs current baseline
- [ ] Record regressions and rollback path if needed

### 20) Documentation sync
- [ ] Keep `docs/LEVEL5_ROADMAP.md` aligned with actual status
- [ ] Add/update architecture docs for each major completed item
- [ ] Remove stale claims when features are only partial

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
