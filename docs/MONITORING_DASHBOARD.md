# Phase L4 — Real-Time Operations Monitoring Dashboard
**Status:** ✅ LIVE | **Commits:** `038ba1b`, `880f239`, `b318386` | **Date:** April 19, 2026

---

## Overview

Phase L4 fills the real-time operational health gap between:
- **Phase 12** — `eval_dashboard.py`: historical benchmark reports (what happened last night)
- **eval_alerting.py**: threshold breach alerts (something is wrong right now)
- **Phase L4** — `monitoring_dashboard.py`: live system pulse (what is happening now)

Every query that hits the orchestrator is recorded. Metrics are aggregated in a
1-hour rolling window and exposed via three REST endpoints consumed by the
Streamlit frontend panel.

**Design constraint:** Monitoring must **never block the orchestrator**. All
recording calls are wrapped in `try/except pass` — if the monitoring system
throws, the API response is unaffected.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  FastAPI  POST /chat/master-data                           │
│           run_agent_loop()                                  │
│           ┌──────────────────────────────────────────────┐  │
│           │ result_dict returned                        │  │
│           └──────────┬───────────────────────────────────┘  │
│                      │ try/except pass (non-blocking)      │
│                      ▼                                     │
│           record_query(result_dict)                        │
│           ┌──────────────────────────────────────────────┐  │
│           │ MonitoringDashboard.record_query()           │  │
│           │  • Extract 20 fields from result_dict        │  │
│           │  • Build QueryRecord dataclass               │  │
│           │  • Append to MetricsWindow (deque, 1hr)      │  │
│           └──────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI  GET /eval/monitoring/metrics  ──────────────────┐ │
│  FastAPI  GET /eval/monitoring/status  ────────────────────│ │  Streamlit
│  FastAPI  GET /eval/monitoring/health  ────────────────────│▶│  Frontend
│           MonitoringDashboard singleton                    │ │  render_monitoring_panel()
│           MetricsWindow (thread-safe deque)                │ │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Components

### MonitoringDashboard (`app/core/monitoring_dashboard.py`)

**Singleton** — use `get_monitor()` to access.

```
get_monitor() -> MonitoringDashboard
record_query(result_dict)    # one-line convenience wrapper
```

**MetricsWindow** — thread-safe rolling window (deque, 1-hour default).

```python
monitor = get_monitor()
monitor.record_query({
    "execution_time_ms": 1823,
    "domain": "business_partner",
    "confidence_score": {"before": 0.65, "after": 0.82},
    "data": [...],          # empty → status="empty"
    "tables_used": ["LFA1", "LFB1"],
    "self_heal": {"applied": True, "code": "ORA-00918"},
    "semantic_validation": {"score": 0.91, "trust": "high"},
    "ciba_request_id": None,
    "sentinel": {"threat_detected": False, "severity": ""},
    "swarm_routing": {},    # empty dict = no swarm
    "role_id": "AP_CLERK",
})
```

---

## Metrics Reference

| Metric Group | Fields | Source |
|---|---|---|
| **Throughput** | `qpm`, `qph` | Rolling window time span |
| **Success Rates** | `total`, `success`, `empty`, `error`, `ciba_pending`, `ciba_denied`, `success_rate`, `error_rate` | Per-query status inference |
| **Latency** | `p50_ms`, `p95_ms`, `p99_ms`, `avg_ms`, `max_ms` | `execution_time_ms` from result_dict |
| **Voting** | `triggered_pct`, `consensus_rate`, `disagreement_rate`, `avg_confidence_boost` | `voting_triggered`, `voting_outcome`, `confidence_score` |
| **Self-Heal** | `heal_rate`, `total_heals`, `top_heal_codes[]`, `heal_rate_pct` | `self_heal.applied`, `self_heal.code` |
| **Semantic Trust** | `validated_count`, `high/medium/low_pct`, `avg_score`, `high/medium/low_count` | `semantic_validation.trust`, `semantic_validation.score` |
| **CIBA** | `backend`, `pending_count`, `approved_auto`, `denied_auto` | `get_ciba_store().get_stats()` |
| **Sentinel** | `detection_rate`, `total_detected`, `by_severity{}` | `sentinel.threat_detected`, `sentinel.severity` |
| **Swarm** | `swarm_rate`, `avg_agents_per_query`, `mono_queries`, `swarm_queries` | `agent_count` from swarm_routing |
| **Domain Breakdown** | `{domain: {count, avg_ms}}` | Per-query domain + timing |
| **Role Breakdown** | `{role: {count, errors, error_rate}}` | Per-query role + error status |

---

## API Endpoints

### `GET /api/v1/eval/monitoring/metrics`

Full metrics snapshot.

