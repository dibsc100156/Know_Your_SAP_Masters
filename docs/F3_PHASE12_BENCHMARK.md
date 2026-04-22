# F3 + Phase 12 Benchmark Notes (2026-04-22)

## Artifacts
- Script: `backend/benchmark_f3_phase12.py`
- Report: `backend/reports/benchmark_f3_phase12.json`

## F3 summary
Synthetic benchmark comparing a fixed baseline tool sequence vs the refined iterative F3 planner on representative scenarios.

- average baseline precision: **0.815**
- average refined precision: **0.944**
- precision delta: **+0.129**

Interpretation: the iterative planner is selecting a more relevant tool subset than the static baseline while keeping explicit validation/execution guardrails.

## Phase 12 summary
Synthetic benchmark comparing a legacy phase-state-only correctness view vs the current trajectory-aware quality evaluator.

- average legacy correctness: **0.905**
- average current correctness: **0.810**
- average current trajectory adherence: **0.890**

Interpretation: the current evaluator is intentionally stricter on correctness while adding a strong structured trajectory signal instead of treating phase completion alone as success.
