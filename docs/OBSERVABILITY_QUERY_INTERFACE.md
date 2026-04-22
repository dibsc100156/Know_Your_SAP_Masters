# Observability Query Interface

## What was added
- `backend/app/core/observability_interface.py`
- endpoints:
  - `GET /api/v1/automation/observability/logs?logql=...`
  - `GET /api/v1/automation/observability/metrics?promql=...`
  - `GET /api/v1/automation/observability/traces/{run_id}`

## Safe read-only query surface
### Supported LogQL-style filters
- `status=success|error|empty|ciba_pending|ciba_denied`
- `domain=<domain>`
- `role=<role_id>`
- `heal=true|false`
- `sentinel=true|false`

### Supported PromQL-style metrics
- `success_rate`
- `error_rate`
- `qpm`
- `qph`
- `latency_p95_ms`
- `latency_p99_ms`
- `heal_rate`

## Example queries
- `status=error domain=finance`
- `role=AP_CLERK heal=true`
- `promql=latency_p95_ms`
- `promql=success_rate`

## Current boundary
This is an agent-safe facade over monitoring + harness traces, not a direct Loki/Prometheus backend.
