"""
safety_guardrails.py — Phase 23: Standalone Safety Guardrails Layer
====================================================================
A clean, reusable, standalone safety layer for the KYSM Agentic RAG architecture.
Decoupled from the orchestrator — usable by any agent, API endpoint, or worker.

Architecture:
    SafetyGuardrailsLayer  (top-level API)
        CompositeEngine     (runs all registered engines)
            CrossModuleEscalationEngine
            SchemaEnumerationEngine
            DeniedTableProbeEngine
            DataExfiltrationEngine
            TemporalInferenceEngine
            RoleImpersonationEngine

Unified API:
    guard(query, role_id, tables, ...) -> GuardVerdict
    SafetyGuardrailsLayer.check(context) -> GuardVerdict

Integration:
    - Backward-compatible with existing SecuritySentinel
    - Uses the same ROLE_SCOPE_MAP, thresholds, and detection logic
    - Can run alongside or replace the legacy sentinel
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# Core Verdict Types
# =============================================================================

class GuardAction(Enum):
    ALLOW = "allow"   # Query passes through
    WARN  = "warn"    # Query allowed but flag for review
    BLOCK = "block"   # Query denied

    # Internal routing helpers
    @property
    def is_allowed(self) -> bool:
        return self in (GuardAction.ALLOW, GuardAction.WARN)

    @property
    def is_blocked(self) -> bool:
        return self == GuardAction.BLOCK

    @property
    def is_flagged(self) -> bool:
        return self == GuardAction.WARN


class ThreatSeverity(Enum):
    INFO     = 0
    LOW      = 1
    MEDIUM   = 2
    HIGH     = 3
    CRITICAL = 4


@dataclass
class GuardVerdict:
    """
    Unified, simplified safety verdict.
    Returned by every check in the SafetyGuardrailsLayer.
    """
    is_safe: bool = True          # True = no threat detected
    action: GuardAction = GuardAction.ALLOW
    threat_type: Optional[str] = None   # e.g. "cross_module_escalation"
    threat_family: Optional[str] = None # e.g. "security" | "compliance" | "operational"
    severity: ThreatSeverity = ThreatSeverity.INFO
    confidence: float = 0.0       # 0.0–1.0
    reason: str = ""              # Human-readable one-line summary
    evidence: List[str] = field(default_factory=list)  # Detailed evidence lines
    remediation: str = ""         # Suggested fix or next step
    engine_name: str = ""         # Which engine produced this verdict
    tightens_auth: bool = False    # If True, caller should apply AuthContext tightening
    session_flags: List[str] = field(default_factory=list)  # Flags to record on session
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Convenience helpers
    @property
    def is_blocked(self) -> bool:
        return self.action == GuardAction.BLOCK

    @property
    def is_flagged(self) -> bool:
        return self.action == GuardAction.WARN

    def as_dict(self) -> Dict[str, Any]:
        return {
            "is_safe": self.is_safe,
            "action": self.action.value,
            "threat_type": self.threat_type,
            "threat_family": self.threat_family,
            "severity": self.severity.value,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
            "evidence": self.evidence[:4],
            "remediation": self.remediation,
            "engine": self.engine_name,
            "tightens_auth": self.tightens_auth,
            "session_flags": self.session_flags,
        }


# =============================================================================
# Guard Context — Input to every engine check
# =============================================================================

@dataclass
class GuardContext:
    """
    All context needed to evaluate a query against safety policies.
    Passed to every GuardEngine.check() call.
    """
    query: str
    role_id: str
    session_id: str
    tables_accessed: List[str] = field(default_factory=list)
    domains_accessed: List[str] = field(default_factory=list)
    graph_hop_depth: int = 0
    row_count: int = 0
    temporal_mode: str = "none"        # "none" | "key_date" | "fiscal_year" | "fiscal"
    denied_table_access: bool = False   # True = user tried to access a table that was blocked
    is_critical_report: bool = False    # Phase 22: P0 executive report flag
    # AuthContext fields (for tightening)
    tightness_level: int = 0           # Current session tightness (0=normal, 3=max)


# =============================================================================
# Session Profile — Persistent per-session threat tracking
# =============================================================================

@dataclass
class SessionProfile:
    """Tracks a single user session's threat state over time."""
    session_id: str
    role_id: str
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    queries_logged: int = 0
    # Threat counters
    cross_module_attempts: int = 0
    denied_access_attempts: int = 0
    schema_enum_score: float = 0.0      # 0.0–1.0, escalates with bulk discovery
    temporal_anomaly_score: float = 0.0
    # Access tracking
    tables_accessed: List[str] = field(default_factory=list)
    domains_accessed: List[str] = field(default_factory=list)
    graph_hop_depths: List[int] = field(default_factory=list)
    query_hash_history: List[str] = field(default_factory=list)  # last 20
    # Session state
    threat_flags: List[str] = field(default_factory=list)
    tightness_level: int = 0           # 0=normal, 1=partial, 2=lockdown
    # Lockout
    locked_until: Optional[float] = None
    locked_reason: Optional[str] = None

    def is_locked(self) -> bool:
        if self.locked_until is None:
            return False
        return time.time() < self.locked_until

    def record_access(self, tables: List[str], domains: List[str], hop_depth: int):
        self.last_activity = time.time()
        self.queries_logged += 1
        for t in tables:
            if t.upper() not in [x.upper() for x in self.tables_accessed]:
                self.tables_accessed.append(t)
        for d in domains:
            if d.lower() not in [x.lower() for x in self.domains_accessed]:
                self.domains_accessed.append(d)
        if hop_depth > 0:
            self.graph_hop_depths.append(hop_depth)

    def add_flag(self, flag: str):
        if flag not in self.threat_flags:
            self.threat_flags.append(flag)

    def lock(self, duration_seconds: int, reason: str):
        self.locked_until = time.time() + duration_seconds
        self.locked_reason = reason
        self.tightness_level = 3


