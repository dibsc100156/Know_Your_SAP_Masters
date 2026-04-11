"""
memory_layer.py — Persistent Memory Layer (Phase 4)
====================================================
Learns from every query across sessions. Stores:
  - query_history.jsonl      : Every query with timestamp, role, domain, SQL, result
  - pattern_success.json    : SQL patterns that worked (boosted in ranking)
  - pattern_failures.json   : Patterns that produced bad results (buried)
  - schema_discoveries.json : Tables discovered but not in initial schema
  - gotchas.json            : Known failure patterns / edge cases
  - user_preferences.json   : Per-role output format preferences

Usage:
  from app.core.memory_layer import sap_memory, SAPSessionMemory
  sap_memory.log_query(query=..., role=..., domain=..., sql=..., result=...)
  sap_memory.log_pattern_success(domain=..., pattern_name=..., sql_fingerprint=...)
  sap_memory.log_pattern_failure(domain=..., pattern_name=..., sql_fingerprint=..., error=...)
  top_patterns = sap_memory.get_boosted_patterns(domain="purchasing", top_k=5)
"""

import json
import os
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pathlib import Path
from threading import Lock
from collections import defaultdict

# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------
WORKSPACE = Path(os.environ.get("WORKSPACE_ROOT", r"C:\Users\vishnu\.openclaw\workspace"))
SAP_MEMORY_DIR = WORKSPACE / "memory" / "sap_sessions"
SAP_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

QUERY_HISTORY     = SAP_MEMORY_DIR / "query_history.jsonl"
PATTERN_SUCCESS   = SAP_MEMORY_DIR / "pattern_success.json"
PATTERN_FAILURES  = SAP_MEMORY_DIR / "pattern_failures.json"
SCHEMA_DISCOVERIES = SAP_MEMORY_DIR / "schema_discoveries.json"
GOTCHAS           = SAP_MEMORY_DIR / "gotchas.json"
USER_PREFS        = SAP_MEMORY_DIR / "user_preferences.json"


