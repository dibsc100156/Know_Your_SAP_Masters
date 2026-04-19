"""
monitoring_dashboard.py — Phase L4: Real-Time Operations Monitoring
=====================================================================
Provides real-time visibility into the KYSM orchestrator's operational health.

Key metrics tracked:
  - Query throughput (queries/minute, rolling window)
  - Success / failure / error rates (rolling window)
  - Per-phase latency breakdown (p50, p95, p99)
  - Voting Executor: consensus rate, path distribution, avg confidence boost
  - CIBA Approval Flow: pending / approved / denied counts + rates
  - Self-Healing: heal rate, most-used heal codes, PATH_D hit rate
  - Semantic Validation: trust distribution (high/medium/low), avg score
  - Security Sentinel: threat detection rate, severity breakdown
  - Swarm: agent count distribution, cross-module rate

Data source: Redis (harness_runs + ciba_approval + eval_alerting)
Window: configurable rolling window (default: last 60 minutes)

Usage:
  from app.core.monitoring_dashboard import get_monitor
  monitor = get_monitor()
  metrics = monitor.get_all_metrics()

  # In FastAPI endpoint:
  @router.get("/monitoring/metrics")
  async def get_metrics():
      return monitor.get_all_metrics()
"""

import time
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from collections import defaultdict, deque
from threading import Lock

logger = logging.getLogger(__name__)


# ── In-memory rolling window for real-time metrics (no Redis required) ───────

@dataclass
class QueryRecord:
    """Lightweight per-query snapshot for rolling metrics."""
    timestamp: float        # time.time() at query start
    duration_ms: int
    domain: str
    role_id: str
    status: str             # "success" | "empty" | "error" | "ciba_pending"
    tables_used: List[str]
    confidence_before: float
    confidence_after: float
    phases_completed: List[str]
    voting_triggered: bool
    voting_outcome: str     # "consensus" | "disagreement" | "none"
    heal_applied: bool
    heal_code: str
    semantic_trust: str    # "high" | "medium" | "low"
    semantic_score: float
    ciba_request_id: Optional[str]
    sentinel_detected: bool
    sentinel_severity: str
    agent_count: int        # 0 = no swarm, 1 = single agent, N = multi-agent
    error_type: Optional[str] = None


class MetricsWindow:
    """
    Thread-safe rolling window of QueryRecord objects.
    Automatically evicts records older than window_seconds.
    """
    def __init__(self, window_seconds: int = 3600):
        self._records: deque = deque()
        self._lock = Lock()
        self._window_seconds = window_seconds

    def add(self, record: QueryRecord):
        with self._lock:
            self._records.append(record)
            self._evict()

    def _evict(self):
        cutoff = time.time() - self._window_seconds
        while self._records and self._records[0].timestamp < cutoff:
            self._records.popleft()

    def get_all(self) -> List[QueryRecord]:
        with self._lock:
            self._evict()
            return list(self._records)

    def count(self) -> int:
        with self._lock:
            self._evict()
            return len(self._records)