# =============================================================================
# Guard Engine Protocol
# =============================================================================

class GuardEngine(ABC):
    """
    Abstract base for all safety guard engines.
    Each engine checks for one category of threat.
    """

    name: str = "base"
    description: str = ""

    @abstractmethod
    def check(
        self,
        ctx: GuardContext,
        profile: SessionProfile,
    ) -> Optional[GuardVerdict]:
        """
        Evaluate ctx + profile for this engine's threat type.
        Return None if this engine doesn't apply (not a threat).
        Return a GuardVerdict (safe or threat detected).
        """
        ...

    def on_threat(
        self,
        ctx: GuardContext,
        profile: SessionProfile,
        threat_type: str,
        threat_family: str,
        severity: ThreatSeverity,
        confidence: float,
        reason: str,
        evidence: List[str],
        action: GuardAction = GuardAction.WARN,
        tightens_auth: bool = False,
        flags: Optional[List[str]] = None,
        remediation: str = "",
    ) -> GuardVerdict:
        """Helper — construct and return a threat verdict."""
        return GuardVerdict(
            is_safe=False,
            action=action,
            threat_type=threat_type,
            threat_family=threat_family,
            severity=severity,
            confidence=confidence,
            reason=reason,
            evidence=evidence,
            engine_name=self.name,
            tightens_auth=tightens_auth,
            session_flags=flags or [],
            remediation=remediation,
        )

    def on_safe(self) -> GuardVerdict:
        """Helper — return a clean pass verdict."""
        return GuardVerdict(
            is_safe=True,
            action=GuardAction.ALLOW,
            engine_name=self.name,
        )


# =============================================================================
# Role Scope Map — canonical source of role permissions
# =============================================================================

ROLE_SCOPE_MAP: Dict[str, List[str]] = {
    "AP_CLERK": [
        "LFA1", "LFB1", "LFBK", "LFC1", "LFASS",
        "EKKO", "EKPO", "EKES",
        "BSIK", "BSAK", "BSEG",
        "ADRC",
    ],
    "HR_ADMIN": [
        "PA0001", "PA0002", "PA0008", "PA0021",
        "PB4000", "PB4100",
        "T001",
    ],
    "CFO_GLOBAL": [
        "LFA1", "KNA1", "MARA", "MARD", "MBEW",
        "EKKO", "EKPO", "VBAK", "VBAP", "BSEG",
        "COEP", "COSP", "COSS", "ANLC", "ANLA",
    ],
    "PROCUREMENT_MANAGER_EU": [
        "LFA1", "LFB1", "EINA", "EINE", "EORD",
        "EKKO", "EKPO", "EKET",
        "MARA", "MARC", "MAPL",
    ],
    "MM_CLERK": [
        "MARA", "MARC", "MARD", "MBEW", "MSKA", "MSLB", "MKOL",
        "EINA", "EINE", "EKKO", "EKPO", "EKET",
        "QALS", "QAMV",
    ],
    "SD_CLERK": [
        "KNA1", "KNB1", "KNVV",
        "VBAK", "VBAP", "VBEP", "LIKP", "LIPS",
        "VBRK", "VBRP",
    ],
    "FI_ACCOUNTANT": [
        "BSEG", "BKPF", "BSID", "BSAD", "BSIK", "BSAK",
        "SKA1", "SKB1", "T001", "T003",
    ],
    "WAREHOUSE_MANAGER": [
        "LQUA", "LAGP", "MLGT", "LEIN", "LEUN",
        "MARD", "MSKA", "MSLB",
        "QALS",
    ],
    "QM_INSPECTOR": [
        "QALS", "QAMV", "QAVE", "QSCP", "QSBD",
        "MARA", "MAPL",
    ],
    "GUEST": [
        "T001", "T003", "T001U",
    ],
}


# =============================================================================
# Domain Buckets — for cross-domain detection
# =============================================================================

DOMAIN_BUCKETS: Dict[str, List[str]] = {
    "finance":   ["fi", "accounting", "controlling", "co", "ap", "ar", "gl", "finance"],
    "hr":        ["hr", "payroll", "personnel", "employee"],
    "mm":        ["material_master", "purchasing", "inventory", "mm", "logistics"],
    "sd":        ["sales", "distribution", "crm", "sd"],
    "qm":        ["quality", "qm", "inspection"],
    "wm":        ["warehouse", "wm", "storage"],
}


ROLE_PRIMARY_BUCKET: Dict[str, str] = {
    "AP_CLERK":                 "finance",
    "HR_ADMIN":                 "hr",
    "CFO_GLOBAL":               "finance",
    "PROCUREMENT_MANAGER_EU":   "mm",
    "MM_CLERK":                 "mm",
    "SD_CLERK":                 "sd",
    "FI_ACCOUNTANT":            "finance",
    "WAREHOUSE_MANAGER":        "wm",
    "QM_INSPECTOR":             "qm",
    "GUEST":                    "finance",
}


# =============================================================================
# Detection Engine 1: Cross-Module Escalation
# =============================================================================

