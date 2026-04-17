# HARNESS_ENGINEERING_RYAN_LOPOPOLO — Gap Analysis vs KYSM Implementation
**Compared against:** `docs/HARNESS_ENGINEERING_RYAN_LOPOPOLO_SUMMARY.md` + `LEVEL5_ROADMAP.md`
**Date:** April 17, 2026

---

## What Ryan Lopopolo Built (OpenAI Experiment)

| # | Capability | Description | KYSM Status |
|---|-----------|-------------|-------------|
| 1 | **Ephemeral per-task environments** | Git worktrees per change; Codex launches and drives isolated app instance with its own logs/metrics | ❌ **MISSING** |
| 2 | **DOM/Screenshot Validation** | Chrome DevTools Protocol wired in; skills for DOM snapshots, screenshots, navigation | ❌ **MISSING** |
| 3 | **Doc-Gardening Agent** | Recurring background Codex task that scans stale/obsolete docs and opens fix-up PRs | ❌ **MISSING** |
| 4 | **Golden Principles Enforcement** | Custom linters mechanically enforce taste invariants (structured logging, naming, file sizes) | ⚠️ **PARTIAL** — `self_improver.py` promotes/demotes patterns but no mechanical linters |
| 5 | **Full Agent Autonomy Threshold** | Single prompt → validate → reproduce bug → record video → fix → validate → record video → PR → agent review → detect failures → remediate → merge | ❌ **MISSING** — No end-to-end pipeline |
| 6 | **6-hour Codex runs** | Single runs execute for hours while humans sleep | ⚠️ **LIMIT** — Celery task timeout unknown; no long-running task infrastructure |
| 7 | **Ralph Wiggum Loop** | Agent self-review → additional agent reviews → iterate until all pass → auto-merge | ⚠️ **PARTIAL** — Self-healer exists; agent-to-agent PR review loop not implemented |
| 8 | **In-Repo Knowledge Store** | Structured `docs/` as system of record; versioned artifacts (code, markdown, schemas, plans) | ⚠️ **PARTIAL** — docs/ exists; no versioning discipline for plans |
| 9 | **Parse Don't Validate** | Data shape validation at boundaries; not prescriptive about how | ✅ **IMPLEMENTED** — Phase 5.5 dry-run at boundary |
| 10 | **Layer Dependency Enforcement** | Types→Config→Repo→Service→Runtime→UI with custom linters | ⚠️ **PARTIAL** — No custom linters; architectural constraints in code but not enforced |
| 11 | **Observability Stack for Agents** | LogQL/PromQL exposed to Codex; ephemeral observability per worktree | ⚠️ **PARTIAL** — Logs exist but not exposed as queryable interface to agents |
| 12 | **Context = Table of Contents** | AGENTS.md ~100 lines as map; real knowledge in structured `docs/` | ⚠️ **PARTIAL** — AGENTS.md exists but no progressive disclosure enforcement |
| 13 | **Garbage Collection for AI Slop** | Background tasks scan deviations, open refactoring PRs daily | ❌ **MISSING** — `self_improver.py` runs pattern quality but no recurring doc/taste cleanup |
| 14 | **Human Escalation Gate** | Agent escalates to human only when judgment required | ⚠️ **PARTIAL** — Sentinel raises alerts; no formal escalation protocol |

---

## Critical Gaps to Build

### 🔴 P0 — End-to-End Autonomous Pipeline
No unified flow where Codex drives: validate → reproduce → fix → validate → PR → merge autonomously.

**What to build:**
- `backend/app/agents/autonomous_pipeline.py` — Single-prompt end-to-end executor
- Steps: `codebase_state_validation()` → `bug_reproducer()` → `fix_implementer()` → `app_driver_validator()` → `pr_opener()` → `agent_reviewer()` → `merge_autonomous()`
- Needs: DOM validation skill, ephemeral worktree management, CI integration

### 🔴 P0 — Ephemeral Task Environments
Agents need isolated app instances to work in, with teardown after task completion.

**What to build:**
- `backend/app/core/ephemeral_environment.py` — Git worktree clone per task, unique port allocation, log capture, teardown
- Worktree pool manager with max concurrency limit
- LogQL/PromQL interface for agents to query their isolated stack

### 🔴 P0 — DOM / Screenshot Validation
For UI bug reproduction and validation — critical for the full autonomy threshold.

**What to build:**
- `backend/app/tools/browser_harness.py` — Chrome DevTools Protocol skills
- `screenshot_on_error()`, `dom_snapshot()`, `ui_validate("expected_state")` tools
- Register in TOOL_REGISTRY

---

### 🟡 P1 — Doc-Gardening Agent
Recurring background task that scans `docs/` for stale content and opens fix-up PRs.

**What to build:**
- `backend/app/agents/swarm/doc_gardening_agent.py`
- Checks: file freshness timestamps, cross-link validity, orphaned files, contradiction with code
- Opens PR with fix for human in loop (fast review, automerge eligible)

### 🟡 P1 — Ralph Wiggum Loop for PRs
Agent self-review + cross-agent review loop on every PR, auto-merge when stable.

**What to build:**
- `backend/app/core/pr_review_loop.py`
- `submit_self_review()` → `request_agent_reviews(agents[])` → `iterate_until_stable()` → `auto_merge()`
- Integrates with existing `self_healer.py` and `synthesis_agent.py`

### 🟡 P1 — Observability Query Interface
Expose logs/metrics as agent-queryable via LogQL/PromQL.

