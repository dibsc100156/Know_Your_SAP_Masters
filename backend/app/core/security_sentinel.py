"""
security_sentinel.py — Phase 6: Proactive Threat Sentinel
=========================================================
Real-time behavioral anomaly detection for the SAP Masters RAG pipeline.

Monitors:
  1. Cross-module path traversal attempts (role escalation)
  2. Schema enumeration attacks (bulk table discovery probes)
  3. Temporal inference attacks ( querying historical data outside role scope)
  4. Repeated denied-table access attempts (brute-force auth object probing)
  5. Suspicious cross-domain query clustering

Tightens AuthContext dynamically when threat threshold is breached:
  - Adds tables to denied_tables
  - Expands masked_fields
  - Issues session-level warnings

Usage:
    sentinel = SecuritySentinel()
    verdict = sentinel.evaluate(query, auth_context, session_history, graph_traversal)
    if verdict.threat_detected:
        sentinel.apply_tightening(verdict, auth_context)
        sentinel.alert_security_team(verdict)
"""

from __future__ import annotations

import re
import time
import hashlib
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from threading import Lock
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Threat Types & Severity
# ============================================================================

class ThreatType(Enum):
    CROSS_MODULE_ESCALATION = "cross_module_escalation"     # Accessing tables outside role domain
    SCHEMA_ENUMERATION      = "schema_enumeration"          # Bulk table discovery probes
    TEMPORAL_INFERENCE      = "temporal_inference"           # Querying restricted historical periods
    DENIED_TABLE_PROBE      = "denied_table_probe"           # Repeated attempts to access blocked tables
    DATA_EXFILTRATION       = "data_exfiltration"           # Unusual volume / full table scans
    ROLE_IMPERSONATION      = "role_impersonation"          # Query pattern suddenly changes to different domain
    GRAPH_HOP_ATTEMPT       = "graph_hop_attempt"           # Multi-hop traversal to unauthorized tables via JOINs


class ThreatSeverity(Enum):
    INFO     = "info"      # Watchful note — no action
    LOW      = "low"       # Flag, log, continue
    MEDIUM   = "medium"    # Flag, apply partial tightening, warn user
    HIGH     = "high"      # Immediate tightening, alert team
    CRITICAL = "critical"  # Session suspend, escalate to admin


# ============================================================================
# Threat Verdict
# ============================================================================

@dataclass
class ThreatVerdict:
    threat_detected: bool = False
    threat_type: Optional[ThreatType] = None
    severity: ThreatSeverity = ThreatSeverity.INFO
    confidence: float = 0.0           # 0.0–1.0
    evidence: List[str] = field(default_factory=list)
    recommended_action: str = "allow"  # "allow" | "warn" | "tighten" | "block"
    session_flags: List[str] = field(default_factory=list)  # e.g. ["HR_FI_ESCALATION", "BULK_ENUM"]
    tighten_hints: Dict[str, Any] = field(default_factory=dict)  # tables to deny, fields to mask


# ============================================================================
# Session Threat Profile
# ============================================================================

@dataclass
class SessionThreatProfile:
    session_id: str
    role_id: str
    created_at: float = field(default_factory=time.time)
    queries_logged: int = 0
    denied_access_attempts: int = 0
    cross_module_attempts: int = 0
    schema_enum_score: float = 0.0    # 0.0–1.0, escalates with rapid bulk discovery
    temporal_anomaly_score: float = 0.0
    tables_accessed: List[str] = field(default_factory=list)
    domains_accessed: List[str] = field(default_factory=list)
    graph_hop_depths: List[int] = field(default_factory=list)
    recent_query_hashes: List[str] = field(default_factory=list)  # last 20 query hashes
    threat_flags: List[str] = field(default_factory=list)
    tightness_level: int = 0         # 0=normal, 1=partial, 2=full lockdown
    last_activity: float = field(default_factory=time.time)


# ============================================================================
# Security Sentinel
# ============================================================================