class CrossModuleEscalationEngine(GuardEngine):
    """
    Detect when a user accesses tables/domains outside their authorized role scope.
    e.g., HR_ADMIN querying FI tables (BSEG, COSP) via graph traversal.
    """

    name = "CrossModuleEscalation"
    description = "Flags access to tables or domains outside the user's authorized scope."

    def check(self, ctx: GuardContext, profile: SessionProfile) -> Optional[GuardVerdict]:
        role_id = ctx.role_id
        in_scope = set(ROLE_SCOPE_MAP.get(role_id, []))
        if not in_scope:
            return None  # No scope defined — can't detect escalation

        # Tables outside scope
        out_of_scope_tables = [
            t for t in ctx.tables_accessed
            if t.upper() not in {x.upper() for x in in_scope}
        ]

        # Domain crossing
        role_bucket = ROLE_PRIMARY_BUCKET.get(role_id)
        domain_cross = False
        if role_bucket:
            for domain in ctx.domains_accessed:
                d_lower = domain.lower()
                bucket_hit = False
                for bucket_name, keywords in DOMAIN_BUCKETS.items():
                    if any(kw in d_lower for kw in keywords):
                        if bucket_name != role_bucket and bucket_name != role_bucket.capitalize():
                            domain_cross = True
                            break

        # Cross-module escalation detected
        if out_of_scope_tables or domain_cross:
            evidence = []
            if out_of_scope_tables:
                evidence.append(
                    f"Out-of-scope tables ({len(out_of_scope_tables)}): "
                    f"{', '.join(out_of_scope_tables[:5])}"
                )
            if domain_cross:
                evidence.append(f"Domain bucket switched to unrelated domain: {ctx.domains_accessed}")

            # Confidence based on proportion of out-of-scope tables
            if ctx.tables_accessed:
                ratio = len(out_of_scope_tables) / len(ctx.tables_accessed)
                confidence = min(0.6 + ratio * 0.35, 0.95)
            else:
                confidence = 0.75

            severity = ThreatSeverity.HIGH if len(out_of_scope_tables) > 2 else ThreatSeverity.MEDIUM
            action = GuardAction.WARN
            if len(out_of_scope_tables) > 4:
                action = GuardAction.BLOCK

            return self.on_threat(
                ctx=ctx,
                profile=profile,
                threat_type="cross_module_escalation",
                threat_family="security",
                severity=severity,
                confidence=confidence,
                reason=(
                    f"Role '{role_id}' accessed {len(out_of_scope_tables)} out-of-scope table(s)"
                    + (f" and {len(ctx.domains_accessed)} unrelated domain(s)" if domain_cross else "")
                ),
                evidence=evidence,
                action=action,
                tightens_auth=(action == GuardAction.BLOCK),
                flags=["CROSS_MODULE_ESCALATION"],
                remediation=(
                    "Request access to the required domain through the standard "
                    "SAP role assignment process."
                ),
            )

        return self.on_safe()


# =============================================================================
# Detection Engine 2: Schema Enumeration
# =============================================================================

class SchemaEnumerationEngine(GuardEngine):
    """
    Detect bulk schema discovery probes — rapid asking for many tables
    or "show me all tables" patterns.
    """

    name = "SchemaEnumeration"
    description = "Flags rapid bulk table discovery patterns."

    SCHEMA_ENUM_KEYWORDS = [
        "all tables", "every table", "list all tables", "show all tables",
        "ddic", "table list", "table names", "all ddic", "system tables",
        "what tables", "which tables",
    ]

    def check(self, ctx: GuardContext, profile: SessionProfile) -> Optional[GuardVerdict]:
        query_lower = ctx.query.lower()
        tables_accessed = ctx.tables_accessed

        # Check 1: Keyword probe (asking for all tables)
        keyword_probe = any(kw in query_lower for kw in self.SCHEMA_ENUM_KEYWORDS)

        # Check 2: New tables discovered in this query
        existing_upper = {t.upper() for t in profile.tables_accessed}
        new_tables = [t for t in tables_accessed if t.upper() not in existing_upper]

        # Check 3: Rapid new table discovery rate
        if new_tables:
            rate = len(new_tables)
            if rate >= 5 or keyword_probe:
                evidence = []
                if keyword_probe:
                    evidence.append(f"Schema enumeration keyword detected in query")
                if new_tables:
                    evidence.append(
                        f"Discovered {len(new_tables)} new table(s): "
                        f"{', '.join(new_tables[:8])}"
                    )

                confidence = (
                    0.95 if keyword_probe
                    else min(0.5 + rate * 0.1, 0.95)
                )
                severity = ThreatSeverity.HIGH if rate >= 10 else ThreatSeverity.MEDIUM

                return self.on_threat(
                    ctx=ctx,
                    profile=profile,
                    threat_type="schema_enumeration",
                    threat_family="security",
                    severity=severity,
                    confidence=confidence,
                    reason=f"Schema enumeration probe detected: {len(new_tables)} new tables requested",
                    evidence=evidence,
                    action=GuardAction.WARN,
                    flags=["BULK_ENUM"],
                    remediation=(
                        "Specify the exact tables needed for your analysis. "
                        "Bulk table discovery is restricted."
                    ),
                )

        return self.on_safe()


# =============================================================================
# Detection Engine 3: Denied Table Probe
# =============================================================================

