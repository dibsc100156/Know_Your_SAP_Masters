"""
self_improver.py — Phase 6 Autonomous Self-Improvement Engine
===========================================================
Closes the loop from query → execution → feedback → pattern update → future queries.

Responsibilities:
  1. PATTERN PROMOTION — patterns that succeed repeatedly get boosted in ranking
  2. PATTERN DEMOTION — patterns that fail get buried
  3. GHOST PATTERN INJECTION — auto-discovered JOIN paths that succeed become new patterns
  4. FEEDBACK INTEGRATION — user corrections immediately update relevant patterns
  5. AUTONOMOUS UPGRADE — critique score trends trigger proactive pattern replacement
  6. SCHEMA INSIGHT — newly discovered tables get integrated into known patterns

Usage (runs automatically after every query):
  from app.core.self_improver import SelfImprover
  improver = SelfImprover()
  improver.review_and_improve(
      query="vendor spend for material RM-100",
      sql_generated=sql,
      sql_executed=sql_executed,
      critique_score=0.85,
      result_status="success",
      execution_time_ms=200,
      auth_context=ctx,
      domain="purchasing",
  )

  # Check if any patterns need replacement
  alerts = improver.get_improvement_alerts()
  for alert in alerts:
      logger.info(f"ALERT: {alert['action']} — {alert['reason']}")
"""

import logging
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
from threading import Lock

from app.core.memory_layer import (
    sap_memory,
    PATTERN_SUCCESS,
    PATTERN_FAILURES,
    _load_json,
    _save_json,
)
from app.core.harness_runs import get_harness_runs

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
PATTERN_PROMOTE_THRESHOLD = 5      # successes before promoting
PATTERN_DEMOTE_THRESHOLD = 3       # failures before demoting
PATTERN_BURY_THRESHOLD = 0.4       # success ratio below this → bury
PATTERN_GHOST_MIN_USES = 3         # ad-hoc SQLs seen ≥N times → promote to ghost pattern
CRITIQUE_SCORE_DEMOTE = 0.5        # avg critique score below this → flag for review
ADHOC_SQL_CACHE_MAX = 100          # max ad-hoc SQLs to track


