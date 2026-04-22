from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from app.core.monitoring_dashboard import QueryRecord, get_monitor


class ObservabilityQueryInterface:
    """Safe read-only LogQL/PromQL-style facade over KYSM monitoring + traces."""

    def __init__(self, monitor=None, harness_runs=None):
        self.monitor = monitor or get_monitor()
        self.harness_runs = harness_runs

    def query_logs(self, logql: str, limit: int = 50) -> Dict[str, Any]:
        tokens = self._parse_expr(logql)
        records: List[QueryRecord] = self.monitor._window.get_all()  # read-only snapshot
        filtered = []
        for record in records:
            if self._matches(record, tokens):
                filtered.append({
                    "timestamp": record.timestamp,
                    "status": record.status,
                    "domain": record.domain,
                    "role_id": record.role_id,
                    "duration_ms": record.duration_ms,
                    "tables_used": record.tables_used,
                    "heal_applied": record.heal_applied,
                    "error_type": record.error_type,
                    "semantic_trust": record.semantic_trust,
                })
        filtered.sort(key=lambda r: r["timestamp"], reverse=True)
        return {"query": logql, "count": len(filtered), "records": filtered[:limit]}

    def query_metrics(self, promql: str) -> Dict[str, Any]:
        metrics = self.monitor.get_all_metrics()
        key = promql.strip().lower()
        mapping = {
            "success_rate": metrics.get("success_rates", {}).get("success_rate"),
            "error_rate": metrics.get("success_rates", {}).get("error_rate"),
            "qpm": metrics.get("throughput", {}).get("qpm"),
            "qph": metrics.get("throughput", {}).get("qph"),
            "latency_p95_ms": metrics.get("latency", {}).get("p95_ms"),
            "latency_p99_ms": metrics.get("latency", {}).get("p99_ms"),
            "heal_rate": metrics.get("self_heal", {}).get("heal_rate"),
        }
        if key not in mapping:
            raise ValueError(f"Unsupported promql metric: {promql}")
        return {"query": promql, "value": mapping[key]}

    def get_trace(self, span_id: str) -> Dict[str, Any]:
        if self.harness_runs is None:
            try:
                from app.core.harness_runs import HarnessRuns
                from app.core.redis_client import get_redis
                self.harness_runs = HarnessRuns(get_redis())
            except Exception as e:
                raise ValueError(f"HarnessRuns unavailable: {e}")
        run = self.harness_runs.get_run(span_id)
        if run is None:
            raise ValueError(f"Trace not found: {span_id}")
        return {
            "run_id": run.run_id,
            "query": run.query,
            "status": run.status,
            "routing_tier": run.routing_tier,
            "trajectory_event_count": run.trajectory_event_count,
            "trajectory_log": run.trajectory_log,
            "phase_states": [p.to_dict() for p in run.phase_states],
        }

    def _parse_expr(self, expr: str) -> Dict[str, str]:
        tokens: Dict[str, str] = {}
        for part in expr.split():
            if "=" in part:
                key, value = part.split("=", 1)
                tokens[key.strip().lower()] = value.strip()
        return tokens

    def _matches(self, record: QueryRecord, tokens: Dict[str, str]) -> bool:
        for key, value in tokens.items():
            if key == "status" and record.status != value:
                return False
            if key == "domain" and record.domain != value:
                return False
            if key == "role" and record.role_id != value:
                return False
            if key == "heal" and str(record.heal_applied).lower() != value.lower():
                return False
            if key == "sentinel" and str(record.sentinel_detected).lower() != value.lower():
                return False
        return True