class DeniedTableProbeEngine(GuardEngine):
    """
    Detect repeated attempts to access explicitly denied tables.
    Tracks globally across all sessions.
    """

    name = "DeniedTableProbe"
    description = "Flags repeated access attempts to explicitly denied tables."

    # Per-role denied tables
    DENIED_TABLES_BY_ROLE: Dict[str, Set[str]] = {
        "HR_ADMIN":    {"BSEG", "COSP", "COSS", "ANLC", "ANLA"},
        "AP_CLERK":    {"PA0001", "PA0002", "PA0008", "PA0021"},
        "GUEST":       {"BSEG", "LFA1", "KNA1", "EKKO", "VBAK"},
    }

    def __init__(self):
        super().__init__()
        self._probe_counts: Dict[str, int] = {}   # session_id → count
        self._lock = Lock()
        self.probe_threshold: int = 2

    def check(self, ctx: GuardContext, profile: SessionProfile) -> Optional[GuardVerdict]:
        denied_tables = self.DENIED_TABLES_BY_ROLE.get(ctx.role_id, set())
        if not denied_tables:
            return None

        # Check if current query touches any denied tables
        accessed_denied = [
            t for t in ctx.tables_accessed
            if t.upper() in {x.upper() for x in denied_tables}
        ]

        if not accessed_denied and not ctx.denied_table_access:
            return self.on_safe()

        # Increment probe counter for this session
        with self._lock:
            self._probe_counts[ctx.session_id] = self._probe_counts.get(ctx.session_id, 0) + 1
            count = self._probe_counts[ctx.session_id]

        if count >= self.probe_threshold:
            severity = ThreatSeverity.HIGH
            action = GuardAction.BLOCK if count >= 4 else GuardAction.WARN
            return self.on_threat(
                ctx=ctx,
                profile=profile,
                threat_type="denied_table_probe",
                threat_family="security",
                severity=severity,
                confidence=min(0.7 + count * 0.05, 0.95),
                reason=(
                    f"Role '{ctx.role_id}' attempted denied table access "
                    f"{count} time(s) (threshold={self.probe_threshold})"
                ),
                evidence=[
                    f"Denied table(s) accessed: {', '.join(accessed_denied[:5]) or 'blocked table'}",
                    f"Session probe count: {count}",
                ],
                action=action,
                tightens_auth=(count >= 4),
                flags=["DENIED_TABLE_PROBE"],
                remediation=(
                    "Access to these tables is not permitted for your role. "
                    "Contact your SAP administrator if access is required."
                ),
            )

        # First attempt — warn only
        return self.on_threat(
            ctx=ctx,
            profile=profile,
            threat_type="denied_table_probe",
            threat_family="security",
            severity=ThreatSeverity.MEDIUM,
            confidence=0.6,
            reason=f"First denied-table access attempt by role '{ctx.role_id}'",
            evidence=[
                f"Attempted denied tables: {', '.join(accessed_denied[:5])}",
                f"Probe count: {count} (threshold: {self.probe_threshold})",
            ],
            action=GuardAction.WARN,
            flags=["DENIED_TABLE_PROBE"],
            remediation="This table is not permitted for your role.",
        )


# =============================================================================
# Detection Engine 4: Data Exfiltration
# =============================================================================

class DataExfiltrationEngine(GuardEngine):
    """
    Flag unusually large result sets — could be data exfiltration attempt.
    """

    name = "DataExfiltration"
    description = "Flags requests that return unusually large result sets."

    # Thresholds per role
    ROW_THRESHOLDS: Dict[str, int] = {
        "CFO_GLOBAL":              100000,  # Execs can legitimately pull large reports
        "HR_ADMIN":                500,
        "AP_CLERK":                5000,
        "MM_CLERK":                5000,
        "PROCUREMENT_MANAGER_EU":  10000,
        "SD_CLERK":                10000,
        "FI_ACCOUNTANT":           5000,
        "WAREHOUSE_MANAGER":       5000,
        "QM_INSPECTOR":            1000,
        "GUEST":                   100,
    }

    def check(self, ctx: GuardContext, profile: SessionProfile) -> Optional[GuardVerdict]:
        threshold = self.ROW_THRESHOLDS.get(ctx.role_id, 5000)
        row_count = ctx.row_count

        # Allow critical reports to pull more (Phase 22 flag)
        if ctx.is_critical_report:
            threshold = threshold * 3

        if row_count > threshold:
            ratio = row_count / threshold
            confidence = min(0.5 + ratio * 0.2, 0.95)
            severity = ThreatSeverity.HIGH if ratio > 5 else ThreatSeverity.MEDIUM
            action = GuardAction.BLOCK if ratio > 10 else GuardAction.WARN

            return self.on_threat(
                ctx=ctx,
                profile=profile,
                threat_type="data_exfiltration",
                threat_family="security",
                severity=severity,
                confidence=confidence,
                reason=(
                    f"Result set of {row_count:,} rows exceeds threshold {threshold:,} "
                    f"for role '{ctx.role_id}'"
                ),
                evidence=[
                    f"Row count: {row_count:,} (threshold: {threshold:,})",
                    f"Excess ratio: {ratio:.1f}x",
                    f"Query excerpt: {ctx.query[:150]}",
                ],
                action=action,
                flags=["DATA_EXFILTRATION"],
                remediation=(
                    "Add specific filters to your query (company code, date range, "
                    "material group, etc.) to reduce the result set size."
                ),
            )

        return self.on_safe()


# =============================================================================
# Detection Engine 5: Temporal Inference
# =============================================================================

class TemporalInferenceEngine(GuardEngine):
    """
    Detect queries targeting restricted historical periods outside role scope.
    e.g., HR_ADMIN querying 10-year-old payroll data.
    """

    name = "TemporalInference"
    description = "Flags queries targeting restricted historical periods."

    HISTORICAL_RESTRICTED: Set[str] = {"HR_ADMIN", "AP_CLERK"}

    def check(self, ctx: GuardContext, profile: SessionProfile) -> Optional[GuardVerdict]:
        if ctx.temporal_mode in ("fiscal_year", "key_date", "fiscal"):
            if ctx.role_id in self.HISTORICAL_RESTRICTED:
                # Increment temporal anomaly score
                profile.temporal_anomaly_score = min(
                    profile.temporal_anomaly_score + 0.2, 1.0
                )

                if profile.temporal_anomaly_score >= 0.6:
                    severity = ThreatSeverity.MEDIUM
                    action = GuardAction.WARN

                    return self.on_threat(
                        ctx=ctx,
                        profile=profile,
                        threat_type="temporal_inference",
                        threat_family="compliance",
                        severity=severity,
                        confidence=profile.temporal_anomaly_score,
                        reason=(
                            f"Role '{ctx.role_id}' querying historical period "
                            f"(mode={ctx.temporal_mode}) — restricted for this role"
                        ),
                        evidence=[
                            f"Temporal mode: {ctx.temporal_mode}",
                            f"Role: {ctx.role_id} (historical-restricted)",
                            f"Anomaly score: {profile.temporal_anomaly_score:.2f}",
                        ],
                        action=action,
                        flags=["TEMPORAL_INFERENCE"],
                        remediation=(
                            "Historical data access for this role requires "
                            "special authorization. Use current period data only."
                        ),
                    )

        return self.on_safe()