**What to build:**
- `backend/app/core/observability_interface.py`
- `query_logs(logql)`, `query_metrics(promql)`, `get_trace(span_id)`
- Agents use this to validate "startup < 800ms" or "critical journey spans < 2s"

### 🟡 P1 — Golden Principles Mechanical Enforcement
Custom linters that check code for taste deviations and auto-open refactoring PRs.

**What to build:**
- `backend/app/core/golden_linter.py`
- Rules: shared utilities over hand-rolled, no YOLO data access, structured logging enforced, file size limits
- Runs on every PR; comments lint violations with remediation instructions in context
- Recurring daily scan for technical debt accumulation

### 🟡 P1 — Context Progressive Disclosure Enforcement
Mechanically enforce that AGENTS.md is a map, not an encyclopedia.

**What to build:**
- `backend/app/core/progressive_disclosure_linter.py`
- CI checks: AGENTS.md line count ≤ 150, no section longer than 30 lines, all section headings reference deeper docs/
- Validates docs/ cross-links are valid and not orphaned

### 🟡 P1 — Long-Running Agent Infrastructure
Support 6+ hour Codex runs (often overnight) — requires different task infrastructure.

**What to build:**
- Celery task `soft_time_limit` increase for long-running agents
- Or: spawn detached `exec` session for 6hr tasks, callback on completion
- Progress heartbeat every 10 minutes to avoid task lost

---

## Roadmap Corrections Needed

The following items are marked ✅ LIVE in LEVEL5_ROADMAP.md but are **NOT implemented** in code:

| Phase | Name | Marked | Reality | Action |
|-------|------|--------|---------|--------|
| Phase 11 | Automated Meta-Harness | ✅ LIVE | ❌ No `meta_harness_loop.py` found | **Build** |
| Phase 12 | Quality Metrics Eval | ✅ LIVE | ❌ No `QualityEvaluator` found | **Build** |
| Phase 12b | Trajectory Log | ✅ LIVE | ❌ No `HarnessRun.trajectory_log[]` found | **Build** |
| Phase 13 | Inter-Agent Message Bus | ✅ LIVE | ❌ No `message_bus.py` found (but `message_dispatcher.py` exists) | **Build** |
| Phase 13b | Negotiation Protocol | ✅ LIVE | ❌ No `negotiation_protocol.py` found (but `message_dispatcher.py` exists) | **Build** |
| Agent Inbox | `agent_inbox.py` | 🚧 Pending | ❌ File does not exist | **Build** |
| Swarm Autoscaling | Celery domain workers | ✅ IMPLEMENTED | ✅ `domain_tasks.py` exists (24KB) | Verify |
| Contracts | `contracts.py` | ✅ IMPLEMENTED | ✅ `contracts.py` exists (24KB) | Confirm working |

> **Note:** `message_dispatcher.py` (14KB) exists and may contain partial implementations of Phase 13/13b — needs code review to determine coverage.

---

## What's Actually Built (Confirmed by File System)

✅ **Confirmed existing files:**
- `planner_agent.py` (19KB)
- `synthesis_agent.py` (16KB)
- `message_dispatcher.py` (14KB) — partial Phase 13/13b
- `contracts.py` (24KB)
- `domain_tasks.py` (24KB) — Celery domain workers
- `harness_runs.py`
- `self_improver.py`
- `orchestrator_tools.py` (47KB)
- `eval_alerting.py` (16KB)
- `eval_dashboard.py` (17KB)
- `memory_layer.py` (18KB)

❌ **Missing files (marked LIVE in roadmap):**
- `agent_inbox.py`
- `meta_harness_loop.py`
- `QualityEvaluator` class
- `message_bus.py` (Phase 13)
- `negotiation_protocol.py` (Phase 13b)
- `harness_runs.py` — confirmed exists but `trajectory_log[]` needs verification

---

## Priority Build Order

1. **[agent_inbox.py](C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\core\agent_inbox.py)** — Pending since April 12; unblocks swarm message handling
2. **[message_bus.py](C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\core\message_bus.py)** + **[negotiation_protocol.py](C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\core\negotiation_protocol.py)** — Phase 13 core; check if `message_dispatcher.py` already covers these
3. **Automated Meta-Harness Loop** (`meta_harness_loop.py`) — Phase 11
4. **QualityEvaluator + TrajectoryLog** — Phase 12
5. **Doc-Gardening Agent** — P1
6. **Ralph Wiggum PR Review Loop** — P1
7. **Ephemeral Task Environments** — P0
8. **DOM/Screenshot Validation** — P0
9. **Observability Query Interface** — P1
10. **Full Autonomous Pipeline** — P0

---

## Update to LEVEL5_ROADMAP.md

The roadmap needs these corrections:

**Remove from LIVE columns:**
- Phase 11 (Automated Meta-Harness) → Move to 🚧 IN PROGRESS
- Phase 12 (Quality Metrics Eval) → 🚧 IN PROGRESS
- Phase 12b (Trajectory Log) → 🚧 IN PROGRESS
- Phase 13 (Inter-Agent Message Bus) → 🚧 IN PROGRESS (file missing)
- Phase 13b (Negotiation Protocol) → 🚧 IN PROGRESS (file missing)

**Add new sections:**
- P0 Gaps: Ephemeral Environments, DOM Validation, Full Autonomous Pipeline
- P1 Gaps: Doc-Gardening Agent, Ralph Wiggum Loop, Observability Interface, Golden Principles Linters
- P2: Long-Running Agent Infrastructure

**Update Key Files Reference table** to include the confirmed files and note agent_inbox as 🚧 Pending.