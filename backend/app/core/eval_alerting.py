"""
eval_alerting.py — P1: Eval Alerting + Benchmark Monitoring
===========================================================
Tracks benchmark results over time, fires alerts when success rate drops
below configurable thresholds, and surfaces alerts to the frontend via Redis.

Alert conditions:
  - success_rate < SUCCESS_RATE_THRESHOLD (default: 0.70)
  - any RED query in the latest run
  - average score drop > SCORE_DROP_THRESHOLD from previous run
  - p95 latency exceeds LATENCY_P95_THRESHOLD_MS

Usage:
  monitor = EvalAlertMonitor()
  monitor.record_run(results_summary_dict)        # after each benchmark run
  alerts = monitor.get_active_alerts()            # for frontend polling
  monitor.clear_resolved()                       # after frontend acknowledges
"""

from __future__ import annotations

import os
import json
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)

# ── Thresholds (can be overridden via env) ────────────────────────────────────

SUCCESS_RATE_THRESHOLD = float(os.environ.get("EVAL_SUCCESS_RATE_THRESHOLD", "0.70"))
SCORE_DROP_THRESHOLD   = float(os.environ.get("EVAL_SCORE_DROP_THRESHOLD", "0.30"))
LATENCY_P95_THRESHOLD_MS = int(os.environ.get("EVAL_LATENCY_P95_MS", "5000"))
ALERT_TTL_SECONDS      = int(os.environ.get("EVAL_ALERT_TTL_SECONDS", "86400"))  # 24h

REDIS_ALERT_PREFIX     = "eval:alert"
REDIS_HISTORY_PREFIX   = "eval:history"
MAX_HISTORY_RUNS       = 30   # keep last 30 runs


# ── Alert model ────────────────────────────────────────────────────────────────

class AlertSeverity(str):
    WARNING = "warning"   # score near threshold, single RED query
    ERROR   = "error"     # success_rate below threshold, or >3 RED queries
    CRITICAL = "critical" # score collapsed or p95 exceeded