```json
{
  "uptime_seconds": 1234,
  "generated_at": "2026-04-19T17:30:00.000Z",
  "window_seconds": 3600,
  "queries_in_window": 47,
  "total_queries": 312,
  "throughput": {"qpm": 2.3, "qph": 138.0},
  "success_rates": {"total": 47, "success": 38, "empty": 7, "error": 2, "success_rate": 0.808},
  "latency": {"p50_ms": 1240, "p95_ms": 2800, "p99_ms": 4500, "avg_ms": 1510, "max_ms": 8900},
  "voting": {"triggered_pct": 0.12, "consensus_rate": 0.83, "avg_confidence_boost": 0.14},
  "self_heal": {"heal_rate": 0.06, "total_heals": 3, "top_heal_codes": [{"code": "ORA-00918", "count": 2}]},
  "semantic_validation": {"validated_count": 38, "high_pct": 0.71, "avg_score": 0.87},
  "ciba": {"backend": "redis", "pending_count": 1, "approved_auto": 12, "denied_auto": 3},
  "sentinel": {"detection_rate": 0.02, "total_detected": 1, "by_severity": {"LOW": 1}},
  "swarm": {"swarm_rate": 0.23, "avg_agents_per_query": 2.4, "mono_queries": 36, "swarm_queries": 11},
  "domains": {"business_partner": {"count": 18, "avg_ms": 1200}, "purchasing": {"count": 12, "avg_ms": 2100}},
  "roles": {"AP_CLERK": {"count": 22, "errors": 1, "error_rate": 0.045}}
}
```

### `GET /api/v1/eval/monitoring/status`

Lightweight health badge + key operational metrics.

```json
{
  "status": "GREEN",
  "health_score": 0.91,
  "queries_in_window": 47,
  "total": 47,
  "success": 38,
  "empty": 7,
  "error": 2,
  "ciba_pending": 0,
  "ciba_denied": 0,
  "success_rate": 0.808,
  "error_rate": 0.043,
  "uptime_seconds": 1234,
  "throughput": {"qpm": 2.3, "qph": 138.0},
  "latency": {"p50_ms": 1240, "p95_ms": 2800, "p99_ms": 4500, "avg_ms": 1510, "max_ms": 8900},
  "self_heal": {"heal_rate": 0.06, "total_heals": 3, "top_heal_codes": [], "heal_rate_pct": "6.0%"},
  "ciba": {"backend": "redis", "pending_count": 1, "approved_auto": 12, "denied_auto": 3},
  "swarm": {"swarm_rate": 0.23, "avg_agents_per_query": 2.4, "mono_queries": 36, "swarm_queries": 11}
}
```

### `GET /api/v1/eval/monitoring/health`

Composite health score + throughput + latency.

```json
{
  "status": "GREEN",
  "health_score": 0.91,
  "queries_in_window": 47,
  "success_rate": 0.808,
  "error_rate": 0.043,
  "throughput": {"qpm": 2.3, "qph": 138.0},
  "latency": {"p50_ms": 1240, "p95_ms": 2800, "p99_ms": 4500, "avg_ms": 1510, "max_ms": 8900}
}
```

---

## Health Score Formula

```
health_score = success_rate × 0.50
             + latency_score × 0.30
             + sentinel_score × 0.20
```

**Components:**

| Component | Weight | Calculation |
|---|---|---|
| `success_rate` | 50% | `success_count / total_count` in window |
| `latency_score` | 30% | `max(0, 1 - p95 / 2000)` — penalizes p95 > 2s |
| `sentinel_score` | 20% | `1.0 - (high_detections / total_detected) × 0.5` if threats found; else `1.0` |

**Badge thresholds:**

| Badge | Threshold |
|---|---|
| 🟢 GREEN | `health_score ≥ 0.85` |
| 🟡 YELLOW | `0.65 ≤ health_score < 0.85` |
| 🔴 RED | `health_score < 0.65` |

**Empty window:** Returns `1.0` (no data = assume healthy).

---

## Status Inference

`record_query()` infers query status from `result_dict` fields:

```
ciba_pending  → result_dict.status == "ciba_pending"
ciba_denied   → result_dict.status == "ciba_denied"
error         → result_dict.status == "error"
               OR result_dict.get("error") is truthy
               OR any tool_trace entry has status == "error"
empty         → data is an empty list
success       → data is a non-empty list
```

---

## Frontend Panel (`frontend/monitoring_panel.py`)

`render_monitoring_panel()` — called in `frontend/app.py` after the backend
health check. Auto-refreshes on every Streamlit interaction (no polling loop
needed — Streamlit re-renders on each user action).

**Layout:**