# =============================================================================
# Detection Engine 6: Role Impersonation
# =============================================================================

class RoleImpersonationEngine(GuardEngine):
    """
    Detect sudden domain shifts in a session — legitimate user switching
    to an unrelated domain mid-session (could indicate session hijacking).
    """

    name = "RoleImpersonation"
    description = "Flags mid-session domain switching that is inconsistent with the user's role."

    def check(self, ctx: GuardContext, profile: SessionProfile) -> Optional[GuardVerdict]:
        role_bucket = ROLE_PRIMARY_BUCKET.get(ctx.role_id)
        if not role_bucket:
            return None

        # Check if session has queried in a different bucket before
        if profile.domains_accessed:
            last_domain = profile.domains_accessed[-1]
            last_bucket_hit = None
            for bucket_name, keywords in DOMAIN_BUCKETS.items():
                if any(kw in last_domain.lower() for kw in keywords):
                    last_bucket_hit = bucket_name
                    break

            # Domain switch to unrelated bucket
            if last_bucket_hit and last_bucket_hit != role_bucket:
                # Count how many different buckets accessed this session
                buckets_hit: Set[str] = set()
                for domain in profile.domains_accessed:
                    for bucket_name, keywords in DOMAIN_BUCKETS.items():
                        if any(kw in domain.lower() for kw in keywords):
                            buckets_hit.add(bucket_name)

                if len(buckets_hit) >= 3:
                    severity = ThreatSeverity.HIGH
                    action = GuardAction.BLOCK if len(buckets_hit) >= 4 else GuardAction.WARN

                    return self.on_threat(
                        ctx=ctx,
                        profile=profile,
                        threat_type="role_impersonation",
                        threat_family="security",
                        severity=severity,
                        confidence=min(0.5 + len(buckets_hit) * 0.1, 0.95),
                        reason=(
                            f"Session spanning {len(buckets_hit)} unrelated domain buckets "
                            f"('{ctx.role_id}' role) — possible session hijacking"
                        ),
                        evidence=[
                            f"Domains accessed this session: {', '.join(profile.domains_accessed[-6:])}",
                            f"Buckets: {', '.join(sorted(buckets_hit))}",
                            f"Role primary bucket: {role_bucket}",
                        ],
                        action=action,
                        tightens_auth=True,
                        flags=["ROLE_IMPERSONATION", "MULTI_DOMAIN_SESSION"],
                        remediation=(
                            "Your session has accessed multiple unrelated domains. "
                            "Please start a new session for each domain scope."
                        ),
                    )

        return self.on_safe()


# =============================================================================
# Detection Engine 7: SQL Injection Probe  (Phase 23 new engine)
# =============================================================================

class SQLInjectionEngine(GuardEngine):
    """
    Detect SQL injection patterns in the natural language query.
    Catches common injection vectors before they reach the SQL executor.
    """

    name = "SQLInjection"
    description = "Detects SQL injection patterns in user queries."

    # Sorted by confidence descending — first match wins
    INJECTION_PATTERNS: List[Tuple[str, str, float]] = [
        # CRITICAL (0.95)
        (r";\s*DROP\s+TABLE", "DROP TABLE injection", 0.95),
        (r";\s*DELETE\s+FROM", "DELETE FROM injection", 0.95),
        (r";\s*TRUNCATE", "TRUNCATE injection", 0.95),
        # HIGH (0.85-0.90)
        (r"UNION\s+SELECT", "UNION SELECT injection", 0.85),
        (r"sleep\s*\(\s*\d+\s*\)", "time-based blind injection (SLEEP)", 0.85),
        (r"waitfor\s+delay", "time-based blind injection (WAITFOR)", 0.85),
        (r"OR\s+1\s*=\s*1", "OR 1=1 injection", 0.9),
        (r"EXEC\s*\(\s*@", "EXEC() injection", 0.9),
        # MEDIUM (0.75-0.80)
        (r"1\s*=\s*1", "tautology (1=1)", 0.8),
        (r"'\s*OR\s*'", "string tautology injection", 0.75),
        # LOW (0.70)
        (r"--\s*$", "SQL comment at end of line", 0.7),
        (r"xp_", "extended stored procedure (xp_)", 0.7),
        (r"'\s*;\s*", "multiple statement injection", 0.7),
    ]

    def check(self, ctx: GuardContext, profile: SessionProfile) -> Optional[GuardVerdict]:
        query_lower = ctx.query.lower()

        for pattern, description, conf_boost in self.INJECTION_PATTERNS:
            import re
            if re.search(pattern, query_lower, re.IGNORECASE):
                return self.on_threat(
                    ctx=ctx,
                    profile=profile,
                    threat_type="sql_injection_probe",
                    threat_family="security",
                    severity=ThreatSeverity.CRITICAL,
                    confidence=conf_boost,
                    reason=f"SQL injection pattern detected: {description}",
                    evidence=[
                        f"Pattern matched: {pattern}",
                        f"Query: {ctx.query[:200]}",
                    ],
                    action=GuardAction.BLOCK,
                    tightens_auth=True,
                    flags=["SQL_INJECTION"],
                    remediation=(
                        "SQL injection is blocked. Your query has been denied. "
                        "If this was a legitimate use of these keywords, "
                        "rephrase your request."
                    ),
                )

        return self.on_safe()


# =============================================================================
# Detection Engine 8: Output PII Leak  (Phase 23 new engine)
# =============================================================================