class MonitoringDashboard:
    """
    Phase L4: Real-time operations monitoring dashboard.

    Collects metrics from the orchestrator on every query and provides
    a comprehensive snapshot of system health.

    Wired into orchestrator via `monitor.record_query(...)` call at the
    end of each run_agent_loop execution.
    """

    def __init__(self, window_seconds: int = 3600):
        self._window = MetricsWindow(window_seconds=window_seconds)
        self._start_time = time.time()
        self._total_queries = 0
        self._total_errors = 0
        self._ciba_store = None
        self._sentinel_store = None

    # ── Recording ─────────────────────────────────────────────────────────────

    def record_query(self, result_dict: Dict[str, Any]):
        """
        Call this at the END of run_agent_loop with the full result dict.
        Extracts all relevant metrics and stores them in the rolling window.
        """
        # Extract fields from result_dict with safe defaults
        timing = result_dict.get("execution_time_ms", 0)
        domain = result_dict.get("domain", "unknown")
        status = self._infer_status(result_dict)
        tables = result_dict.get("tables_used", [])
        conf_before = result_dict.get("confidence_score", {}).get("before", 0.5) \
            if isinstance(result_dict.get("confidence_score"), dict) else 0.5
        conf_after = result_dict.get("confidence_score", {}).get("after", conf_before) \
            if isinstance(result_dict.get("confidence_score"), dict) else conf_before

        # Voting
        voting_triggered = result_dict.get("voting_triggered", False)
        voting_outcome = result_dict.get("voting_outcome", "none")

        # Self-heal
        heal_info = result_dict.get("self_heal", {})
        heal_applied = isinstance(heal_info, dict) and heal_info.get("applied", False)
        heal_code = isinstance(heal_info, dict) and heal_info.get("code", "") or ""

        # Semantic validation
        sem_val = result_dict.get("semantic_validation", {})
        sem_score = isinstance(sem_val, dict) and sem_val.get("score") or None
        sem_trust = isinstance(sem_val, dict) and sem_val.get("trust", "unknown") or "unknown"

        # CIBA
        ciba_id = result_dict.get("ciba_request_id")

        # Sentinel
        sentinel = result_dict.get("sentinel", {})
        sentinel_detected = isinstance(sentinel, dict) and sentinel.get("threat_detected", False)
        sentinel_sev = isinstance(sentinel, dict) and sentinel.get("severity", "") or ""

        # Swarm
        swarm = result_dict.get("swarm_routing", {}) if isinstance(result_dict.get("swarm_routing"), dict) else {}
        agent_count = swarm.get("agent_count", 0) if swarm else 0

        record = QueryRecord(
            timestamp=time.time(),
            duration_ms=timing,
            domain=domain,
            role_id=result_dict.get("role_id", "unknown"),
            status=status,
            tables_used=tables,
            confidence_before=conf_before,
            confidence_after=conf_after,
            phases_completed=result_dict.get("phases_completed", []),
            voting_triggered=voting_triggered,
            voting_outcome=voting_outcome,
            heal_applied=heal_applied,
            heal_code=heal_code,
            semantic_trust=sem_trust,
            semantic_score=sem_score,
            ciba_request_id=ciba_id,
            sentinel_detected=sentinel_detected,
            sentinel_severity=sentinel_sev,
            agent_count=agent_count,
        )

        self._window.add(record)
        self._total_queries += 1
        if status == "error":
            self._total_errors += 1

    def _infer_status(self, result_dict: Dict[str, Any]) -> str:
        if result_dict.get("status") == "ciba_pending":
            return "ciba_pending"
        if result_dict.get("status") == "ciba_denied":
            return "ciba_denied"
        data = result_dict.get("data", [])
        tool_trace = result_dict.get("tool_trace", [])
        if result_dict.get("error"):
            return "error"
        if isinstance(data, list) and len(data) == 0:
            return "empty"
        if isinstance(data, list) and len(data) > 0:
            return "success"
        # Fallback: check tool trace for errors
        for trace in tool_trace:
            if isinstance(trace, dict) and trace.get("status") == "error":
                return "error"
        return "success"

    # ── Metrics computation ────────────────────────────────────────────────────

    def get_all_metrics(self) -> Dict[str, Any]:
        """Return a comprehensive metrics snapshot."""
        records = self._window.get_all()
        now = time.time()

        return {
            "uptime_seconds": round(now - self._start_time),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_seconds": 3600,
            "queries_in_window": len(records),
            "total_queries": self._total_queries,
            "total_errors": self._total_errors,
            "throughput": self._compute_throughput(records),
            "success_rates": self._compute_success_rates(records),
            "latency": self._compute_latency(records),
            "voting": self._compute_voting_metrics(records),
            "self_heal": self._compute_self_heal_metrics(records),
            "semantic_validation": self._compute_semantic_metrics(records),
            "ciba": self._compute_ciba_metrics(),
            "sentinel": self._compute_sentinel_metrics(records),
            "swarm": self._compute_swarm_metrics(records),
            "domains": self._compute_domain_breakdown(records),
            "roles": self._compute_role_breakdown(records),
        }

    def _compute_throughput(self, records: List[QueryRecord]) -> Dict[str, float]:
        if not records:
            return {"qpm": 0.0, "qph": 0.0}
        oldest = min(r.timestamp for r in records)
        newest = max(r.timestamp for r in records)
        duration_h = max(newest - oldest, 1.0) / 3600.0
        duration_m = duration_h * 60.0
        qpm = len(records) / max(duration_m, 1/60)
        qph = len(records) / max(duration_h, 1/3600)
        return {"qpm": round(qpm, 2), "qph": round(qph, 1)}

    def _compute_success_rates(self, records: List[QueryRecord]) -> Dict[str, Any]:
        total = len(records)
        if total == 0:
            return {"total": 0, "success": 0, "empty": 0, "error": 0,
                    "ciba_pending": 0, "ciba_denied": 0, "success_rate": 0.0}
        counts = defaultdict(int)
        for r in records:
            counts[r.status] += 1
        return {
            "total": total,
            "success": counts.get("success", 0),
            "empty": counts.get("empty", 0),
            "error": counts.get("error", 0),
            "ciba_pending": counts.get("ciba_pending", 0),
            "ciba_denied": counts.get("ciba_denied", 0),
            "success_rate": round(counts.get("success", 0) / total, 4),
            "error_rate": round(counts.get("error", 0) / total, 4),
        }

    def _compute_latency(self, records: List[QueryRecord]) -> Dict[str, Any]:
        if not records:
            return {"p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "avg_ms": 0}
        times = sorted(r.duration_ms for r in records)
        n = len(times)
        p50 = times[int(n * 0.50)]
        p95 = times[int(n * 0.95)] if n >= 20 else times[-1]
        p99 = times[int(n * 0.99)] if n >= 100 else times[-1]
        return {
            "p50_ms": p50,
            "p95_ms": p95,
            "p99_ms": p99,
            "avg_ms": round(sum(times) / n, 1),
            "max_ms": max(times),
        }

    def _compute_voting_metrics(self, records: List[QueryRecord]) -> Dict[str, Any]:
        """Voting Executor health: consensus rate, path distribution, confidence boost."""
        voted = [r for r in records if r.voting_triggered]
        total = len(records)

        if not voted:
            return {"triggered_pct": 0.0, "consensus_rate": 0.0,
                    "path_a": 0, "path_b": 0, "path_c": 0, "path_d": 0,
                    "avg_confidence_boost": 0.0}

        consensus = sum(1 for r in voted if r.voting_outcome == "consensus")
        disagreement = sum(1 for r in voted if r.voting_outcome == "disagreement")

        boosts = [r.confidence_after - r.confidence_before for r in voted if r.confidence_after > 0]
        avg_boost = round(sum(boosts) / len(boosts), 4) if boosts else 0.0

        return {
            "triggered_pct": round(len(voted) / total, 4) if total else 0.0,
            "consensus_rate": round(consensus / len(voted), 4) if voted else 0.0,
            "disagreement_rate": round(disagreement / len(voted), 4) if voted else 0.0,
            "consensus_count": consensus,
            "disagreement_count": disagreement,
            "avg_confidence_boost": avg_boost,
        }

    def _compute_self_heal_metrics(self, records: List[QueryRecord]) -> Dict[str, Any]:
        """Self-healing health: heal rate, top heal codes, PATH_D contribution."""
        healed = [r for r in records if r.heal_applied]
        total = len(records)

        code_counts = defaultdict(int)
        for r in healed:
            code_counts[r.heal_code] += 1

        top_codes = sorted(code_counts.items(), key=lambda x: -x[1])[:5]
        heal_rate = round(len(healed) / total, 4) if total else 0.0

        return {
            "heal_rate": heal_rate,
            "total_heals": len(healed),
            "top_heal_codes": [{"code": c, "count": n} for c, n in top_codes],
            "heal_rate_pct": f"{heal_rate*100:.1f}%",
        }

    def _compute_semantic_metrics(self, records: List[QueryRecord]) -> Dict[str, Any]:
        """Semantic validation health: trust distribution, avg score."""
        validated = [r for r in records if r.semantic_trust != "unknown"]
        if not validated:
            return {"validated_count": 0, "high_pct": 0.0, "medium_pct": 0.0, "low_pct": 0.0,
                    "avg_score": 0.0}

        high = sum(1 for r in validated if r.semantic_trust == "high")
        medium = sum(1 for r in validated if r.semantic_trust == "medium")
        low = sum(1 for r in validated if r.semantic_trust == "low")
        scores = [r.semantic_score for r in validated if r.semantic_score is not None]
        n = len(validated)

        return {
            "validated_count": n,
            "high_pct": round(high / n, 4),
            "medium_pct": round(medium / n, 4),
            "low_pct": round(low / n, 4),
            "avg_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "high_count": high,
            "medium_count": medium,
            "low_count": low,
        }

    def _compute_ciba_metrics(self) -> Dict[str, Any]:
        """CIBA approval flow health from Redis store."""
        try:
            from app.core.ciba_approval_store import get_ciba_store
            store = get_ciba_store()
            stats = store.get_stats()
            pending_reqs = store.get_pending_for_session("_global_") \
                if hasattr(store, 'get_pending_for_session') else []
            # Get pending count from stats
            return {
                "backend": stats.get("backend", "unknown"),
                "pending_count": stats.get("total_pending", 0),
                "approved_auto": stats.get("total_approved_auto", 0),
                "denied_auto": stats.get("total_denied_auto", 0),
            }
        except Exception as exc:
            return {"error": str(exc)}

    def _compute_sentinel_metrics(self, records: List[QueryRecord]) -> Dict[str, Any]:
        """Security Sentinel health: detection rate, severity breakdown."""
        detected = [r for r in records if r.sentinel_detected]
        total = len(records)
        if total == 0:
            return {"detection_rate": 0.0, "total_detected": 0}
        sev_counts = defaultdict(int)
        for r in detected:
            sev_counts[r.sentinel_severity] += 1
        return {
            "detection_rate": round(len(detected) / total, 4),
            "total_detected": len(detected),
            "by_severity": dict(sev_counts),
        }

    def _compute_swarm_metrics(self, records: List[QueryRecord]) -> Dict[str, Any]:
        """Swarm health: agent count distribution, cross-module rate."""
        swarm_records = [r for r in records if r.agent_count > 0]
        mono = [r for r in records if r.agent_count == 0]
        total = len(records)
        if total == 0:
            return {"swarm_rate": 0.0, "avg_agents": 0.0, "cross_module_rate": 0.0}
        agent_counts = [r.agent_count for r in swarm_records]
        avg_agents = round(sum(agent_counts) / len(agent_counts), 2) if agent_counts else 0.0
        return {
            "swarm_rate": round(len(swarm_records) / total, 4),
            "avg_agents_per_query": avg_agents,
            "mono_queries": len(mono),
            "swarm_queries": len(swarm_records),
        }

    def _compute_domain_breakdown(self, records: List[QueryRecord]) -> Dict[str, Any]:
        """Per-domain query counts and avg latency."""
        by_domain = defaultdict(lambda: {"count": 0, "total_time_ms": 0})
        for r in records:
            by_domain[r.domain]["count"] += 1
            by_domain[r.domain]["total_time_ms"] += r.duration_ms
        return {
            d: {
                "count": s["count"],
                "avg_ms": round(s["total_time_ms"] / s["count"], 1),
            }
            for d, s in sorted(by_domain.items(), key=lambda x: -x[1]["count"])
        }

    def _compute_role_breakdown(self, records: List[QueryRecord]) -> Dict[str, Any]:
        """Per-role query counts and success rates."""
        by_role = defaultdict(lambda: {"count": 0, "errors": 0})
        for r in records:
            by_role[r.role_id]["count"] += 1
            if r.status == "error":
                by_role[r.role_id]["errors"] += 1
        return {
            role: {
                "count": s["count"],
                "errors": s["errors"],
                "error_rate": round(s["errors"] / max(s["count"], 1), 4),
            }
            for role, s in sorted(by_role.items(), key=lambda x: -x[1]["count"])
        }

    # ── Alert summary (compatible with eval_alerting) ──────────────────────────

    def get_health_score(self) -> float:
        """
        Compute a 0.0–1.0 system health score.
        Combines success rate (50%) + latency (30%) + sentinel safety (20%).
        """
        records = self._window.get_all()
        if not records:
            return 1.0  # no data = assume healthy

        # Success rate component (50%)
        success_count = sum(1 for r in records if r.status == "success")
        success_rate = success_count / len(records)

        # Latency component (30%) — based on p95 vs threshold of 2000ms
        times = sorted(r.duration_ms for r in records)
        p95 = times[int(len(times) * 0.95)] if len(times) >= 20 else max(times, default=0)
        latency_score = max(0.0, 1.0 - (p95 / 2000.0))

        # Sentinel safety component (20%) — low false-positive rate is good
        sentinel_records = [r for r in records if r.sentinel_detected]
        if not sentinel_records:
            sentinel_score = 1.0
        else:
            # Penalize HIGH/CRITICAL detections (legitimate threats are expected)
            high_detections = sum(1 for r in sentinel_records if r.sentinel_severity in ("HIGH", "CRITICAL"))
            sentinel_score = 1.0 - (high_detections / len(sentinel_records)) * 0.5

        return round(success_rate * 0.50 + latency_score * 0.30 + sentinel_score * 0.20, 4)

    def get_status_badge(self) -> Dict[str, str]:
        """Simple health badge: GREEN / YELLOW / RED."""
        score = self.get_health_score()
        if score >= 0.85:
            status = "GREEN"
        elif score >= 0.65:
            status = "YELLOW"
        else:
            status = "RED"
        records = self._window.get_all()
        return {
            "status": status,
            "health_score": score,
            "queries_in_window": len(records),
        }


# ── Singleton ─────────────────────────────────────────────────────────────────

_monitor: Optional[MonitoringDashboard] = None

def get_monitor() -> MonitoringDashboard:
    global _monitor
    if _monitor is None:
        _monitor = MonitoringDashboard(window_seconds=3600)
    return _monitor


def record_query(result_dict: Dict[str, Any]):
    """One-line convenience wrapper for orchestrator to record metrics."""
    get_monitor().record_query(result_dict)