def _sql_fingerprint(sql: str) -> str:
    """Normalize SQL to a comparable hash (strip whitespace, uppercase)."""
    normalized = " ".join(sql.upper().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _load_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _append_jsonl(path: Path, record: Dict):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def _save_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# SAPSessionMemory — core class
# ---------------------------------------------------------------------------
class SAPSessionMemory:
    """
    Thread-safe persistent memory for the SAP Masters chatbot.
    All writes are append-only (jsonl) or atomic (json).
    """

    def __init__(self):
        self._lock = Lock()
        self._gotchas_cache: Optional[List[Dict]] = None
        self._pattern_success_cache: Optional[Dict] = None
        self._pattern_failure_cache: Optional[Dict] = None

    # -------------------------------------------------------------------------
    # Query Logging
    # -------------------------------------------------------------------------
    def log_query(
        self,
        query: str,
        role: str,
        domain: str,
        sql: str,
        tables_used: List[str],
        critique_score: float,
        result: str,          # "success" | "empty" | "error" | "partial"
        execution_time_ms: int,
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Append a complete query record to query_history.jsonl.
        Returns the record written.
        """
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "role": role,
            "domain": domain,
            "sql_fingerprint": _sql_fingerprint(sql),
            "tables_used": tables_used,
            "critique_score": critique_score,
            "result": result,
            "execution_time_ms": execution_time_ms,
            "error": error,
        }
        with self._lock:
            _append_jsonl(QUERY_HISTORY, record)
        return record

    # -------------------------------------------------------------------------
    # Pattern Success Logging
    # -------------------------------------------------------------------------
    def log_pattern_success(
        self,
        domain: str,
        pattern_name: str,
        sql: str,
        tables: List[str],
        user_rating: Optional[int] = None,  # 1-5 thumbs up/down if provided
    ):
        """
        Increment success count for a pattern. Boosts its ranking score.
        """
        fp = _sql_fingerprint(sql)
        with self._lock:
            data = _load_json(PATTERN_SUCCESS, {})
            key = f"{domain}:{pattern_name}"
            if key not in data:
                data[key] = {
                    "domain": domain,
                    "pattern_name": pattern_name,
                    "success_count": 0,
                    "failure_count": 0,
                    "sql_fingerprints": [],
                    "avg_critique_score": 0.0,
                    "total_critique_score": 0.0,
                    "last_used": None,
                }
            entry = data[key]
            entry["success_count"] += 1
            entry["last_used"] = datetime.now(timezone.utc).isoformat()
            if fp not in entry["sql_fingerprints"]:
                entry["sql_fingerprints"].append(fp)
            if user_rating is not None:
                entry["user_rating"] = max(entry.get("user_rating", 0), user_rating)
            _save_json(PATTERN_SUCCESS, data)
        self._invalidate_caches()

    # -------------------------------------------------------------------------
    # Pattern Failure Logging
    # -------------------------------------------------------------------------
    def log_pattern_failure(
        self,
        domain: str,
        pattern_name: str,
        sql: str,
        tables: List[str],
        error: str,
        critique_score: float,
    ):
        """
        Log a pattern that produced bad results. Increases failure_count.
        """
        fp = _sql_fingerprint(sql)
        with self._lock:
            data = _load_json(PATTERN_FAILURES, {})
            key = f"{domain}:{pattern_name}"
            if key not in data:
                data[key] = {
                    "domain": domain,
                    "pattern_name": pattern_name,
                    "failure_count": 0,
                    "last_failure": None,
                    "errors": [],
                    "sql_fingerprints": [],
                }
            entry = data[key]
            entry["failure_count"] += 1
            entry["last_failure"] = datetime.now(timezone.utc).isoformat()
            if len(entry["errors"]) < 10:  # keep last 10 unique errors
                if error not in entry["errors"]:
                    entry["errors"].append(error)
            if fp not in entry["sql_fingerprints"]:
                entry["sql_fingerprints"].append(fp)
            _save_json(PATTERN_FAILURES, data)

            # Also increment failure count in success file (for ratio tracking)
            success_data = _load_json(PATTERN_SUCCESS, {})
            skey = f"{domain}:{pattern_name}"
            if skey in success_data:
                success_data[skey]["failure_count"] += 1
                success_data[skey]["total_critique_score"] += critique_score
                avg = success_data[skey]["total_critique_score"] / max(success_data[skey]["success_count"], 1)
                success_data[skey]["avg_critique_score"] = round(avg, 3)
                _save_json(PATTERN_SUCCESS, success_data)
        self._invalidate_caches()

    # -------------------------------------------------------------------------
    # Schema Discovery Logging
    # -------------------------------------------------------------------------
    def log_schema_discovery(
        self,
        table: str,
        domain: str,
        discovered_via: str,   # "ddic_query" | "graph_traverse" | "user_hint"
        confidence: float,
        fields: List[str],
    ):
        """
        Log a table discovered at runtime that's not in the initial schema store.
        """
        with self._lock:
            data = _load_json(SCHEMA_DISCOVERIES, {"tables": []})
            existing = {t["table"]: i for i, t in enumerate(data.get("tables", []))}
            now = datetime.now(timezone.utc).isoformat()
            if table in existing:
                idx = existing[table]
                data["tables"][idx]["discovery_count"] += 1
                data["tables"][idx]["last_seen"] = now
                data["tables"][idx]["last_via"] = discovered_via
                data["tables"][idx]["confidence"] = max(data["tables"][idx]["confidence"], confidence)
            else:
                data["tables"].append({
                    "table": table,
                    "domain": domain,
                    "discovered_via": discovered_via,
                    "confidence": confidence,
                    "discovery_count": 1,
                    "first_seen": now,
                    "last_seen": now,
                    "fields": fields[:20],  # cap at 20 fields
                })
            _save_json(SCHEMA_DISCOVERIES, data)

    # -------------------------------------------------------------------------
    # Gotcha Logging
    # -------------------------------------------------------------------------
    def log_gotcha(
        self,
        pattern: str,          # e.g., "LFA1.STCD1 must be masked for AP_CLERK"
        domain: str,
        severity: str,         # "info" | "warn" | "critical"
        description: str,
    ):
        """
        Log a known edge case or failure pattern that the system should remember.
        """
        with self._lock:
            data = _load_json(GOTCHAS, {"gotchas": []})
            fp = hashlib.sha256(pattern.encode()).hexdigest()[:12]
            # Avoid duplicates
            if not any(g.get("hash") == fp for g in data.get("gotchas", [])):
                data["gotchas"].append({
                    "hash": fp,
                    "pattern": pattern,
                    "domain": domain,
                    "severity": severity,
                    "description": description,
                    "logged_at": datetime.now(timezone.utc).isoformat(),
                    "hit_count": 0,
                })
                _save_json(GOTCHAS, data)
                self._invalidate_caches()

    def bump_gotcha_hit(self, pattern_hash: str):
        """Increment hit count when a known gotcha is triggered."""
        with self._lock:
            data = _load_json(GOTCHAS, {"gotchas": []})
            for g in data.get("gotchas", []):
                if g.get("hash") == pattern_hash:
                    g["hit_count"] = g.get("hit_count", 0) + 1
                    break
            _save_json(GOTCHAS, data)

    # -------------------------------------------------------------------------
    # User Preferences
    # -------------------------------------------------------------------------
    def set_user_preference(
        self,
        role: str,
        output_format: str = "table",  # "table" | "json" | "csv"
        max_rows: int = 100,
        include_sql: bool = True,
        language: str = "en",
    ):
        """Set per-role output preferences."""
        with self._lock:
            data = _load_json(USER_PREFS, {"preferences": {}})
            data["preferences"][role] = {
                "output_format": output_format,
                "max_rows": max_rows,
                "include_sql": include_sql,
                "language": language,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            _save_json(USER_PREFS, data)

    def get_user_preference(self, role: str) -> Dict[str, Any]:
        """Get preferences for a role, with sensible defaults."""
        defaults = {
            "output_format": "table",
            "max_rows": 100,
            "include_sql": True,
            "language": "en",
        }
        data = _load_json(USER_PREFS, {"preferences": {}})
        prefs = data.get("preferences", {}).get(role, {})
        return {**defaults, **prefs}

    # -------------------------------------------------------------------------
    # Query — Boosted Patterns
    # -------------------------------------------------------------------------
    def get_boosted_patterns(self, domain: str, top_k: int = 5) -> List[Dict]:
        """
        Return top-k patterns for a domain sorted by success ratio.
        Patterns with high failure rates are excluded.
        """
        data = _load_json(PATTERN_SUCCESS, {})
        domain_patterns = []
        for key, entry in data.items():
            if entry.get("domain") != domain:
                continue
            total = entry.get("success_count", 0) + entry.get("failure_count", 0)
            if total == 0:
                continue
            ratio = entry["success_count"] / total
            # Penalize: don't return patterns that fail >30% of the time
            if ratio < 0.7:
                continue
            domain_patterns.append({
                "key": key,
                "pattern_name": entry["pattern_name"],
                "success_count": entry["success_count"],
                "failure_count": entry.get("failure_count", 0),
                "success_ratio": round(ratio, 3),
                "avg_critique_score": entry.get("avg_critique_score", 0),
                "last_used": entry.get("last_used"),
                "rank_score": round(ratio * entry["success_count"], 3),
            })
        domain_patterns.sort(key=lambda x: x["rank_score"], reverse=True)
        return domain_patterns[:top_k]

    # -------------------------------------------------------------------------
    # Query — Recent History
    # -------------------------------------------------------------------------
    def get_recent_queries(self, limit: int = 20) -> List[Dict]:
        """Return the most recent queries from history."""
        records = _load_jsonl(QUERY_HISTORY)
        return records[-limit:]

    # -------------------------------------------------------------------------
    # Query — Schema Discoveries
    # -------------------------------------------------------------------------
    def get_schema_discoveries(self, domain: Optional[str] = None) -> List[Dict]:
        """Return discovered tables, optionally filtered by domain."""
        data = _load_json(SCHEMA_DISCOVERIES, {"tables": []})
        tables = data.get("tables", [])
        if domain:
            tables = [t for t in tables if t.get("domain") == domain]
        return sorted(tables, key=lambda x: x.get("discovery_count", 0), reverse=True)

    # -------------------------------------------------------------------------
    # Query — Gotchas
    # -------------------------------------------------------------------------
    def get_gotchas(self, domain: Optional[str] = None, severity: Optional[str] = None) -> List[Dict]:
        """Return known gotchas, optionally filtered."""
        data = _load_json(GOTCHAS, {"gotchas": []})
        gotchas = data.get("gotchas", [])
        if domain:
            gotchas = [g for g in gotchas if g.get("domain") == domain]
        if severity:
            gotchas = [g for g in gotchas if g.get("severity") == severity]
        return sorted(gotchas, key=lambda x: x.get("hit_count", 0), reverse=True)

    # -------------------------------------------------------------------------
    # Eval Stats
    # -------------------------------------------------------------------------
    def get_eval_stats(self) -> Dict[str, Any]:
        """Aggregate evaluation metrics across all sessions."""
        records = _load_jsonl(QUERY_HISTORY)
        total = len(records)
        if total == 0:
            return {"total_queries": 0}

        success = sum(1 for r in records if r.get("result") == "success")
        errors = sum(1 for r in records if r.get("result") == "error")
        avg_time = sum(r.get("execution_time_ms", 0) for r in records) / total
        avg_critique = sum(r.get("critique_score", 0) for r in records) / total

        # Domain breakdown
        by_domain: Dict[str, Dict] = defaultdict(lambda: {"total": 0, "success": 0})
        for r in records:
            d = r.get("domain", "unknown")
            by_domain[d]["total"] += 1
            if r.get("result") == "success":
                by_domain[d]["success"] += 1

        return {
            "total_queries": total,
            "successful_queries": success,
            "failed_queries": errors,
            "success_rate": round(success / total, 3),
            "avg_execution_ms": round(avg_time, 1),
            "avg_critique_score": round(avg_critique, 3),
            "by_domain": {k: {**v, "rate": round(v["success"] / max(v["total"], 1), 3)}
                          for k, v in by_domain.items()},
        }

    # -------------------------------------------------------------------------
    # Cache invalidation
    # -------------------------------------------------------------------------
    def _invalidate_caches(self):
        self._gotchas_cache = None
        self._pattern_success_cache = None
        self._pattern_failure_cache = None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
sap_memory = SAPSessionMemory()
