# Phase 22 Queue Policy — Dynamic Query Prioritization

## Goal
Schedule higher-value work earlier without starving normal work.

## Inputs
Priority score uses:
- urgency
- recent activity by `user_id`
- role authority
- routing tier complexity penalty
- SLA contract bonus
- critical-report override

## Queue routing
- **critical report or score >= 8.0** → `priority`
- **score >= 5.0** → `agent` with elevated RabbitMQ priority
- **otherwise** → normal `agent`

## Fairness rules
- recency is tracked per **user_id**, not per role
- first few recent queries get a light boost
- heavy recent volume is capped, then penalized after 10 recent queries
- expert/long-running work gets a complexity penalty so it does not crowd fast lanes
- low-priority work still stays on `agent`; it is not dropped

## Operator expectations
- CFO / critical-report traffic can jump queues
- repeated spam from one active user should not keep increasing priority forever
- normal clerical traffic should remain routable even during bursts
- async submit responses should expose:
  - `priority_score`
  - `queue_target`
  - `priority_breakdown`

## Validation coverage
- recency isolation by `user_id`
- critical request routing to `priority`
- async submit metadata propagation
- fairness / anti-starvation edge cases in `backend/tests/test_phase22_query_prioritization.py`