```
┌──────────────────────────────────────────────────────────────┐
│ 📊 Real-Time Operations Dashboard                            │
│                                                              │
│ [Health: YELLOW 0.70]  [Queries: 2/2]  [Uptime: 3m 49s]     │
│                                                              │
│ Throughput: 54.25 qpm | 3255.0 qph                           │
│ Latency: avg=14615ms p50=29136ms p95=29136ms p99=29136ms    │
│                                                              │
│ ✅Success  ⬜Empty  ❌Error  ⏳CIBA  🚫Denied  SuccRate      │
│                                                              │
│ Self-Heal        │ Semantic Trust        Voting Executor      │
│ 0.0% rate        │ 0 validated          0.0% triggered       │
│ 0 heals          │ high=0 med=0 low=0   consensus=0.0%       │
│                                                              │
│ CIBA             │ Sentinel              Swarm               │
│ backend=redis    │ detection=0.0%        rate=0.0%           │
│ pending=0        │ total=0               mono=2 swarm=0        │
│                                                              │
│ ▶ Domain Breakdown (expandable)                              │
│ ▶ Role Breakdown (expandable)                               │
│                                                              │
│ ⏱ Generated at 2026-04-19T17:30:00Z | window=3600s          │
└──────────────────────────────────────────────────────────────┘
```

---

## Wiring Checklist

To add Phase L4 monitoring to any new endpoint:

```python
# 1. Import
from app.core.monitoring_dashboard import record_query

# 2. Call after run_agent_loop (or any function returning result_dict)
result = run_agent_loop(...)
try:
    record_query(result)
except Exception:
    pass  # monitoring must never affect API responses
```

To expose monitoring endpoints in a new router:

```python
from app.core.monitoring_dashboard import get_monitor

@router.get("/monitoring/metrics")
async def get_metrics():
    return get_monitor().get_all_metrics()

@router.get("/monitoring/status")
async def get_status():
    m = get_monitor()
    return m.get_status_badge()

@router.get("/monitoring/health")
async def get_health():
    return {"health_score": get_monitor().get_health_score()}
```

---

## Configuration

| Parameter | Default | Env Var | Notes |
|---|---|---|---|
| Rolling window | 3600s (1 hour) | — | Pass `window_seconds=` to `MonitoringDashboard()` |
| Health: success weight | 0.50 | — | Hardcoded in `get_health_score()` |
| Health: latency weight | 0.30 | — | Hardcoded in `get_health_score()` |
| Health: sentinel weight | 0.20 | — | Hardcoded in `get_health_score()` |
| Latency p95 threshold | 2000ms | — | Used for latency_score in health |
| Sentinel HIGH penalty | 0.5× | — | Applied to sentinel_score |
| Sentinel CRITICAL penalty | same as HIGH | — | Both count as high_detections |

---

## Files Reference

| File | Lines | Purpose |
|---|---|---|
| `backend/app/core/monitoring_dashboard.py` | 489 | Core MonitoringDashboard + MetricsWindow + QueryRecord |
| `backend/app/api/endpoints/eval.py` | ~70 added | 3 monitoring REST endpoints |
| `backend/app/api/endpoints/chat.py` | +8 | `record_query()` call after `run_agent_loop()` |
| `frontend/monitoring_panel.py` | 169 | `render_monitoring_panel()` — Streamlit panel |
| `frontend/app.py` | +8 | Import + call to `render_monitoring_panel()` |

---

## Known Limitations

1. **Domain always "unknown"** — `result_dict["domain"]` is the routing domain hint
   from the API request, not the inferred domain. This is a known gap: the
   orchestrator returns the *input* domain, not the *resolved* domain. Fix requires
   adding a `resolved_domain` field to the orchestrator response.

2. **p99 is same as p95** — percentiles use simple index lookup (`times[int(n*p)]`).
   For small windows (<20 records), p95=p99=p95_index. Not a correctness issue.

3. **CIBA metrics require Redis** — `get_ciba_store()` falls back gracefully but
   will return `{"error": "...not available"}` if Redis is down.

4. **YELLOW/RED health is expected with mock executor** — p95 ~29s in the current
   deployment is caused by the mock executor's artificial delay, not real latency.
   Health will improve to GREEN once real SAP HANA is wired (Phase M8).

---

## Related Phases

- **Phase 12** (`eval_dashboard.py`) — historical benchmark reports
- **eval_alerting.py** — threshold breach alerting
- **Phase 17** (`semantic_answer_validator.py`) — answer quality scoring, feeds into
  semantic trust metrics here
- **Phase 15** (`ciba_approval_store.py`) — CIBA flow, feeds CIBA metrics here
- **Phase M8** — Real SAP HANA connection (will fix the YELLOW health status)