# ---------------------------------------------------------------------------
# Improvement Types
# ---------------------------------------------------------------------------
@dataclass
class ImprovementAction:
    action: str           # "promote" | "demote" | "ghost" | "feedback_applied" | "replace"
    pattern_key: str
    reason: str
    sql_before: Optional[str] = None
    sql_after: Optional[str] = None
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# SelfImprover
# ---------------------------------------------------------------------------
class SelfImprover:
    """
    Autonomous self-improvement engine.
    Monitors pattern health and applies corrections automatically.
    Designed to run after every query without blocking the response.
    """

    def __init__(self, harness_runs=None):
        self._lock = Lock()
        self._ad_hoc_sqls: Dict[str, Dict] = {}  # sql_fingerprint → count + metadata
        self._improvement_alerts: List[Dict] = []
        self._last_review = datetime.now(timezone.utc).isoformat()
        self._harness_runs = harness_runs

    def _log_improvement_event(
        self,
        event_type: str,
        domain: str,
        action: str,
        details: Dict[str, Any],
    ) -> None:
        """Log improvement event to HarnessRuns trajectory if available."""
        if self._harness_runs is None:
            try:
                self._harness_runs = get_harness_runs()
            except Exception:
                pass
        if self._harness_runs is None:
            return
        try:
            # HarnessRuns.add_trajectory_event(run_id, step, decision, reasoning, metadata)
            run_id = details.pop("_run_id", "")
            if not run_id:
                return
            self._harness_runs.add_trajectory_event(
                run_id=run_id,
                step=f"self_improvement:{event_type}",
                decision=f"{action}: {domain}",
                reasoning=details.get("reason", ""),
                metadata={"domain": domain, "action": action, **details},
            )
        except Exception:
            pass

    def review_and_improve(
        self,
        query: str,
        sql_generated: str,
        sql_executed: str,
        critique_score: float,
        result_status: str,  # "success" | "error" | "empty" | "partial"
        execution_time_ms: int,
        auth_context: Any,
        domain: str,
        tables_used: Optional[List[str]] = None,
        self_heal_applied: bool = False,
        feedback_applied: bool = False,
        run_id: Optional[str] = None,
    ) -> List[ImprovementAction]:
        """
        Main entry point — call after every orchestrator run.
        Returns list of improvement actions taken (may be empty).
        Pass run_id to log improvement events to HarnessRuns trajectory.
        """
        actions: List[ImprovementAction] = []
        _had_harness = self._harness_runs is not None
        if run_id and self._harness_runs is None:
            try:
                self._harness_runs = get_harness_runs()
            except Exception:
                self._harness_runs = None
        tables = tables_used or []
        sql = sql_executed or sql_generated

        with self._lock:
            # 1. Track ad-hoc SQLs (SQLs not matched to any known pattern)
            if sql and result_status == "success":
                self._track_ad_hoc_sql(sql, query, domain, tables, critique_score)

            # 2. Promote successful patterns
            if result_status == "success" and critique_score >= 0.7:
                promoted = self._promote_pattern(domain, sql)
                if promoted:
                    actions.append(promoted)

            # 3. Demote failing patterns
            if result_status in ("error", "partial") or critique_score < 0.6:
                demoted = self._demote_pattern(domain, sql)
                if demoted:
                    actions.append(demoted)

            # 4. Ghost pattern injection — ad-hoc SQLs that appear repeatedly
            ghost = self._check_ghost_pattern(sql, domain, tables)
            if ghost:
                actions.append(ghost)

            # 5. Heal-trend tracking — patterns that required self-heal
            if self_heal_applied:
                self._track_self_heal_needed(domain, sql)

            # 6. Feedback integration (called explicitly by feedback_agent)
            #    — this is handled by record_feedback_correction() below

            # 7. Build improvement alerts for reporting
            self._build_alerts(actions)

        return actions

    def record_feedback_correction(
        self,
        query: str,
        original_sql: str,
        corrected_sql: str,
        feedback_type: str,
        domain: str,
        tables: List[str],
    ) -> ImprovementAction:
        """
        Called by FeedbackAgent when user corrects a query.
        Applies the correction directly to the relevant pattern.
        """
        action = ImprovementAction(
            action="feedback_applied",
            pattern_key=f"{domain}:{feedback_type}",
            reason=f"User correction: {feedback_type}",
            sql_before=original_sql,
            sql_after=corrected_sql,
            confidence=1.0,
        )

        with self._lock:
            # Log to HarnessRuns trajectory
            self._log_improvement_event(
                event_type="IMPROVEMENT_FEEDBACK",
                domain=domain,
                action="feedback_applied",
                details={
                    "feedback_type": feedback_type,
                    "query": query[:50],
                    "sql_before": original_sql[:100] if original_sql else "",
                    "sql_after": corrected_sql[:100] if corrected_sql else "",
                },
            )

            # Log gotcha
            sap_memory.log_gotcha(
                pattern=f"feedback:{feedback_type}:{query[:50]}",
                domain=domain,
                severity="warn",
                description=f"User corrected SQL — {feedback_type}",
            )

            # Update the pattern success file with the corrected SQL
            pattern_data = _load_json(PATTERN_SUCCESS, {})
            key = f"{domain}:user_corrected"
            if key not in pattern_data:
                pattern_data[key] = {
                    "domain": domain,
                    "pattern_name": f"user_corrected:{query[:40]}",
                    "success_count": 0,
                    "failure_count": 0,
                    "sql_fingerprints": [],
                    "user_feedback_count": 0,
                    "last_corrected_sql": "",
                    "last_feedback_at": None,
                }

            entry = pattern_data[key]
            entry["user_feedback_count"] = entry.get("user_feedback_count", 0) + 1
            entry["last_corrected_sql"] = corrected_sql
            entry["last_feedback_at"] = datetime.now(timezone.utc).isoformat()

            # If this pattern existed before, transfer success count
            for k, e in list(pattern_data.items()):
                if e.get("domain") == domain and corrected_sql[:50] in str(e.get("sql_fingerprints", [])):
                    entry["success_count"] = max(entry.get("success_count", 0), e.get("success_count", 0))

            pattern_data[key] = entry
            _save_json(PATTERN_SUCCESS, pattern_data)

        return action

    # -------------------------------------------------------------------------
    # Promotion / Demotion
    # -------------------------------------------------------------------------
    def _promote_pattern(self, domain: str, sql: str) -> Optional[ImprovementAction]:
        """Increment success count for this domain+pattern combo."""
        from app.core.memory_layer import _sql_fingerprint
        fp = _sql_fingerprint(sql)

        pattern_data = _load_json(PATTERN_SUCCESS, {})

        # Find the closest matching pattern
        best_key = self._find_best_matching_key(pattern_data, domain, sql)

        if best_key:
            entry = pattern_data[best_key]
            entry["success_count"] = entry.get("success_count", 0) + 1
            entry["last_used"] = datetime.now(timezone.utc).isoformat()
            if fp not in entry.get("sql_fingerprints", []):
                entry.setdefault("sql_fingerprints", []).append(fp)
            pattern_data[best_key] = entry
            _save_json(PATTERN_SUCCESS, pattern_data)

            if entry["success_count"] >= PATTERN_PROMOTE_THRESHOLD:
                return ImprovementAction(
                    action="promote",
                    pattern_key=best_key,
                    reason=f"Pattern '{best_key}' promoted — {entry['success_count']} consecutive successes",
                    sql_after=sql,
                    confidence=0.9,
                )

        return None

    def _demote_pattern(self, domain: str, sql: str) -> Optional[ImprovementAction]:
        """Increment failure count for this pattern."""
        from app.core.memory_layer import _sql_fingerprint
        fp = _sql_fingerprint(sql)

        pattern_data = _load_json(PATTERN_SUCCESS, {})
        failure_data = _load_json(PATTERN_FAILURES, {})

        # Find best matching key
        best_key = self._find_best_matching_key(pattern_data, domain, sql)

        if best_key:
            # Increment failure in success data
            entry = pattern_data[best_key]
            entry["failure_count"] = entry.get("failure_count", 0) + 1
            total = entry["success_count"] + entry["failure_count"]
            ratio = entry["success_count"] / max(total, 1)

            pattern_data[best_key] = entry

            # Check if it should be buried
            if ratio < PATTERN_BURY_THRESHOLD and total >= PATTERN_DEMOTE_THRESHOLD:
                entry["buried"] = True
                entry["buried_at"] = datetime.now(timezone.utc).isoformat()
                _save_json(PATTERN_SUCCESS, pattern_data)
                return ImprovementAction(
                    action="demote",
                    pattern_key=best_key,
                    reason=f"Pattern '{best_key}' demoted — success ratio {ratio:.2f} below {PATTERN_BURY_THRESHOLD}",
                    sql_before=sql,
                    confidence=0.85,
                )
            else:
                _save_json(PATTERN_SUCCESS, pattern_data)

        # Also log to failures
        fkey = best_key or f"{domain}:unknown"
        if fkey not in failure_data:
            failure_data[fkey] = {
                "domain": domain,
                "pattern_name": fkey,
                "failure_count": 0,
                "errors": [],
                "sql_fingerprints": [],
            }
        failure_data[fkey]["failure_count"] += 1
        if fp not in failure_data[fkey].get("sql_fingerprints", []):
            failure_data[fkey].setdefault("sql_fingerprints", []).append(fp)
        _save_json(PATTERN_FAILURES, failure_data)

        return ImprovementAction(
            action="demote",
            pattern_key=fkey,
            reason=f"Failure recorded for '{fkey}'",
            sql_before=sql,
            confidence=0.6,
        )

    def _find_best_matching_key(self, pattern_data: Dict, domain: str, sql: str) -> Optional[str]:
        """Find the best-matching pattern key for a given SQL."""
        from app.core.memory_layer import _sql_fingerprint
        fp = _sql_fingerprint(sql)

        # Exact fingerprint match
        for key, entry in pattern_data.items():
            if fp in entry.get("sql_fingerprints", []):
                return key

        # Domain-only key
        domain_key = f"{domain}:ad_hoc"
        if domain_key in pattern_data:
            return domain_key

        return None

    # -------------------------------------------------------------------------
    # Ghost Pattern Injection
    # -------------------------------------------------------------------------
    def _track_ad_hoc_sql(
        self,
        sql: str,
        query: str,
        domain: str,
        tables: List[str],
        critique_score: float,
    ):
        """Track SQLs that weren't matched to any known pattern."""
        from app.core.memory_layer import _sql_fingerprint
        fp = _sql_fingerprint(sql)

        if fp in self._ad_hoc_sqls:
            self._ad_hoc_sqls[fp]["count"] += 1
        else:
            # Only track if critique score is good (worth promoting later)
            if critique_score >= 0.7:
                self._ad_hoc_sqls[fp] = {
                    "sql": sql[:200],
                    "query": query[:100],
                    "domain": domain,
                    "tables": tables[:5],
                    "count": 1,
                    "first_seen": datetime.now(timezone.utc).isoformat(),
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                }

        # Trim if too large
        if len(self._ad_hoc_sqls) > ADHOC_SQL_CACHE_MAX:
            oldest = sorted(self._ad_hoc_sqls.items(), key=lambda x: x[1]["last_seen"])[:10]
            for fp_old, _ in oldest:
                del self._ad_hoc_sqls[fp_old]

    def _check_ghost_pattern(
        self,
        sql: str,
        domain: str,
        tables: List[str],
    ) -> Optional[ImprovementAction]:
        """Check if an ad-hoc SQL has been seen enough times to become a ghost pattern."""
        from app.core.memory_layer import _sql_fingerprint
        fp = _sql_fingerprint(sql)

        entry = self._ad_hoc_sqls.get(fp)
        if not entry:
            return None

        if entry["count"] >= PATTERN_GHOST_MIN_USES:
            # Promote to ghost pattern
            pattern_data = _load_json(PATTERN_SUCCESS, {})
            ghost_key = f"{domain}:ghost:{entry['query'][:30]}"

            if ghost_key not in pattern_data:
                pattern_data[ghost_key] = {
                    "domain": domain,
                    "pattern_name": entry["query"][:50],
                    "success_count": entry["count"],
                    "failure_count": 0,
                    "sql_fingerprints": [fp],
                    "tables": entry["tables"],
                    "is_ghost": True,
                    "ghost_created_at": datetime.now(timezone.utc).isoformat(),
                    "avg_critique_score": 0.8,
                    "total_critique_score": 0.8 * entry["count"],
                }
                _save_json(PATTERN_SUCCESS, pattern_data)

                # Remove from ad-hoc cache
                del self._ad_hoc_sqls[fp]

                return ImprovementAction(
                    action="ghost",
                    pattern_key=ghost_key,
                    reason=f"Ghost pattern created from {entry['count']} successful ad-hoc executions — query: '{entry['query'][:40]}'",
                    sql_after=sql,
                    confidence=0.8,
                )

        return None

    def _track_self_heal_needed(self, domain: str, sql: str):
        """Track that self-heal was required — pattern may need fixing."""
        sap_memory.log_gotcha(
            pattern=f"self_heal_required:{domain}:{sql[:60]}",
            domain=domain,
            severity="info",
            description=f"Self-heal was applied for this query",
        )

    # -------------------------------------------------------------------------
    # Improvement Alerts
    # -------------------------------------------------------------------------
    def _build_alerts(self, actions: List[ImprovementAction]):
        """Build a summary of recent improvement actions for reporting."""
        for action in actions:
            self._improvement_alerts.append({
                "action": action.action,
                "pattern_key": action.pattern_key,
                "reason": action.reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        # Keep only last 50 alerts
        self._improvement_alerts = self._improvement_alerts[-50:]

    def get_improvement_alerts(self, since: Optional[str] = None) -> List[Dict]:
        """Return recent improvement actions."""
        if since:
            filtered = [
                a for a in self._improvement_alerts
                if a.get("timestamp", "") >= since
            ]
            return filtered
        return self._improvement_alerts[-10:]

    def get_pattern_health_report(self) -> Dict[str, Any]:
        """
        Return a comprehensive health report of all patterns.
        Used by the eval dashboard.
        """
        pattern_data = _load_json(PATTERN_SUCCESS, {})
        failure_data = _load_json(PATTERN_FAILURES, {})

        healthy = []
        degraded = []
        buried = []
        ghost = []

        for key, entry in pattern_data.items():
            total = entry.get("success_count", 0) + entry.get("failure_count", 0)
            if total == 0:
                continue
            ratio = entry["success_count"] / total
            health = {
                "key": key,
                "domain": entry.get("domain", "unknown"),
                "success_count": entry.get("success_count", 0),
                "failure_count": entry.get("failure_count", 0),
                "total_uses": total,
                "success_ratio": round(ratio, 3),
                "is_ghost": entry.get("is_ghost", False),
                "is_buried": entry.get("buried", False),
                "avg_critique_score": entry.get("avg_critique_score", 0),
                "last_used": entry.get("last_used"),
            }

            if entry.get("buried"):
                buried.append(health)
            elif entry.get("is_ghost"):
                ghost.append(health)
            elif ratio >= 0.8:
                healthy.append(health)
            elif ratio < 0.6:
                degraded.append(health)
            else:
                healthy.append(health)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_patterns": len(pattern_data),
            "healthy": len(healthy),
            "degraded": len(degraded),
            "buried": len(buried),
            "ghost": len(ghost),
            "recent_alerts": self.get_improvement_alerts()[-10:],
            "health_breakdown": {
                "healthy": sorted(healthy, key=lambda x: x["success_count"], reverse=True)[:10],
                "degraded": sorted(degraded, key=lambda x: x["success_ratio"])[:5],
                "buried": buried,
                "ghost": ghost,
            },
        }

    # -------------------------------------------------------------------------
    # Proactive Autonomous Actions
    # -------------------------------------------------------------------------
    def run_autonomous_review(self) -> List[ImprovementAction]:
        """
        Run a periodic review of all patterns.
        Called by a cron job or on startup.
        Returns list of actions taken.
        """
        actions: List[ImprovementAction] = []
        pattern_data = _load_json(PATTERN_SUCCESS, {})
        health = self.get_pattern_health_report()

        # Auto-bury patterns below threshold
        for degraded in health.get("health_breakdown", {}).get("degraded", []):
            key = degraded["key"]
            entry = pattern_data.get(key, {})
            if not entry.get("buried") and degraded["success_ratio"] < PATTERN_BURY_THRESHOLD:
                entry["buried"] = True
                entry["buried_at"] = datetime.now(timezone.utc).isoformat()
                pattern_data[key] = entry
                actions.append(ImprovementAction(
                    action="demote",
                    pattern_key=key,
                    reason=f"Auto-buried: success ratio {degraded['success_ratio']:.2f} below {PATTERN_BURY_THRESHOLD}",
                    confidence=0.95,
                ))

        _save_json(PATTERN_SUCCESS, pattern_data)
        self._build_alerts(actions)
        self._last_review = datetime.now(timezone.utc).isoformat()

        return actions

    @property
    def ad_hoc_tracking_count(self) -> int:
        return len(self._ad_hoc_sqls)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
self_improver = SelfImprover()