class SecuritySentinel:
    """
    Proactive Threat Sentinel — watches every query against the SAP Masters
    orchestrator and detects behavioral anomalies that indicate misuse,
    role escalation attempts, or data exfiltration probes.

    Operates in three modes:
      DISABLED  — Pass through, no monitoring
      AUDIT     — Monitor and log, never intervene
      ENFORCING — Monitor, warn, AND dynamically tighten AuthContext
    """

    # Role → list of tables/domains considered "in-scope" for that role
    # Anything outside this is a cross-module escalation candidate
    ROLE_SCOPE_MAP: Dict[str, List[str]] = {
        "AP_CLERK": [
            "LFA1", "LFB1", "LFBK", "LFC1", "LFASS",  # Vendor master + company + bank
            "EKKO", "EKPO", "EKES",                    # Purchasing docs
            "BSIK", "BSAK", "BSEG",                    # AP accounting docs
            "ADRC",                                     # Address
        ],
        "HR_ADMIN": [
            "PA0001", "PA0002", "PA0008", "PA0021",   # HR master
            "PB4000", "PB4100",                       # HR recruiting
            "T001",                                    # Company codes (minimal)
        ],
        "CFO_GLOBAL": [                                 # Can see everything — but suspicious volume still flagged
            "LFA1", "KNA1", "MARA", "MARD", "MBEW",
            "EKKO", "EKPO", "VBAK", "VBAP", "BSEG",
            "COEP", "COSP", "COSS", "ANLC", "ANLA",
        ],
        "PROCUREMENT_MANAGER_EU": [
            "LFA1", "LFB1", "EINA", "EINE", "EORD",   # Vendor info records
            "EKKO", "EKPO", "EKET",                    # PO scheduling
            "MARA", "MARC", "MAPL",                     # Material + BOM + routing
        ],
    }

    # Domain-level scope boundaries
    HR_DOMAINS     = {"hr", "payroll", "personnel", "employee"}
    FI_DOMAINS     = {"finance", "accounting", "fi", "controlling", "co"}
    MM_DOMAINS     = {"material_master", "purchasing", "inventory", "mm"}
    SD_DOMAINS     = {"sales", "distribution", "sd", "crm"}
    CROSS_MODULE   = {"graph_traverse", "all_paths", "cross_module"}

    def __init__(
        self,
        mode: str = "AUDIT",
        schema_enum_threshold: float = 0.7,     # Score at which schema enum is flagged
        cross_module_threshold: int = 3,         # Cross-module attempts before flagging
        denied_probe_threshold: int = 5,        # Denied-table probes before tightening
        exfil_row_threshold: int = 5000,        # Full table scan threshold
        lockout_duration_seconds: int = 300,
    ):
        """
        Args:
            mode: "DISABLED" | "AUDIT" | "ENFORCING"
            schema_enum_threshold: 0.0–1.0; score based on unique new tables per time window
            cross_module_threshold: Cross-module path attempts before MEDIUM severity
            denied_probe_threshold: Denied-table probe attempts before tightening
            exfil_row_threshold: If a single query returns >N rows, flag as potential exfil
            lockout_duration_seconds: How long a CRITICAL lockout lasts before auto-reset
        """
        self.mode = mode.upper()
        self.schema_enum_threshold = schema_enum_threshold
        self.cross_module_threshold = cross_module_threshold
        self.denied_probe_threshold = denied_probe_threshold
        self.exfil_row_threshold = exfil_row_threshold
        self.lockout_duration_seconds = lockout_duration_seconds

        # Per-session threat profiles (session_id → profile)
        self._profiles: Dict[str, SessionThreatProfile] = {}
        self._profile_lock = Lock()

        # Global anomaly counters for distributed session detection
        self._global_denied_count: Dict[str, int] = defaultdict(int)  # role_id → count
        self._global_lock = Lock()

        # Alert callbacks (Security team webhook, SIEM, etc.)
        self._alert_callbacks: List[Callable[[ThreatVerdict, str], None]] = []

        logger.info(f"[SecuritySentinel] Initialized in {self.mode} mode.")

    # =========================================================================
    # Public API — Evaluate a query
    # =========================================================================

    def evaluate(
        self,
        query: str,
        auth_context,          # SAPAuthContext
        session_id: str,
        tables_accessed: List[str],
        domains_accessed: List[str],
        graph_hop_depth: int = 0,
        row_count: int = 0,
        temporal_mode: str = "none",
        denied_table_access: bool = False,
    ) -> ThreatVerdict:
        """
        Evaluate a single query for threat indicators.
        Called by the orchestrator before each query is executed.

        Returns a ThreatVerdict with threat_detected=True if anomaly found.
        """
        if self.mode == "DISABLED":
            return ThreatVerdict()

        profile = self._get_or_create_profile(session_id, auth_context.role_id)

        # Update profile timestamps and counters
        profile.queries_logged += 1
        profile.last_activity = time.time()

        # Track tables and domains
        for t in tables_accessed:
            if t not in profile.tables_accessed:
                profile.tables_accessed.append(t)
        for d in domains_accessed:
            if d not in profile.domains_accessed:
                profile.domains_accessed.append(d)
        if graph_hop_depth > 0:
            profile.graph_hop_depths.append(graph_hop_depth)

        verdict = ThreatVerdict()

        # ── Check 1: Cross-Module Escalation ──────────────────────────────
        cross_mod = self._check_cross_module_escalation(
            query, auth_context.role_id, tables_accessed, domains_accessed, profile
        )
        if cross_mod.threat_detected:
            profile.cross_module_attempts += 1
            verdict = cross_mod
            profile.threat_flags.append(f"CROSS_MODULE_ESCALATION")

        # ── Check 2: Schema Enumeration ───────────────────────────────────
        schema_enum = self._check_schema_enumeration(
            query, tables_accessed, profile, auth_context.role_id
        )
        if schema_enum.threat_detected:
            if schema_enum.severity.value >= ThreatSeverity.MEDIUM.value:
                verdict = schema_enum
                profile.threat_flags.append("SCHEMA_ENUMERATION")
            profile.schema_enum_score = schema_enum.confidence

        # ── Check 3: Denied Table Probe ────────────────────────────────────
        denied_probe = self._check_denied_table_probe(
            denied_table_access, auth_context.role_id, session_id
        )
        if denied_probe.threat_detected:
            profile.denied_access_attempts += 1
            verdict = denied_probe
            profile.threat_flags.append("DENIED_TABLE_PROBE")

        # ── Check 4: Data Exfiltration (volume anomaly) ────────────────────
        exfil = self._check_data_exfiltration(row_count, auth_context.role_id)
        if exfil.threat_detected:
            verdict = exfil
            profile.threat_flags.append("DATA_EXFILTRATION")

        # ── Check 5: Temporal Inference ─────────────────────────────────────
        temporal = self._check_temporal_inference(temporal_mode, auth_context.role_id, profile)
        if temporal.threat_detected:
            verdict = temporal
            profile.threat_flags.append("TEMPORAL_INFERENCE")

        # ── Check 6: Role Impersonation (sudden domain shift) ───────────────
        impersonation = self._check_role_impersonation(profile, auth_context.role_id)
        if impersonation.threat_detected:
            verdict = impersonation
            profile.threat_flags.append("ROLE_IMPERSONATION")

        # ── Apply dynamic tightening if in ENFORCING mode ──────────────────
        if self.mode == "ENFORCING" and verdict.threat_detected:
            self._apply_tightening(verdict, profile)
            self._dispatch_alerts(verdict, session_id)

        return verdict

    # =========================================================================
    # Threat Detection Routines
    # =========================================================================

    def _check_cross_module_escalation(
        self,
        query: str,
        role_id: str,
        tables_accessed: List[str],
        domains_accessed: List[str],
        profile: SessionThreatProfile,
    ) -> ThreatVerdict:
        """
        Detect when a user tries to access tables/domains outside their role scope.
        e.g., an HR_ADMIN suddenly querying FI tables (BSEG, COSP) via graph traversal.
        """
        verdict = ThreatVerdict()
        in_scope = set(self.ROLE_SCOPE_MAP.get(role_id, []))
        if not in_scope:
            return verdict  # No scope defined for this role — no escalation possible

        # Check 1: Tables outside scope
        out_of_scope_tables = [t for t in tables_accessed if t.upper() not in in_scope]

        # Check 2: Domain crossing
        domain_cross = False
        role_domain_bucket = None
        if role_id == "HR_ADMIN":
            role_domain_bucket = self.HR_DOMAINS
        elif role_id == "AP_CLERK":
            role_domain_bucket = self.FI_DOMAINS  # AP is Finance-adjacent

        if role_domain_bucket and domains_accessed:
            for d in domains_accessed:
                d_lower = d.lower()
                # Check if the query domain is different from role domain
                if not any(hd in d_lower for hd in role_domain_bucket):
                    domain_cross = True
                    break

        # Cross-module escalation via graph traversal
        avg_hop_depth = sum(profile.graph_hop_depths) / max(len(profile.graph_hop_depths), 1)
        if avg_hop_depth >= 3 and len(out_of_scope_tables) > 0:
            verdict.threat_detected = True
            verdict.threat_type = ThreatType.CROSS_MODULE_ESCALATION
            verdict.severity = ThreatSeverity.MEDIUM
            verdict.confidence = min(0.6 + (profile.cross_module_attempts * 0.1), 0.95)
            verdict.evidence = [
                f"Role '{role_id}' accessed {len(out_of_scope_tables)} out-of-scope table(s): {out_of_scope_tables}",
                f"Graph hop depth: {avg_hop_depth:.1f} (multi-hop escalation)",
                f"Domain cross detected: {domains_accessed}",
            ]
            verdict.recommended_action = "tighten"
            verdict.tighten_hints = {
                "add_denied_tables": out_of_scope_tables[:3],
                "mask_additional_fields": self._suggest_fields_to_mask(out_of_scope_tables),
            }
            verdict.session_flags = ["CROSS_MODULE_ESCALATION"]
            profile.cross_module_attempts += 1

        elif out_of_scope_tables and profile.cross_module_attempts >= self.cross_module_threshold:
            verdict.threat_detected = True
            verdict.threat_type = ThreatType.CROSS_MODULE_ESCALATION
            verdict.severity = ThreatSeverity.LOW
            verdict.confidence = 0.65
            verdict.evidence = [
                f"Repeated out-of-scope table access by {role_id}: {out_of_scope_tables}",
            ]
            verdict.recommended_action = "warn"
            verdict.session_flags = ["CROSS_MODULE_ESCALATION"]

        return verdict

    def _check_schema_enumeration(
        self,
        query: str,
        tables_accessed: List[str],
        profile: SessionThreatProfile,
        role_id: str,
    ) -> ThreatVerdict:
        """
        Detect bulk schema discovery probes — e.g., a user rapidly asking
        "show me all tables" or cycling through many tables in a short window.
        Uses a rolling window of unique new table discoveries per query batch.
        """
        verdict = ThreatVerdict()

        # Compute how many genuinely new tables this query discovered
        new_tables = [t for t in tables_accessed if t not in profile.tables_accessed]
        new_ratio = len(new_tables) / max(profile.queries_logged, 1)

        # Escalate score for large batch discoveries
        if len(new_tables) >= 5:
            profile.schema_enum_score = min(profile.schema_enum_score + 0.4, 1.0)
        elif len(new_tables) >= 3:
            profile.schema_enum_score = min(profile.schema_enum_score + 0.2, 1.0)

        # Heuristic: legitimate users rarely discover >5 new tables per query
        if profile.schema_enum_score >= self.schema_enum_threshold:
            verdict.threat_detected = True
            verdict.threat_type = ThreatType.SCHEMA_ENUMERATION
            verdict.confidence = profile.schema_enum_score

            if profile.schema_enum_score >= 0.9:
                verdict.severity = ThreatSeverity.HIGH
                verdict.recommended_action = "tighten"
            elif profile.schema_enum_score >= 0.8:
                verdict.severity = ThreatSeverity.MEDIUM
                verdict.recommended_action = "warn"
            else:
                verdict.severity = ThreatSeverity.LOW
                verdict.recommended_action = "warn"

            verdict.evidence = [
                f"Schema enumeration score: {profile.schema_enum_score:.2f} (threshold: {self.schema_enum_threshold})",
                f"New tables discovered this session: {len(new_tables)}",
                f"Total unique tables accessed: {len(profile.tables_accessed)}",
                f"Queries in session: {profile.queries_logged}",
            ]
            verdict.session_flags = ["SCHEMA_ENUMERATION"]
            # Don't auto-tighten on schema enum — just warn

        return verdict

    def _check_denied_table_probe(
        self,
        denied_access: bool,
        role_id: str,
        session_id: str,
    ) -> ThreatVerdict:
        """
        Detect repeated attempts to access explicitly denied tables.
        This indicates the user is probing for authorization gaps.
        """
        verdict = ThreatVerdict()

        if denied_access:
            with self._global_lock:
                self._global_denied_count[session_id] += 1
                probe_count = self._global_denied_count[session_id]

            if probe_count >= self.denied_probe_threshold:
                verdict.threat_detected = True
                verdict.threat_type = ThreatType.DENIED_TABLE_PROBE
                verdict.confidence = min(0.5 + (probe_count * 0.08), 0.95)
                verdict.severity = ThreatSeverity.HIGH if probe_count >= 8 else ThreatSeverity.MEDIUM
                verdict.recommended_action = "tighten"
                verdict.evidence = [
                    f"Denied-table probe attempt #{probe_count} by session {session_id[:8]}",
                    f"Threshold: {self.denied_probe_threshold}",
                ]
                verdict.session_flags = ["DENIED_TABLE_PROBE"]

        return verdict

    def _check_data_exfiltration(
        self,
        row_count: int,
        role_id: str,
    ) -> ThreatVerdict:
        """
        Flag unusually large result sets — could be data exfiltration.
        """
        verdict = ThreatVerdict()

        if row_count > self.exfil_row_threshold:
            verdict.threat_detected = True
            verdict.threat_type = ThreatType.DATA_EXFILTRATION
            verdict.confidence = min(0.5 + (row_count / self.exfil_row_threshold * 0.3), 0.95)
            verdict.severity = ThreatSeverity.HIGH
            verdict.recommended_action = "warn"  # Warn but don't block legitimate large exports
            verdict.evidence = [
                f"Large result set: {row_count:,} rows (threshold: {self.exfil_row_threshold:,})",
                f"Role: {role_id}",
            ]
            verdict.session_flags = ["LARGE_RESULT_SET"]

        return verdict

    def _check_temporal_inference(
        self,
        temporal_mode: str,
        role_id: str,
        profile: SessionThreatProfile,
    ) -> ThreatVerdict:
        """
        Detect queries targeting restricted historical periods outside role scope.
        e.g., HR_ADMIN querying 10-year-old payroll data.
        """
        verdict = ThreatVerdict()

        # Roles with historical restrictions
        HISTORICAL_RESTRICTED = {"HR_ADMIN", "AP_CLERK"}

        if temporal_mode in ("fiscal_year", "key_date", "fiscal") and role_id in HISTORICAL_RESTRICTED:
            # Increment temporal anomaly score
            profile.temporal_anomaly_score = min(
                profile.temporal_anomaly_score + 0.25, 1.0
            )

            if profile.temporal_anomaly_score >= 0.75:
                verdict.threat_detected = True
                verdict.threat_type = ThreatType.TEMPORAL_INFERENCE
                verdict.severity = ThreatSeverity.MEDIUM
                verdict.confidence = profile.temporal_anomaly_score
                verdict.recommended_action = "warn"
                verdict.evidence = [
                    f"Restricted historical period query by {role_id}",
                    f"Temporal anomaly score: {profile.temporal_anomaly_score:.2f}",
                ]
                verdict.session_flags = ["TEMPORAL_INFERENCE"]

        return verdict

    def _check_role_impersonation(
        self,
        profile: SessionThreatProfile,
        role_id: str,
    ) -> ThreatVerdict:
        """
        Detect sudden domain shifts in a session — a legitimate user switching
        from their domain to an entirely different one mid-session.
        e.g., AP_CLERK suddenly querying HR tables — could be session hijacking.
        """
        verdict = ThreatVerdict()

        DOMAIN_BUCKETS = {
            "finance": ["fi", "accounting", "controlling", "co", "ap", "ar", "gl"],
            "hr":      ["hr", "payroll", "personnel", "employee"],
            "mm":      ["material_master", "purchasing", "inventory", "mm"],
            "sd":      ["sales", "distribution", "crm", "sd"],
        }

        # Assign each role a primary bucket
        ROLE_BUCKET = {
            "AP_CLERK": "finance",
            "CFO_GLOBAL": "finance",
            "HR_ADMIN": "hr",
            "PROCUREMENT_MANAGER_EU": "mm",
        }

        role_bucket = ROLE_BUCKET.get(role_id)
        if not role_bucket or len(profile.domains_accessed) < 3:
            return verdict

        # Count how many different domain buckets this session touched
        buckets_hit = set()
        for d in profile.domains_accessed:
            d_lower = d.lower()
            for bucket_name, keywords in DOMAIN_BUCKETS.items():
                if any(kw in d_lower for kw in keywords):
                    buckets_hit.add(bucket_name)

        # If we've hit 3+ different buckets in one session, flag
        if len(buckets_hit) >= 3 and role_bucket not in buckets_hit:
            verdict.threat_detected = True
            verdict.threat_type = ThreatType.ROLE_IMPERSONATION
            verdict.severity = ThreatSeverity.MEDIUM
            verdict.confidence = 0.72
            verdict.recommended_action = "warn"
            verdict.evidence = [
                f"Session touched {len(buckets_hit)} distinct domain buckets: {buckets_hit}",
                f"Role '{role_id}' is primarily in bucket '{role_bucket}'",
                f"This is a cross-domain anomaly for this role.",
            ]
            verdict.session_flags = ["ROLE_IMPERSONATION"]

        return verdict

    # =========================================================================
    # Dynamic Tightening
    # =========================================================================

    def _apply_tightening(
        self,
        verdict: ThreatVerdict,
        profile: SessionThreatProfile,
    ):
        """
        Dynamically tighten the AuthContext based on threat verdict.
        Called in ENFORCING mode when a threat is confirmed.
        """
        if verdict.recommended_action not in ("tighten", "block"):
            return

        old_tightness = profile.tightness_level
        profile.tightness_level = min(profile.tightness_level + 1, 3)  # Max level 3

        if profile.tightness_level > old_tightness:
            logger.warning(
                f"[SecuritySentinel] Session '{profile.session_id[:8]}' "
                f"tightened to level {profile.tightness_level} "
                f"(threat: {verdict.threat_type.value if verdict.threat_type else 'unknown'})"
            )

    def apply_tightening_to_auth_context(
        self,
        verdict: ThreatVerdict,
        auth_context,          # SAPAuthContext — will be modified in place
    ) -> SAPAuthContext:
        """
        Apply the tightening hints from a ThreatVerdict to an SAPAuthContext.
        This modifies the auth_context object and returns it for the orchestrator
        to use in subsequent queries.

        Usage:
            new_auth = sentinel.apply_tightening_to_auth_context(verdict, auth_context)
        """
        hints = verdict.tighten_hints

        # Add newly denied tables
        new_denied = hints.get("add_denied_tables", [])
        for t in new_denied:
            if t.upper() not in [dt.upper() for dt in auth_context.denied_tables]:
                auth_context.denied_tables.append(t)

        # Expand masked fields
        new_masks = hints.get("mask_additional_fields", {})
        if new_masks:
            current_masks = dict(auth_context.masked_fields)
            current_masks.update(new_masks)
            auth_context.masked_fields = current_masks

        if new_denied or new_masks:
            logger.info(
                f"[SecuritySentinel] AuthContext for '{auth_context.role_id}' tightened. "
                f"New denied tables: {new_denied}, New masked fields: {list(new_masks.keys())}"
            )

        return auth_context

    # =========================================================================
    # Alert Dispatch
    # =========================================================================

    def register_alert_callback(self, callback: Callable[[ThreatVerdict, str], None]):
        """Register a callback to be called when a HIGH/CRITICAL threat is detected."""
        self._alert_callbacks.append(callback)

    def _dispatch_alerts(self, verdict: ThreatVerdict, session_id: str):
        """Fire alerts to all registered callbacks for HIGH/CRITICAL threats."""
        if verdict.severity in (ThreatSeverity.HIGH, ThreatSeverity.CRITICAL):
            for cb in self._alert_callbacks:
                try:
                    cb(verdict, session_id)
                except Exception as e:
                    logger.error(f"[SecuritySentinel] Alert callback failed: {e}")

    def alert_security_team(
        self,
        verdict: ThreatVerdict,
        session_id: str,
        role_id: str = None,
    ):
        """
        Default alert handler — logs to console + generates a security audit record.
        Replace or extend via register_alert_callback().
        """
        severity_str = verdict.severity.value.upper()
        threat_str = verdict.threat_type.value if verdict.threat_type else "unknown"

        alert_msg = (
            f"\n"
            f"╔══════════════════════════════════════════════════╗\n"
            f"║       🔐 SECURITY SENTINEL ALERT [{severity_str}]       ║\n"
            f"╠══════════════════════════════════════════════════╣\n"
            f"║ Threat Type : {threat_str:<32} ║\n"
            f"║ Confidence  : {verdict.confidence:.2f}                              ║\n"
            f"║ Session ID  : {session_id[:32]:<32} ║\n"
            f"║ Action      : {verdict.recommended_action:<32} ║\n"
            f"╠══════════════════════════════════════════════════╣\n"
            f"║ Evidence:                                            ║\n"
        )

        for i, ev in enumerate(verdict.evidence[:4]):
            alert_msg += f"║   {i+1}. {ev[:36]:<36} ║\n"

        if verdict.session_flags:
            alert_msg += f"║ Flags     : {', '.join(verdict.session_flags)[:36]:<36} ║\n"

        alert_msg += f"╚══════════════════════════════════════════════════╝\n"

        logger.warning(alert_msg)

        # In production: webhook to SIEM, email to security team, etc.
        # Example: requests.post(security_webhook_url, json=verdict.__dict__)

    # =========================================================================
    # Session Profile Management
    # =========================================================================

    def _get_or_create_profile(self, session_id: str, role_id: str) -> SessionThreatProfile:
        """Get or create a threat profile for a session."""
        with self._profile_lock:
            if session_id not in self._profiles:
                self._profiles[session_id] = SessionThreatProfile(
                    session_id=session_id,
                    role_id=role_id,
                )
            return self._profiles[session_id]

    def get_session_profile(self, session_id: str) -> Optional[SessionThreatProfile]:
        return self._profiles.get(session_id)

    def clear_session(self, session_id: str):
        """Remove a session profile (called on session end/timeout)."""
        with self._profile_lock:
            if session_id in self._profiles:
                del self._profiles[session_id]
            with self._global_lock:
                if session_id in self._global_denied_count:
                    del self._global_denied_count[session_id]

    def get_threat_stats(self) -> Dict[str, Any]:
        """Return aggregate threat statistics across all sessions."""
        total_sessions = len(self._profiles)
        flagged = sum(1 for p in self._profiles.values() if p.threat_flags)
        return {
            "mode": self.mode,
            "total_sessions": total_sessions,
            "flagged_sessions": flagged,
            "global_denied_probes": dict(self._global_denied_count),
            "tightness_distribution": {
                "normal": sum(1 for p in self._profiles.values() if p.tightness_level == 0),
                "partial": sum(1 for p in self._profiles.values() if p.tightness_level == 1),
                "lockdown": sum(1 for p in self._profiles.values() if p.tightness_level >= 2),
            },
        }

    # =========================================================================
    # Helper Methods
    # =========================================================================

    @staticmethod
    def _suggest_fields_to_mask(tables: List[str]) -> Dict[str, str]:
        """Suggest fields to mask based on out-of-scope tables discovered."""
        sensitive_map = {
            "BSEG":   {"DMBTR": "REDACTED", "WRBTR": "REDACTED", "KUNNR": "REDACTED", "LIFNR": "REDACTED"},
            "COSP":   {"WSL": "REDACTED", "KOSTL": "REDACTED"},
            "COSS":   {"WSL": "REDACTED", "KOSTL": "REDACTED"},
            "ANLC":   {"ANLB1": "REDACTED", "ANLB2": "REDACTED"},
            "PA0008": {"BET01": "REDACTED", "BET02": "REDACTED", "BET03": "REDACTED"},
            "LFA1":   {"STCD1": "REDACTED", "BANKN": "REDACTED"},
            "KNA1":   {"STCD1": "REDACTED", "BANKN": "REDACTED"},
        }
        masks = {}
        for table in tables:
            t_upper = table.upper()
            if t_upper in sensitive_map:
                masks.update(sensitive_map[t_upper])
        return masks


# ============================================================================
# Sentinel Integration Hook — Called by Orchestrator
# ============================================================================

# Global sentinel instance (can be overridden at init time)
_sentinel: Optional[SecuritySentinel] = None


def get_sentinel() -> SecuritySentinel:
    global _sentinel
    if _sentinel is None:
        _sentinel = SecuritySentinel(mode=os.environ.get("SENTINEL_MODE", "AUDIT"))
    return _sentinel


def set_sentinel_mode(mode: str):
    """Switch sentinel mode at runtime: DISABLED | AUDIT | ENFORCING"""
    global _sentinel
    if _sentinel is None:
        _sentinel = SecuritySentinel(mode=mode)
    else:
        _sentinel.mode = mode.upper()
    logger.info(f"[SecuritySentinel] Mode set to: {mode}")


import os