class OutputPIILeakEngine(GuardEngine):
    """
    Detect queries that specifically target PII-containing tables/fields
    without proper authorization.
    """

    name = "OutputPIILeak"
    description = "Flags access to PII-containing tables without appropriate clearance."

    PII_TABLES: Set[str] = {
        "ADRC",   # Address (all entities)
        "PA0002", # HR: Personal data
        "PA0008", # HR: Payroll
        "KNA1",   # Customer master: personal names/addresses
        "BUT000", # BP master: personal data
    }

    PII_ROLES: Set[str] = {
        "HR_ADMIN",
        "CFO_GLOBAL",
    }

    def check(self, ctx: GuardContext, profile: SessionProfile) -> Optional[GuardVerdict]:
        if ctx.role_id in self.PII_ROLES:
            return None  # Authorized for PII

        accessed_pii = [
            t for t in ctx.tables_accessed
            if t.upper() in {x.upper() for x in self.PII_TABLES}
        ]

        if accessed_pii:
            return self.on_threat(
                ctx=ctx,
                profile=profile,
                threat_type="pii_leak_attempt",
                threat_family="compliance",
                severity=ThreatSeverity.HIGH,
                confidence=0.85,
                reason=(
                    f"Role '{ctx.role_id}' accessing PII table(s) without clearance: "
                    f"{', '.join(accessed_pii)}"
                ),
                evidence=[
                    f"PII tables accessed: {', '.join(accessed_pii)}",
                    f"Role '{ctx.role_id}' is not PII-authorized",
                ],
                action=GuardAction.WARN,
                flags=["PII_LEAK"],
                remediation=(
                    "Access to PII tables requires HR_ADMIN or CFO_GLOBAL role. "
                    "Request elevated access through proper channels."
                ),
            )

        return self.on_safe()


# =============================================================================
# Main Safety Guardrails Layer
# =============================================================================