@dataclass
class EvalAlert:
    alert_id: str
    severity: AlertSeverity
    title: str
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    run_id: str
    query_ids: List[int]          # affected query IDs
    created_at: str               # ISO timestamp
    resolved: bool = False
    resolved_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvalAlertMonitor:
    """
    Tracks benchmark results and fires alerts when quality degrades.

    Uses Redis as a durable store so alerts persist across server restarts
    and can be queried by the frontend without running the benchmark again.
    """

    def __init__(self, redis_url: str = None):
        if redis_url is None:
            redis_host = os.environ.get("REDIS_HOST", "localhost")
            redis_port = int(os.environ.get("REDIS_PORT", "6379"))
            redis_db   = int(os.environ.get("REDIS_DB",   "0"))
            redis_url  = f"redis://{redis_host}:{redis_port}/{redis_db}"

        self._redis_url = redis_url
        self._redis = None
        self._connect()

    def _connect(self):
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._redis.ping()
            logger.info("[EvalAlerting] Connected to Redis at %s", self._redis_url)
        except Exception as e:
            logger.warning("[EvalAlerting] Redis unavailable — using in-memory fallback: %s", e)
            self._redis = None

    # ── Run recording ────────────────────────────────────────────────────────

    def record_run(self, summary: Dict[str, Any]) -> List[EvalAlert]:
        """
        Call this after each benchmark run with the summary dict.

        Summary must contain:
          - run_id: unique identifier for this run
          - total, green, yellow, red: query counts
          - avg_score: overall average (0-5)
          - avg_time_ms: average latency
          - domain_breakdown: per-domain scores
          - failed_query_ids: list of RED query IDs

        Returns list of new EvalAlert objects fired by this run.
        """
        run_id = summary.get("run_id", f"run-{int(time.time())}")
        timestamp = datetime.now(timezone.utc).isoformat()

        total   = summary.get("total", 0)
        green   = summary.get("green", 0)
        yellow  = summary.get("yellow", 0)
        red     = summary.get("red", 0)
        avg_score = summary.get("avg_score", 0.0)
        avg_time  = summary.get("avg_time_ms", 0.0)
        failed_ids = summary.get("failed_query_ids", [])
        domain_break = summary.get("domain_breakdown", {})

        success_rate = green / total if total > 0 else 0.0

        # Load previous run for delta comparison
        prev_run = self._get_previous_run()

        new_alerts: List[EvalAlert] = []

        # ── Alert 1: Success rate below threshold ────────────────────────────
        if success_rate < SUCCESS_RATE_THRESHOLD:
            severity = AlertSeverity.CRITICAL if success_rate < SUCCESS_RATE_THRESHOLD - 0.1 \
                       else AlertSeverity.ERROR
            new_alerts.append(EvalAlert(
                alert_id = f"alert-success-rate-{run_id}",
                severity = severity,
                title    = f"Success rate below threshold: {success_rate:.1%}",
                message  = (
                    f"Benchmark success rate is {success_rate:.1%} "
                    f"(threshold: {SUCCESS_RATE_THRESHOLD:.0%}). "
                    f"{green}/{total} GREEN, {yellow} YELLOW, {red} RED. "
                    f"Investigate RED queries: {failed_ids}"
                ),
                metric_name  = "success_rate",
                metric_value = round(success_rate, 4),
                threshold    = SUCCESS_RATE_THRESHOLD,
                run_id       = run_id,
                query_ids    = failed_ids,
                created_at   = timestamp,
            ))

        # ── Alert 2: Any RED queries ───────────────────────────────────────
        if failed_ids:
            severity = AlertSeverity.ERROR if len(failed_ids) > 3 else AlertSeverity.WARNING
            qid_str = ", ".join(f"Q{q:02d}" for q in failed_ids[:10])
            new_alerts.append(EvalAlert(
                alert_id = f"alert-red-queries-{run_id}",
                severity = severity,
                title    = f"{len(failed_ids)} RED query(ies): {qid_str}",
                message  = (
                    f"The following queries scored RED and need investigation: {qid_str}. "
                    f"Score: {avg_score:.2f}/5.00. "
                    f"Check SQL generation, schema RAG, or Graph RAG for these domains."
                ),
                metric_name  = "red_query_count",
                metric_value = len(failed_ids),
                threshold    = 0,
                run_id       = run_id,
                query_ids    = failed_ids,
                created_at   = timestamp,
            ))

        # ── Alert 3: Score drop from previous run ───────────────────────────
        if prev_run:
            prev_score = prev_run.get("avg_score", 0.0)
            score_drop = prev_score - avg_score
            if score_drop > SCORE_DROP_THRESHOLD:
                new_alerts.append(EvalAlert(
                    alert_id = f"alert-score-drop-{run_id}",
                    severity = AlertSeverity.ERROR,
                    title    = f"Score dropped {score_drop:.2f} from previous run",
                    message  = (
                        f"Average score fell from {prev_score:.2f} → {avg_score:.2f} "
                        f"(drop: {score_drop:.2f}, threshold: {SCORE_DROP_THRESHOLD:.2f}). "
                        f"Check for regressions in orchestrator or schema RAG."
                    ),
                    metric_name  = "avg_score_drop",
                    metric_value = round(score_drop, 4),
                    threshold    = SCORE_DROP_THRESHOLD,
                    run_id       = run_id,
                    query_ids    = [],
                    created_at   = timestamp,
                ))

        # ── Alert 4: P95 latency exceeded ──────────────────────────────────
        if avg_time > LATENCY_P95_THRESHOLD_MS:
            new_alerts.append(EvalAlert(
                alert_id = f"alert-latency-{run_id}",
                severity = AlertSeverity.WARNING,
                title    = f"Average latency {avg_time:.0f}ms exceeds threshold",
                message  = (
                    f"Orchestrator average latency is {avg_time:.0f}ms "
                    f"(threshold: {LATENCY_P95_THRESHOLD_MS}ms). "
                    f"Consider enabling Celery workers or caching Qdrant results."
                ),
                metric_name  = "avg_latency_ms",
                metric_value = round(avg_time, 2),
                threshold    = float(LATENCY_P95_THRESHOLD_MS),
                run_id       = run_id,
                query_ids    = [],
                created_at   = timestamp,
            ))

        # ── Persist run + alerts ───────────────────────────────────────────
        run_record = {
            "run_id":       run_id,
            "timestamp":    timestamp,
            "total":        total,
            "green":        green,
            "yellow":       yellow,
            "red":          red,
            "avg_score":    round(avg_score, 4),
            "avg_time_ms":  round(avg_time, 2),
            "success_rate": round(success_rate, 4),
            "failed_query_ids": failed_ids,
            "domain_breakdown": domain_break,
        }

        self._push_history(run_record)
        for alert in new_alerts:
            self._store_alert(alert)

        if new_alerts:
            logger.warning(
                "[EvalAlerting] Firing %d alerts for run %s (success_rate=%.3f, avg_score=%.2f)",
                len(new_alerts), run_id, success_rate, avg_score
            )
        else:
            logger.info(
                "[EvalAlerting] Run %s: all clear (success_rate=%.3f, avg_score=%.2f)",
                run_id, success_rate, avg_score
            )

        return new_alerts

    # ── Alert retrieval ────────────────────────────────────────────────────────

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """
        Returns all unresolved alerts, oldest first.
        Frontend polls this to show notification badges.
        """
        if self._redis:
            try:
                keys = self._redis.keys(f"{REDIS_ALERT_PREFIX}:*")
                alerts = []
                for key in keys:
                    raw = self._redis.get(key)
                    if raw:
                        alert = json.loads(raw)
                        if not alert.get("resolved"):
                            alerts.append(alert)
                alerts.sort(key=lambda a: a["created_at"])
                return alerts
            except Exception as e:
                logger.warning("[EvalAlerting] Redis read error: %s", e)

        # Fallback: in-memory
        return getattr(self, "_memory_alerts", [])

    def get_alert_summary(self) -> Dict[str, Any]:
        """Lightweight summary for the frontend status badge."""
        alerts = self.get_active_alerts()
        return {
            "total":       len(alerts),
            "critical":    sum(1 for a in alerts if a["severity"] == "critical"),
            "error":       sum(1 for a in alerts if a["severity"] == "error"),
            "warning":     sum(1 for a in alerts if a["severity"] == "warning"),
            "newest_at":   alerts[-1]["created_at"] if alerts else None,
            "oldest_at":   alerts[0]["created_at"]  if alerts else None,
        }

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark a specific alert as resolved (frontend acknowledges it)."""
        if self._redis:
            try:
                key = f"{REDIS_ALERT_PREFIX}:{alert_id}"
                raw = self._redis.get(key)
                if raw:
                    alert = json.loads(raw)
                    alert["resolved"] = True
                    alert["resolved_at"] = datetime.now(timezone.utc).isoformat()
                    self._redis.setex(key, ALERT_TTL_SECONDS, json.dumps(alert))
                    return True
            except Exception as e:
                logger.warning("[EvalAlerting] resolve_alert Redis error: %s", e)
        return False

    def clear_resolved(self):
        """Delete resolved alerts older than TTL from Redis."""
        if self._redis:
            try:
                keys = self._redis.keys(f"{REDIS_ALERT_PREFIX}:*")
                for key in keys:
                    raw = self._redis.get(key)
                    if raw:
                        alert = json.loads(raw)
                        if alert.get("resolved"):
                            self._redis.delete(key)
                logger.info("[EvalAlerting] Cleared resolved alerts")
            except Exception as e:
                logger.warning("[EvalAlerting] clear_resolved error: %s", e)

    def get_last_run(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent benchmark run record."""
        if self._redis:
            try:
                keys = self._redis.lrange(f"{REDIS_HISTORY_PREFIX}:runs", 0, 0)
                if keys:
                    return json.loads(keys[0])
            except Exception as e:
                logger.warning("[EvalAlerting] get_last_run error: %s", e)
        return getattr(self, "_memory_history", [None])[0]

    # ── Private helpers ────────────────────────────────────────────────────────

    def _connect(self):
        try:
            import redis
            self._redis = redis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            self._redis.ping()
            logger.info("[EvalAlerting] Connected to Redis")
        except Exception as e:
            logger.warning("[EvalAlerting] Redis unavailable — in-memory fallback: %s", e)
            self._redis = None
            self._memory_alerts: List[Dict] = []
            self._memory_history: List[Dict] = []

    def _store_alert(self, alert: EvalAlert):
        key = f"{REDIS_ALERT_PREFIX}:{alert.alert_id}"
        data = json.dumps(alert.to_dict())
        if self._redis:
            try:
                self._redis.setex(key, ALERT_TTL_SECONDS, data)
            except Exception as e:
                logger.warning("[EvalAlerting] Redis write error: %s", e)
                self._memory_alerts = [a for a in self._memory_alerts if a["alert_id"] != alert.alert_id]
                self._memory_alerts.append(alert.to_dict())

    def _get_previous_run(self) -> Optional[Dict[str, Any]]:
        if self._redis:
            try:
                keys = self._redis.lrange(f"{REDIS_HISTORY_PREFIX}:runs", 0, 0)
                if keys:
                    return json.loads(keys[0])
            except Exception:
                pass
        history = getattr(self, "_memory_history", [])
        return history[0] if history else None

    def _push_history(self, run_record: Dict[str, Any]):
        if self._redis:
            try:
                key = f"{REDIS_HISTORY_PREFIX}:runs"
                self._redis.lpush(key, json.dumps(run_record))
                self._redis.ltrim(key, 0, MAX_HISTORY_RUNS - 1)
            except Exception as e:
                logger.warning("[EvalAlerting] _push_history Redis error: %s", e)
                self._memory_history.insert(0, run_record)
                self._memory_history = self._memory_history[:MAX_HISTORY_RUNS]
        else:
            self._memory_history.insert(0, run_record)
            self._memory_history = self._memory_history[:MAX_HISTORY_RUNS]
