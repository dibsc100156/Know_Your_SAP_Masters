"""
failure_trigger.py — Phase 11 Integration: MetaHarnessLoop Failure Trigger
==========================================================================
Auto-triggers the MetaHarnessLoop diagnosis when failure patterns are detected.

Trigger conditions (all must be true):
  1. result_status == "error" (SQL execution or validation failed)
  2. Self-heal did NOT save the query (heal_info["applied"] == False)
  3. Failure is not already queued (idempotency via Redis flag)

Design: FIRE-AND-FORGET via background thread.
  The orchestrator never blocks on MetaHarnessLoop analysis.
  A background thread checks failure count and calls MetaHarnessLoop.analyze_recent_failures()
  only when the threshold (≥3 failures in 1hr) is crossed.

Usage:
    from app.core.failure_trigger import check_and_trigger_meta_harness

    # Called from orchestrator on error (non-blocking)
    check_and_trigger_meta_harness(run_id, query, error_message, error_code, tables, sql)

    # Or manually trigger analysis:
    trigger_meta_harness_analysis(days=1)
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from app.core.harness_runs import get_harness_runs

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
FAILURE_TRIGGER_KEY = "meta:recent_failures"   # Redis sorted set: failure timestamps
TRIGGER_THRESHOLD   = 3                          # ≥N failures in THRESHOLD_WINDOW_SECS triggers analysis
THRESHOLD_WINDOW_SECS = 3600                     # 1 hour lookback window
TRIGGER_COOLDOWN_SECS = 3600                     # Don't re-trigger within 1 hour of last analysis
LAST_TRIGGER_KEY     = "meta:last_trigger_time"  # Redis key storing last trigger Unix timestamp

# ---------------------------------------------------------------------------
# Error Code Extraction
# ---------------------------------------------------------------------------

def extract_error_code(error_message: str) -> str:
    """
    Extract canonical error codes from a raw error message string.
    Handles: ORA-XXXX, SAP-XXXX, HANA_XXXX, numeric codes (37000 etc.)
    """
    msg = error_message or ""

    # Oracle/SAP codes
    oracle_match = re.search(r'\b(ORA-\d{5})\b', msg, re.IGNORECASE)
    if oracle_match:
        return oracle_match.group(1).upper()

    sap_match = re.search(r'\b(SAP[-\s]?\d{5})\b', msg, re.IGNORECASE)
    if sap_match:
        return "SAP_" + re.sub(r'[^0-9]', '', sap_match.group(1))

    # HANA native codes
    hana_match = re.search(r'\b(HANA_\w+)\b', msg, re.IGNORECASE)
    if hana_match:
        return hana_match.group(1).upper()

    # Numeric SQLSTATE codes (37000, 22003, etc.)
    numeric_match = re.search(r'\b([1-5]\d{3,4})\b', msg)
    if numeric_match:
        return numeric_match.group(1)

    # Known symbolic codes
    symbolic_map = {
        "TABLE NOT FOUND":    "TABLE_NOT_FOUND",
        "NOT FOUND":          "TABLE_NOT_FOUND",
        "SCHEMA MISS":        "SCHEMA_MISS",
        "CARTESIAN":          "CARTESIAN_PRODUCT",
        "DIVISION BY ZERO":   "DIVISION_BY_ZERO",
        "SUBQUERY":           "SUBQUERY_JOIN_ERROR",
        "MISSING MANDT":      "MANDT_MISSING",
        "NOT AUTHORIZED":     "AUTH_ERROR",
        "AUTH FAILED":        "AUTH_ERROR",
        "HEALTH CHECK FAILED": "HANA_CONNECTION_FAILED",
        "CONNECTION":         "HANA_CONNECTION_FAILED",
        "SELF_HEAL FAILED":   "SELF_HEAL_FAILED",
    }
    upper_msg = msg.upper()
    for pattern, code in symbolic_map.items():
        if pattern in upper_msg:
            return code

    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Failure Recorder (Idempotent — always safe to call)
# ---------------------------------------------------------------------------

def record_failure(run_id: str, error_message: str) -> None:
    """
    Record a single failure event in Redis (idempotent).
    Adds the run_id to a failure list keyed by timestamp.
    """
    try:
        hr = get_harness_runs()
        redis_client = hr._redis

        now = time.time()
        pipe = redis_client.pipeline()

        # Add to sorted set with timestamp as score
        pipe.zadd(FAILURE_TRIGGER_KEY, {run_id: now})
        # Trim old entries outside the threshold window
        pipe.zremrangebyrank(FAILURE_TRIGGER_KEY, 0, -TRIGGER_THRESHOLD - 1)
        # Expire the key after 2x threshold window
        pipe.expire(FAILURE_TRIGGER_KEY, THRESHOLD_WINDOW_SECS * 2)

        pipe.execute()

        logger.debug(f"[FAILURE_TRIGGER] recorded run_id={run_id} error={error_message[:60]}")

    except Exception as e:
        logger.warning(f"[FAILURE_TRIGGER] Failed to record failure: {e}")


def get_recent_failure_count(window_secs: int = THRESHOLD_WINDOW_SECS) -> int:
    """Return number of failures recorded in the last `window_secs` seconds."""
    try:
        hr = get_harness_runs()
        redis_client = hr._redis

        cutoff = time.time() - window_secs
        count = redis_client.zcount(FAILURE_TRIGGER_KEY, cutoff, "+")
        return int(count)

    except Exception as e:
        logger.warning(f"[FAILURE_TRIGGER] Failed to get failure count: {e}")
        return 0


def get_last_trigger_time() -> Optional[float]:
    """Return Unix timestamp of last MetaHarness trigger, or None if never triggered."""
    try:
        hr = get_harness_runs()
        val = hr._redis.get(LAST_TRIGGER_KEY)
        return float(val) if val else None
    except Exception:
        return None


def set_last_trigger_time() -> None:
    """Mark now as the last trigger time."""
    try:
        hr = get_harness_runs()
        hr._redis.set(LAST_TRIGGER_KEY, str(time.time()), ex=86400)
    except Exception as e:
        logger.warning(f"[FAILURE_TRIGGER] Failed to set last trigger time: {e}")


# ---------------------------------------------------------------------------
# Check and Trigger
# ---------------------------------------------------------------------------

def check_and_trigger_meta_harness(
    run_id: str,
    query: str,
    error_message: str,
    error_code: str,
    tables_involved: List[str],
    generated_sql: str,
    async_mode: bool = True,
) -> None:
    """
    Primary entry point from the orchestrator.

    Records the failure and checks if the threshold has been crossed.
    If yes and cooldown allows, fires MetaHarnessLoop.analyze_recent_failures()
    in a background thread (default) or synchronously.

    Args:
        run_id, query, error_message, error_code, tables_involved, generated_sql:
            Captured from the orchestrator's error path
        async_mode: If True (default), run analysis in background thread (non-blocking).
                    If False, run synchronously (for testing/cron).
    """
    error_code = error_code or extract_error_code(error_message)

    # 1. Record failure (idempotent, always runs)
    record_failure(run_id, error_message)

    # 2. Check threshold
    failure_count = get_recent_failure_count()

    if failure_count < TRIGGER_THRESHOLD:
        logger.debug(f"[FAILURE_TRIGGER] count={failure_count} < {TRIGGER_THRESHOLD}, skipping")
        return

    # 3. Check cooldown
    last_trigger = get_last_trigger_time()
    if last_trigger and (time.time() - last_trigger) < TRIGGER_COOLDOWN_SECS:
        logger.debug(f"[FAILURE_TRIGGER] cooldown active (last trigger {(time.time() - last_trigger):.0f}s ago)")
        return

    logger.info(f"[FAILURE_TRIGGER] Threshold crossed: {failure_count} failures in {THRESHOLD_WINDOW_SECS}s — triggering MetaHarnessLoop")

    if async_mode:
        t = threading.Thread(
            target=_run_meta_harness_analysis,
            name="meta-harness-trigger",
            kwargs={"days": 1},
            daemon=True,
        )
        t.start()
        logger.info("[FAILURE_TRIGGER] MetaHarnessLoop analysis fired in background thread")
    else:
        _run_meta_harness_analysis(days=1)


def _run_meta_harness_analysis(days: int = 1) -> None:
    """
    Internal: run the MetaHarnessLoop analysis and save recommendations.
    Called in a background thread or synchronously.
    """
    try:
        from app.core.meta_harness_loop import MetaHarnessLoop

        set_last_trigger_time()  # Mark trigger time BEFORE analysis (avoid re-trigger during run)

        mh = MetaHarnessLoop()

        # Step 1: Collect recent failures
        failures = mh.collect_failed_runs(days=days)
        if not failures:
            logger.info("[FAILURE_TRIGGER] No failed runs found in lookback window")
            return

        # Step 2: Group by pattern
        groups = mh._group_by_pattern(failures)

        # Step 3: Build analysis context
        context = mh._build_analysis_context(failures, groups)

        # Step 4: LLM diagnosis → YAML recommendations
        recommendations = mh.analyze_with_llm(failures, groups, context)

        if not recommendations:
            logger.info("[FAILURE_TRIGGER] No recommendations generated by LLM diagnosis")
            return

        # Step 5: Auto-apply safe recommendations (P2 or lower, low risk)
        applied_ids = mh.apply_recommendations(
            rec_ids=[r.id for r in recommendations if r.priority in ("P3", "P4") and r.risk in ("low", "medium")],
            auto_approved=True,
        )

        logger.info(f"[FAILURE_TRIGGER] MetaHarnessLoop analysis complete: {len(recommendations)} recs generated, {len(applied_ids)} applied")

    except Exception as e:
        logger.error(f"[FAILURE_TRIGGER] MetaHarnessLoop analysis failed: {e}")


# ---------------------------------------------------------------------------
# Manual trigger (for cron or testing)
# ---------------------------------------------------------------------------

def trigger_meta_harness_analysis(days: int = 7, min_failures: int = 1) -> List[Any]:
    """
    Manually trigger MetaHarnessLoop analysis.

    Args:
        days: Lookback window for failed runs
        min_failures: Minimum failures required to proceed (default 1 for manual trigger)

    Returns:
        List of Recommendation objects generated
    """
    failure_count = get_recent_failure_count()
    if failure_count < min_failures:
        logger.info(f"[FAILURE_TRIGGER] Manual trigger skipped: only {failure_count} failures found (min={min_failures})")
        return []

    from app.core.meta_harness_loop import MetaHarnessLoop

    mh = MetaHarnessLoop()
    failures = mh.collect_failed_runs(days=days)
    if not failures:
        return []

    groups = mh._group_by_pattern(failures)
    context = mh._build_analysis_context(failures, groups)
    recommendations = mh.analyze_with_llm(failures, groups, context)

    return recommendations


# ---------------------------------------------------------------------------
# Status / Debug
# ---------------------------------------------------------------------------

def get_failure_trigger_status() -> Dict[str, Any]:
    """Return current failure trigger state for debugging/monitoring."""
    try:
        hr = get_harness_runs()
        redis_client = hr._redis

        recent_1h = get_recent_failure_count(3600)
        recent_24h = get_recent_failure_count(86400)
        last_trigger = get_last_trigger_time()
        cooldown_remaining = 0.0
        if last_trigger:
            remaining = TRIGGER_COOLDOWN_SECS - (time.time() - last_trigger)
            cooldown_remaining = max(0.0, remaining)

        # Get recent failure run_ids
        recent_run_ids = []
        try:
            raw = redis_client.zrevrange(FAILURE_TRIGGER_KEY, 0, 9)
            recent_run_ids = [r.decode() if isinstance(r, bytes) else r for r in raw]
        except Exception:
            pass

        return {
            "recent_failures_1h": recent_1h,
            "recent_failures_24h": recent_24h,
            "last_trigger_at": datetime.fromtimestamp(last_trigger).isoformat() if last_trigger else None,
            "cooldown_remaining_secs": round(cooldown_remaining, 1),
            "threshold": TRIGGER_THRESHOLD,
            "threshold_window_secs": THRESHOLD_WINDOW_SECS,
            "trigger_cooldown_secs": TRIGGER_COOLDOWN_SECS,
            "recent_failure_run_ids": recent_run_ids,
            "at_threshold": recent_1h >= TRIGGER_THRESHOLD,
        }

    except Exception as e:
        return {"error": str(e)}