class SafetyGuardrailsLayer:
    """
    Standalone, reusable safety layer for KYSM agents and APIs.

    Modes:
      DISABLED  — Pass through, no monitoring (returns safe verdict)
      AUDIT     — Monitor and log, never intervene
      ENFORCING — Monitor, warn, AND dynamically tighten AuthContext

    Usage:
        guard = SafetyGuardrailsLayer()
        verdict = guard.guard(
            query="show me all vendors",
            role_id="AP_CLERK",
            session_id="ap_clerk_123",
            tables_accessed=["LFA1"],
        )
        if not verdict.is_safe:
            print(f"THREAT: {verdict.reason}")
    """

    DEFAULT_ENGINES: List[type] = [
        SQLInjectionEngine,
        CrossModuleEscalationEngine,
        SchemaEnumerationEngine,
        DeniedTableProbeEngine,
        DataExfiltrationEngine,
        TemporalInferenceEngine,
        RoleImpersonationEngine,
        OutputPIILeakEngine,
    ]

    def __init__(
        self,
        mode: str = "ENFORCING",
        engines: Optional[List[GuardEngine]] = None,
        lockout_duration: int = 300,
        strict: bool = False,  # If True, even WARN verdict logs alert
    ):
        """
        Args:
            mode: "DISABLED" | "AUDIT" | "ENFORCING"
            engines: List of GuardEngine instances (default: all 8 engines)
            lockout_duration: Seconds to lock a session on CRITICAL threat
            strict: If True, log WARN verdicts as well as BLOCK
        """
        self.mode = mode.upper()
        self.lockout_duration = lockout_duration
        self.strict = strict

        # Instantiate engines
        if engines is not None:
            self.engines = engines
        else:
            self.engines = [e() for e in self.DEFAULT_ENGINES]

        # Session profiles: session_id → SessionProfile
        self._profiles: Dict[str, SessionProfile] = {}
        self._profiles_lock = Lock()

        # Alert callbacks: (verdict, session_id) -> None
        self._alert_callbacks: List[Callable[[GuardVerdict, str], None]] = []

        logger.info(
            f"[SafetyGuardrailsLayer] Initialized in {self.mode} mode "
            f"with {len(self.engines)} engines: "
            f"{', '.join(e.name for e in self.engines)}"
        )

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def guard(
        self,
        query: str,
        role_id: str,
        session_id: str,
        tables_accessed: Optional[List[str]] = None,
        domains_accessed: Optional[List[str]] = None,
        graph_hop_depth: int = 0,
        row_count: int = 0,
        temporal_mode: str = "none",
        denied_table_access: bool = False,
        is_critical_report: bool = False,
    ) -> GuardVerdict:
        """
        Unified safety check — primary entry point.

        Args:
            query: Natural language query string
            role_id: SAP role key (e.g. "AP_CLERK", "CFO_GLOBAL")
            session_id: Unique session identifier
            tables_accessed: List of SAP tables involved
            domains_accessed: List of domain names involved
            graph_hop_depth: Graph traversal depth (0=none)
            row_count: Rows returned by this query
            temporal_mode: "none" | "key_date" | "fiscal_year" | "fiscal"
            denied_table_access: True if user tried to access blocked table
            is_critical_report: Phase 22 P0 executive report flag

        Returns:
            GuardVerdict with is_safe=True (allowed) or is_safe=False (threat)
        """
        if self.mode == "DISABLED":
            return GuardVerdict(is_safe=True, action=GuardAction.ALLOW)

        ctx = GuardContext(
            query=query,
            role_id=role_id,
            session_id=session_id,
            tables_accessed=tables_accessed or [],
            domains_accessed=domains_accessed or [],
            graph_hop_depth=graph_hop_depth,
            row_count=row_count,
            temporal_mode=temporal_mode,
            denied_table_access=denied_table_access,
            is_critical_report=is_critical_report,
        )

        profile = self._get_or_create_profile(session_id, role_id)

        # Check if session is locked
        if profile.is_locked():
            return GuardVerdict(
                is_safe=False,
                action=GuardAction.BLOCK,
                threat_type="session_locked",
                threat_family="security",
                severity=ThreatSeverity.CRITICAL,
                confidence=1.0,
                reason=f"Session is locked: {profile.locked_reason}",
                evidence=[f"Locked until {datetime.fromtimestamp(profile.locked_until):%Y-%m-%d %H:%M:%S}"],
                remediation="Wait for lockout to expire or contact your administrator.",
                session_flags=["SESSION_LOCKED"],
            )

        # Update profile
        profile.record_access(
            tables=ctx.tables_accessed,
            domains=ctx.domains_accessed,
            hop_depth=ctx.graph_hop_depth,
        )

        # Run all engines in order
        worst_verdict: Optional[GuardVerdict] = None
        worst_severity = ThreatSeverity.INFO

        for engine in self.engines:
            try:
                verdict = engine.check(ctx, profile)
            except Exception as e:
                logger.warning(f"[{engine.name}] Engine error: {e}")
                continue

            if verdict is None:
                continue

            if not verdict.is_safe:
                # Track worst verdict
                if verdict.severity.value >= worst_severity.value:
                    worst_verdict = verdict
                    worst_severity = verdict.severity

                # Record in profile
                for flag in verdict.session_flags:
                    profile.add_flag(flag)

                # Lockout on CRITICAL
                if worst_severity == ThreatSeverity.CRITICAL:
                    profile.lock(self.lockout_duration, verdict.reason)

                # Alert callbacks
                self._fire_alerts(verdict, session_id, role_id)

                # Log
                self._log_verdict(verdict, role_id)

                # ENFORCING mode: escalate BLOCK immediately
                if self.mode == "ENFORCING" and verdict.action == GuardAction.BLOCK:
                    logger.warning(
                        f"[SafetyGuardrailsLayer] BLOCKING query from role={role_id} "
                        f"session={session_id[:20]}... threat={verdict.threat_type}"
                    )
                    return verdict

        # AUDIT or ENFORCING (non-block path)
        if worst_verdict is not None:
            # AUDIT mode: never block, downgrade BLOCK to WARN
            if self.mode == "AUDIT" and worst_verdict.action == GuardAction.BLOCK:
                from copy import copy
                audit_verdict = copy(worst_verdict)
                audit_verdict.action = GuardAction.WARN
                audit_verdict.is_safe = False
                return audit_verdict
            if self.mode == "ENFORCING":
                # Apply tightening hints
                if worst_verdict.tightens_auth:
                    logger.info(
                        f"[SafetyGuardrailsLayer] Soft-tightening auth for "
                        f"role={role_id} session={session_id[:20]}..."
                    )
            return worst_verdict

        return GuardVerdict(is_safe=True, action=GuardAction.ALLOW)

    def guard_context(self, ctx: GuardContext) -> GuardVerdict:
        """Convenience — pass a GuardContext directly."""
        return self.guard(
            query=ctx.query,
            role_id=ctx.role_id,
            session_id=ctx.session_id,
            tables_accessed=ctx.tables_accessed,
            domains_accessed=ctx.domains_accessed,
            graph_hop_depth=ctx.graph_hop_depth,
            row_count=ctx.row_count,
            temporal_mode=ctx.temporal_mode,
            denied_table_access=ctx.denied_table_access,
            is_critical_report=ctx.is_critical_report,
        )

    def set_mode(self, mode: str) -> None:
        """Change the operating mode at runtime."""
        self.mode = mode.upper()
        logger.info(f"[SafetyGuardrailsLayer] Mode changed to {self.mode}")

    def register_alert_callback(self, cb: Callable[[GuardVerdict, str], None]) -> None:
        """Register a callback for security alerts (webhook, SIEM, etc.)."""
        self._alert_callbacks.append(cb)

    def get_session_profile(self, session_id: str) -> Optional[SessionProfile]:
        """Get the threat profile for a session (for debugging/admin)."""
        with self._profiles_lock:
            return self._profiles.get(session_id)

    def reset_session(self, session_id: str) -> None:
        """Clear a session's threat profile."""
        with self._profiles_lock:
            self._profiles.pop(session_id, None)
        logger.info(f"[SafetyGuardrailsLayer] Session reset: {session_id[:20]}...")

    def get_threat_stats(self) -> Dict[str, Any]:
        """Return aggregate threat statistics across all sessions."""
        with self._profiles_lock:
            total = len(self._profiles)
            locked = sum(1 for p in self._profiles.values() if p.is_locked())
            flagged = sum(len(p.threat_flags) for p in self._profiles.values())
            return {
                "active_sessions": total,
                "locked_sessions": locked,
                "total_threat_flags": flagged,
                "mode": self.mode,
                "engine_count": len(self.engines),
            }

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _get_or_create_profile(self, session_id: str, role_id: str) -> SessionProfile:
        with self._profiles_lock:
            if session_id not in self._profiles:
                self._profiles[session_id] = SessionProfile(
                    session_id=session_id,
                    role_id=role_id,
                )
            return self._profiles[session_id]

    def _fire_alerts(self, verdict: GuardVerdict, session_id: str, role_id: str) -> None:
        for cb in self._alert_callbacks:
            try:
                cb(verdict, session_id)
            except Exception as e:
                logger.error(f"[SafetyGuardrailsLayer] Alert callback error: {e}")

    def _log_verdict(self, verdict: GuardVerdict, role_id: str) -> None:
        if verdict.action == GuardAction.BLOCK:
            logger.warning(
                f"[SafetyGuardrailsLayer] BLOCK | {verdict.threat_type} | "
                f"severity={verdict.severity.value} | confidence={verdict.confidence:.2f} | "
                f"role={role_id} | reason={verdict.reason}"
            )
        elif verdict.action == GuardAction.WARN or self.strict:
            logger.info(
                f"[SafetyGuardrailsLayer] WARN  | {verdict.threat_type} | "
                f"severity={verdict.severity.value} | role={role_id} | reason={verdict.reason}"
            )


# =============================================================================
# Backward-Compatible Adapter — wraps SafetyGuardrailsLayer as SecuritySentinel
# =============================================================================

def create_sentinel_from_guardrails(
    mode: str = "ENFORCING",
    **kwargs
) -> "LegacySentinelAdapter":
    """
    Factory — creates a SecuritySentinel-compatible adapter
    backed by the new SafetyGuardrailsLayer.
    """
    return LegacySentinelAdapter(SafetyGuardrailsLayer(mode=mode, **kwargs))


class LegacySentinelAdapter:
    """
    Adapter that wraps SafetyGuardrailsLayer to expose the old
    SecuritySentinel API (evaluate, get_sentinel, etc.).

    Existing orchestrator code using SecuritySentinel can be migrated
    one import at a time via:
        from app.core.safety_guardrails import get_sentinel

    which returns this adapter.
    """

    def __init__(self, layer: SafetyGuardrailsLayer):
        self._layer = layer
        self.mode = layer.mode

    def evaluate(
        self,
        query: str,
        auth_context,        # SAPAuthContext — used for role_id
        session_id: str,
        tables_accessed: Optional[List[str]] = None,
        domains_accessed: Optional[List[str]] = None,
        graph_hop_depth: int = 0,
        row_count: int = 0,
        temporal_mode: str = "none",
        denied_table_access: bool = False,
    ):
        """Mirrors the old SecuritySentinel.evaluate() signature."""
        role_id = getattr(auth_context, "role_id", "GUEST")
        verdict = self._layer.guard(
            query=query,
            role_id=role_id,
            session_id=session_id,
            tables_accessed=tables_accessed or [],
            domains_accessed=domains_accessed or [],
            graph_hop_depth=graph_hop_depth,
            row_count=row_count,
            temporal_mode=temporal_mode,
            denied_table_access=denied_table_access,
        )

        # Convert to old ThreatVerdict format
        from dataclasses import dataclass, field

        @dataclass
        class LegacyThreatVerdict:
            threat_detected: bool = False
            threat_type: Optional[Any] = None
            severity: Optional[Any] = None
            confidence: float = 0.0
            evidence: List[str] = field(default_factory=list)
            recommended_action: str = "allow"
            session_flags: List[str] = field(default_factory=list)
            tighten_hints: Dict[str, Any] = field(default_factory=dict)

        from enum import Enum

        class _ThreatType(Enum):
            CROSS_MODULE_ESCALATION = "cross_module_escalation"
            SCHEMA_ENUMERATION = "schema_enumeration"
            DENIED_TABLE_PROBE = "denied_table_probe"
            DATA_EXFILTRATION = "data_exfiltration"
            TEMPORAL_INFERENCE = "temporal_inference"
            ROLE_IMPERSONATION = "role_impersonation"
            SQL_INJECTION_PROBE = "sql_injection_probe"
            PII_LEAK_ATTEMPT = "pii_leak_attempt"
            SESSION_LOCKED = "session_locked"

        class _ThreatSeverity(Enum):
            INFO = 0
            LOW = 1
            MEDIUM = 2
            HIGH = 3
            CRITICAL = 4

        lv = LegacyThreatVerdict()
        lv.threat_detected = not verdict.is_safe
        if verdict.threat_type:
            try:
                lv.threat_type = _ThreatType(verdict.threat_type)
            except ValueError:
                lv.threat_type = _ThreatType.SESSION_LOCKED
        else:
            lv.threat_type = None
        try:
            lv.severity = _ThreatSeverity(verdict.severity.value)
        except (ValueError, AttributeError):
            lv.severity = _ThreatSeverity.INFO
        lv.confidence = verdict.confidence
        lv.evidence = verdict.evidence
        lv.recommended_action = verdict.action.value
        lv.session_flags = verdict.session_flags
        if verdict.tightens_auth:
            lv.tighten_hints = {"tighten": True}
        return lv

    def get_session_profile(self, session_id: str):
        return self._layer.get_session_profile(session_id)

    def get_threat_stats(self) -> Dict[str, Any]:
        return self._layer.get_threat_stats()

    def reset_session(self, session_id: str) -> None:
        self._layer.reset_session(session_id)

    def apply_tightening_to_auth_context(self, verdict, auth_context) -> None:
        """Stub — auth tightening is now handled via guard verdict."""
        pass

    def alert_security_team(self, verdict, session_id, role_id) -> None:
        """Stub — alerts are now handled via register_alert_callback."""
        pass


# =============================================================================
# Module-level singleton — backward-compatible with existing orchestrator
# =============================================================================

_guardrails_layer: Optional[SafetyGuardrailsLayer] = None
_sentinel_adapter: Optional[LegacySentinelAdapter] = None


def get_guardrails() -> SafetyGuardrailsLayer:
    """Get the module-level SafetyGuardrailsLayer singleton."""
    global _guardrails_layer
    if _guardrails_layer is None:
        _guardrails_layer = SafetyGuardrailsLayer(mode="ENFORCING")
    return _guardrails_layer


def get_sentinel() -> LegacySentinelAdapter:
    """
    Drop-in replacement for the old get_sentinel().
    Existing orchestrator code: from app.core.security_sentinel import get_sentinel
    New code:            from app.core.safety_guardrails import get_sentinel
    Both return a sentinel-compatible adapter.
    """
    global _sentinel_adapter
    if _sentinel_adapter is None:
        _sentinel_adapter = LegacySentinelAdapter(get_guardrails())
    return _sentinel_adapter


def set_guardrails_mode(mode: str) -> None:
    """Change mode at runtime — DISABLED | AUDIT | ENFORCING."""
    get_guardrails().set_mode(mode)


# =============================================================================
# Convenience function — single-call API
# =============================================================================

def guard(
    query: str,
    role_id: str,
    session_id: str,
    **kwargs,
) -> GuardVerdict:
    """
    One-shot safety check.
    Usage: guard("show me all vendors", "AP_CLERK", "session_123")
    """
    return get_guardrails().guard(
        query=query,
        role_id=role_id,
        session_id=session_id,
        **kwargs
    )
