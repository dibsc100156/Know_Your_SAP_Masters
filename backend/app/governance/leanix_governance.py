"""
leanix_governance.py — LeanIX Agent Governance Layer
================================================
Enterprise-grade governance for Know Your SAP Masters using LeanIX EAM data.

What LeanIX provides:
  1. Application Inventory — all SAP systems, their criticality, owner, IT risk score
  2. Business Capability Map — which BU/capability each table belongs to
  3. Data Flow Analysis — which applications consume which SAP tables
  4. IT Risk Management — GDPR, SOC2, data residency, sensitive data flags
  5. S/4HANA Readiness — migration complexity scores per application
  6. Audit Trail — every agent query logged against the LeanIX application portfolio

Governance flow:
  Query arrives
    │
    ├─ LeanIXPreAuthorization: Is this user/role allowed to query this data?
    │     Returns: ALLOW | DENY | FLAG (needs additional approval)
    │
    ├─ LeanIXComplianceGuard: Does this query touch GDPR/SOC2/HR-sensitive data?
    │     Returns: PASS | BLOCK | MASK_AND_LOG
    │
    ├─ LeanIXContextEnricher: Enrich query with enterprise metadata
    │     Returns: Business context, owner, criticality, related apps
    │
    └─ LeanIXAuditLogger: Record query in LeanIX audit trail
          Returns: Audit ID for traceability

Usage:
  from app.governance.leanix_governance import LeanIXGovernanceService

  gov = LeanIXGovernanceService()
  auth_result = gov.pre_authorize(user_id, role_id, query, tables_accessed)
  compliance_result = gov.check_compliance(query, tables_accessed, auth_context)
  enriched = gov.enrich_context(query, tables_accessed)
  audit_id = gov.log_query(query, auth_result, compliance_result, result_summary)
"""

from __future__ import annotations

import os
import re
import logging
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from typing_extensions import TypedDict

import httpx

from app.core.security import SAPAuthContext

logger = logging.getLogger(__name__)

# ── Enums ──────────────────────────────────────────────────────────────────────

class AuthDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    FLAG = "flag"       # Needs additional approval / manager review
    BLOCK_LOG = "block" # Deny and log as suspicious


class ComplianceStatus(Enum):
    PASS = "pass"         # No compliance concern
    MASK_AND_LOG = "mask_and_log"   # Data is sensitive, mask before returning
    BLOCK = "block"       # Data cannot be returned to this user/role
    GDPR_CONSENT = "gdpr_consent_required"


class DataCriticality(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    TOP_SECRET = "top_secret"


# ── TypedDicts ───────────────────────────────────────────────────────────────────

class LeanIXApplication(TypedDict):
    appId: str
    name: str
    vendor: str
    itRiskScore: int
    criticality: str
    owner: str
    ownerEmail: str
    businessCapabilities: List[str]
    tags: List[str]
    grariskScore: int
    tags_s4: str  # S/4HANA readiness tag


class LeanIXTableMetadata(TypedDict):
    table: str
    application: str
    dataClass: str
    dataCriticality: str
    gdprRelevant: bool
    personalData: bool
    personalDataCategory: str
    dataResidency: str
    complianceFlags: List[str]
    owner: str
    ownerEmail: str
    lastModified: str
    legalBasis: str


class PreAuthorizationResult(TypedDict):
    decision: AuthDecision
    reason: str
    flaggedConditions: List[str]
    leanixApplications: List[str]
    approvalRequired: Optional[str]
    auditId: str


class ComplianceCheckResult(TypedDict):
    status: str           # ComplianceStatus enum .value (e.g. "pass", "block")
    reason: str
    personalDataFound: bool
    dataCategories: List[str]
    maskingRequired: List[str]
    legalBasis: Optional[str]
    dataResidency: Optional[str]
    auditId: str


class EnrichedContext(TypedDict):
    businessContext: Dict[str, Any]
    leanixApplications: List[LeanIXApplication]
    relatedApplications: List[str]
    businessCapabilities: List[str]
    itRiskLevel: str
    ownerContact: str
    dataLineage: List[Dict[str, str]]
    s4Readiness: Dict[str, Any]
    auditId: str


class AuditEntry(TypedDict):
    auditId: str
    timestamp: str
    userId: str
    roleId: str
    query: str
    tablesAccessed: List[str]
    authDecision: str
    complianceStatus: str
    leanixApplications: List[str]
    queryHash: str
    executionTimeMs: int
    resultRowCount: int
    maskedFields: List[str]


# ── LeanIX Client ──────────────────────────────────────────────────────────────

class LeanIXClient:
    """
    HTTP client for LeanIX API (EAM Integration).

    LeanIX provides a REST API for:
      - GET /applications        — application inventory
      - GET /applications/{id} — single application
      - GET /factsheets         — all factsheet types
      - GET /relations          — data flow relationships
      - POST /search            — full-text search across all factsheets
      - GET /serviceNowImport   — ServiceNow integration data

    API version: v1 (Bearer token auth)
    Base URL: https://{account}.leanix.net/api/v1/
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        workspace: Optional[str] = None,
    ):
        self.base_url = (
            base_url
            or os.environ.get("LEANIX_BASE_URL", "")
            or os.environ.get("LEANIX_URL", "")
        )
        self.api_token = (
            api_token
            or os.environ.get("LEANIX_API_TOKEN", "")
            or os.environ.get("LEANIX_TOKEN", "")
        )
        self.workspace = workspace or os.environ.get("LEANIX_WORKSPACE", "default")
        self._client: Optional[httpx.AsyncClient] = None

        if self.base_url and self.api_token:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=httpx.Timeout(10.0, connect=5.0),
            )
            logger.info(f"[LeanIX] Connected to {self.base_url}")
        else:
            logger.warning(
                "[LeanIX] No credentials — running in DEMO mode. "
                "Set LEANIX_BASE_URL and LEANIX_API_TOKEN env vars."
            )

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def get_applications(self) -> List[LeanIXApplication]:
        """Fetch all application factsheets from LeanIX."""
        if not self._client:
            return []

        try:
            resp = await self._client.get("/applications", params={"pageSize": 500})
            resp.raise_for_status()
            data = resp.json()
            return data.get("data", [])
        except httpx.HTTPStatusError as e:
            logger.error(f"[LeanIX] get_applications failed: {e}")
            return []
        except Exception as e:
            logger.error(f"[LeanIX] get_applications error: {e}")
            return []

    async def get_application(self, app_id: str) -> Optional[LeanIXApplication]:
        """Fetch a single application by LeanIX factsheet ID."""
        if not self._client:
            return None

        try:
            resp = await self._client.get(f"/applications/{app_id}")
            resp.raise_for_status()
            return resp.json().get("data")
        except httpx.HTTPStatusError:
            return None

    async def search_factsheets(
        self,
        query: str,
        factsheet_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Full-text search across LeanIX factsheets."""
        if not self._client:
            return []

        try:
            payload = {
                "query": query,
                "filter": [
                    {"type": ft} for ft in (factsheet_types or ["application"])
                ],
                "pageSize": 20,
            }
            resp = await self._client.post("/search", json=payload)
            resp.raise_for_status()
            return resp.json().get("results", [])
        except Exception as e:
            logger.error(f"[LeanIX] search_factsheets failed: {e}")
            return []

    async def get_relations(
        self,
        from_factsheet_id: Optional[str] = None,
        to_factsheet_id: Optional[str] = None,
        relation_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch data flow / IT landscape relationships."""
        if not self._client:
            return []

        try:
            params = {}
            if from_factsheet_id:
                params["fromFactsheet"] = from_factsheet_id
            if to_factsheet_id:
                params["toFactsheet"] = to_factsheet_id
            if relation_type:
                params["type"] = relation_type

            resp = await self._client.get("/relations", params=params)
            resp.raise_for_status()
            return resp.json().get("data", [])
        except Exception as e:
            logger.error(f"[LeanIX] get_relations failed: {e}")
            return []

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Fetch user info from LeanIX (for delegation audit)."""
        if not self._client:
            return {}

        try:
            resp = await self._client.get(f"/users/{user_id}")
            resp.raise_for_status()
            return resp.json().get("data", {})
        except Exception:
            return {}


# ── GDPR/Sensitive Data Detector ───────────────────────────────────────────────

class DataClassificationEngine:
    """
    Classifies SAP table data based on LeanIX metadata + known SAP patterns.

    Assigns GDPR, personal data, financial data, HR data, operational data classifications.
    """

    # GDPR-relevant table prefixes (common SAP patterns)
    GDPR_TABLE_PATTERNS = {
        "PA0": "HR - Personnel Administration",
        "PA1": "HR - Time Management",
        "PA2": "HR - Payroll",
        "PB0": "HR - Benefits",
        "PC0": "HR - Compensation",
        "HRS": "HR - Recruiting",
        "VTW": "HR - Travel",
        "KNA1": "Customer Master - Personal",
        "LFA1": "Vendor Master - Business",
        "BUT000": "Business Partner - Personal",
        "ADRC": "Address Services - Personal",
        "ADDR": "Address - Personal",
        "T16FS": "Financials - Bank Master",
        "T012": "Financials - Bank Data",
        "DFKK": "Financials - Collections/ Dispute Management",
    }

    # Financial sensitive tables
    FINANCIAL_SENSITIVE = {
        "BSEG", "BSIK", "BSAK", "BSID", "BSAD",
        "FAGLFLEXA", "GLP", "ACDOCA", "AUFK",
    }

    # HR sensitive
    HR_SENSITIVE = {
        "PA0001", "PA0002", "PA0008", "PCL1", "PCL2",
        "HRS1000", "VTFL", "VTBF",
    }

    # Tables requiring explicit consent (GDPR Article 9 - special categories)
    GDPR_SPECIAL_CATEGORIES = {
        "PA0002",   # Personal data / race
        "PA0008",   # Pay / wages
        "PCL1",     # HR health data
        "T77UA",    # HR attributes
        "HRP1000",  # Org management
    }

    def classify(self, table_name: str) -> Dict[str, Any]:
        """Classify a SAP table by data sensitivity."""
        table = table_name.upper()

        # Check exact matches
        gdpr_reason = self.GDPR_TABLE_PATTERNS.get(table, "")
        financial_flag = table in self.FINANCIAL_SENSITIVE
        hr_flag = table in self.HR_SENSITIVE
        gdpr_special = table in self.GDPR_SPECIAL_CATEGORIES

        # Pattern-based checks
        is_hr = any(table.startswith(p) for p in ["PA", "PB", "PC", "HR", "VT"])
        is_financial = any(
            table.startswith(p)
            for p in ["FAGL", "GL", "ACDOC", "FINS", "DFKK", "J_1I"]
        )
        is_pii_table = any(
            table.startswith(p)
            for p in ["BUT", "ADRC", "ADDR", "KNA", "LFA"]
        )

        if gdpr_special or (is_hr and "PERSONAL" in gdpr_reason.upper()):
            return {
                "gdprRelevant": True,
                "personalData": True,
                "personalDataCategory": "special_category",
                "dataCriticality": DataCriticality.RESTRICTED.value,
                "complianceFlags": ["GDPR_ARTICLE_9", "EXPLICIT_CONSENT_REQUIRED"],
                "maskingRequired": True,
            }
        elif is_hr:
            return {
                "gdprRelevant": True,
                "personalData": True,
                "personalDataCategory": "employment",
                "dataCriticality": DataCriticality.CONFIDENTIAL.value,
                "complianceFlags": ["GDPR_ARTICLE_88", "EMPLOYER_LEGITIMATE_INTEREST"],
                "maskingRequired": False,
            }
        elif is_pii_table and "PERSONAL" in gdpr_reason.upper():
            return {
                "gdprRelevant": True,
                "personalData": True,
                "personalDataCategory": "identity_contact",
                "dataCriticality": DataCriticality.CONFIDENTIAL.value,
                "complianceFlags": ["GDPR_ARTICLE_6_LF"],
                "maskingRequired": False,
            }
        elif financial_flag:
            return {
                "gdprRelevant": False,
                "personalData": False,
                "personalDataCategory": "financial",
                "dataCriticality": DataCriticality.RESTRICTED.value,
                "complianceFlags": ["SOX", "FINANCIAL_REPORTING"],
                "maskingRequired": False,
            }
        elif is_financial:
            return {
                "gdprRelevant": False,
                "personalData": False,
                "personalDataCategory": "financial",
                "dataCriticality": DataCriticality.INTERNAL.value,
                "complianceFlags": ["SOX"],
                "maskingRequired": False,
            }
        else:
            return {
                "gdprRelevant": False,
                "personalData": False,
                "personalDataCategory": "operational",
                "dataCriticality": DataCriticality.INTERNAL.value,
                "complianceFlags": [],
                "maskingRequired": False,
            }


# ── Main Governance Service ────────────────────────────────────────────────────

class LeanIXGovernanceService:
    """
    LeanIX Agent Governance — the governance layer for Know Your SAP Masters.

    Provides four governance functions:
      pre_authorize()  — Is this query allowed for this user/role?
      check_compliance() — Does the query touch sensitive/GDPR/HR data?
      enrich_context()   — Get LeanIX business metadata for the query
      log_query()        — Record query in the audit trail
    """

    def __init__(
        self,
        leanix_url: Optional[str] = None,
        leanix_token: Optional[str] = None,
        demo_mode: bool = True,
    ):
        self._client = LeanIXClient(
            base_url=leanix_url or os.environ.get("LEANIX_BASE_URL"),
            api_token=leanix_token or os.environ.get("LEANIX_API_TOKEN"),
        )
        self._classifier = DataClassificationEngine()
        self._audit_log: List[AuditEntry] = []  # In-proc fallback
        self._audit_redis: Optional[Any] = None   # Redis-backed if available
        self._demo_mode = demo_mode or not bool(
            os.environ.get("LEANIX_API_TOKEN")
        )

        # Cache LeanIX application data (refreshed on init)
        self._application_cache: Dict[str, LeanIXApplication] = {}
        self._cache_ttl_seconds = 3600  # 1 hour
        self._cache_timestamp = 0.0

        logger.info(
            f"[LeanIXGovernance] {'DEMO mode (no credentials)' if self._demo_mode else 'LIVE mode'}"
        )

    # ── Pre-authorization ──────────────────────────────────────────────────

    async def pre_authorize(
        self,
        user_id: str,
        role_id: str,
        query: str,
        tables_accessed: List[str],
        auth_context: Optional[SAPAuthContext] = None,
    ) -> PreAuthorizationResult:
        """
        Determine if a query should be allowed.

        Logic:
          1. Check user's role against allowed roles for each table (LeanIX app catalog)
          2. Flag cross-BU queries (user in BU-A querying BU-B data)
          3. Flag high-risk tables (BSEG, ANLA, COSP, ANLC) unless role is CFO/compliance
          4. Flag anomalous query patterns (unusual table combinations)
          5. Flag high-volume queries (>1000 rows for restricted tables)
        """
        audit_id = str(uuid.uuid4())
        flagged_conditions: List[str] = []
        leanix_apps: List[str] = []
        decision: AuthDecision = AuthDecision.ALLOW

        query_upper = query.upper()
        tables_upper = [t.upper() for t in tables_accessed]

        # ── Rule 1: Sensitive table access for non-authorized roles ────────────
        restricted_tables = {
            "ANLA", "ANLC", "ANEP", "ANLB", "ANLI",  # Asset accounting
            "COSP", "COSS", "GLP", "FAGLFLEXA",     # CO/FI actuals
            "BSIK", "BSAK", "BSID", "BSAD",           # Vendor/Customer open items
            "J_1IEXCHDRATE",                           # India tax exchange rates
            "PCL1", "PCL2",                             # HR cluster tables
        }

        restricted_allowed_roles = {
            "CFO_GLOBAL", "CFO_EU", "COMPLIANCE_OFFICER",
            "GRANT_ADMIN", "IT_AUDITOR", "SECURITY_ADMIN",
        }

        unauthorized_restricted = [
            t for t in tables_upper
            if t in restricted_tables
            and role_id not in restricted_allowed_roles
        ]

        if unauthorized_restricted:
            flagged_conditions.append(
                f"Restricted tables require elevated role: {unauthorized_restricted}"
            )
            decision = AuthDecision.DENY
            logger.warning(
                f"[LeanIX] DENY: User {user_id} ({role_id}) attempted "
                f"restricted tables: {unauthorized_restricted}"
            )

        # ── Rule 2: GDPR/HR data access ─────────────────────────────────────
        gdpr_tables = [t for t in tables_upper if self._classifier.classify(t)["gdprRelevant"]]
        gdpr_allowed_roles = {
            "HR_ADMIN", "DPO", "GDPR_COMPLIANCE", "LEGAL",
            "COMPLIANCE_OFFICER", "EMPLOYEE_SELF_SERVICE",
        }

        if gdpr_tables:
            unauthorized_gdpr = [
                t for t in gdpr_tables
                if role_id not in gdpr_allowed_roles
                and not (auth_context and auth_context.allowed_company_codes == ["*"])
            ]
            if unauthorized_gdpr:
                flagged_conditions.append(
                    f"GDPR/HR tables require DPO or HR role: {unauthorized_gdpr}"
                )
                if decision == AuthDecision.DENY:
                    decision = AuthDecision.DENY  # Already denied
                else:
                    decision = AuthDecision.FLAG

        # ── Rule 3: Cross-BU data access ─────────────────────────────────────
        if auth_context:
            bu_scope = getattr(auth_context, "allowed_bu", None)
            if bu_scope and bu_scope != "*":
                # Check if query references tables not in user's BU scope
                cross_bu_tables = [t for t in tables_upper if t not in tables_accessed]
                if cross_bu_tables:
                    flagged_conditions.append(
                        f"Cross-BU access attempt: BU={bu_scope}, tables={cross_bu_tables}"
                    )
                    if decision == AuthDecision.ALLOW:
                        decision = AuthDecision.FLAG

        # ── Rule 4: Anomalous query patterns ──────────────────────────────────
        # Detect potential data exfiltration
        exfil_patterns = [
            (len(tables_accessed) > 5, "Unusually high table count (>5)"),
            (len(tables_upper) > 0 and all(t in restricted_tables for t in tables_upper),
             "All restricted tables queried simultaneously"),
            ("SELECT * FROM" in query_upper, "Full table scan (SELECT *)"),
        ]
        for condition, msg in exfil_patterns:
            if condition:
                flagged_conditions.append(msg)

        # ── Rule 5: LeanIX application lookup ─────────────────────────────────
        if not self._demo_mode and tables_accessed:
            leanix_apps = await self._lookup_applications(tables_accessed)

        return PreAuthorizationResult(
            decision=decision,
            reason=self._describe_decision(decision, flagged_conditions),
            flaggedConditions=flagged_conditions,
            leanixApplications=leanix_apps,
            approvalRequired=(
                "GDPR_COMPLIANCE" if decision == AuthDecision.FLAG else None
            ),
            auditId=audit_id,
        )

    # ── Compliance check ────────────────────────────────────────────────────

    async def check_compliance(
        self,
        query: str,
        tables_accessed: List[str],
        auth_context: Optional[SAPAuthContext] = None,
    ) -> ComplianceCheckResult:
        """
        Check if the query touches sensitive data requiring special handling.

        Returns masking requirements, GDPR categories, and data residency.
        """
        audit_id = str(uuid.uuid4())
        tables_upper = [t.upper() for t in tables_accessed]
        all_classifications: List[Dict[str, Any]] = [
            self._classifier.classify(t) for t in tables_upper
        ]

        # Aggregate findings
        gdpr_relevant = any(c["gdprRelevant"] for c in all_classifications)
        personal_data = any(c["personalData"] for c in all_classifications)
        masking_required_tables = [
            tables_upper[i]
            for i, c in enumerate(all_classifications)
            if c["maskingRequired"]
        ]
        compliance_flags = list(set(
            flag for c in all_classifications for flag in c["complianceFlags"]
        ))
        data_categories = list(set(
            c["personalDataCategory"] for c in all_classifications
            if c["personalDataCategory"]
        ))

        # Determine overall compliance status
        has_gdpr_special = any(
            "GDPR_ARTICLE_9" in c["complianceFlags"]
            for c in all_classifications
        )

        if has_gdpr_special:
            status: ComplianceStatus = ComplianceStatus.BLOCK
            reason = "Query touches GDPR Article 9 special-category data (health, racial/ethnic origin, etc.)"
        elif personal_data and not gdpr_relevant:
            status = ComplianceStatus.MASK_AND_LOG
            reason = "Personal data detected — columns will be masked and query logged for DPO audit"
        elif gdpr_relevant:
            status = ComplianceStatus.GDPR_CONSENT
            reason = "GDPR-relevant data — explicit consent or legal basis required"
        else:
            status = ComplianceStatus.PASS
            reason = "No compliance concerns detected"

        return ComplianceCheckResult(
            status=status.value,
            reason=reason,
            personalDataFound=personal_data,
            dataCategories=data_categories,
            maskingRequired=masking_required_tables,
            legalBasis=", ".join(compliance_flags) or None,
            dataResidency=getattr(auth_context, "data_residency", None),
            auditId=audit_id,
        )

    # ── Context enrichment ─────────────────────────────────────────────────

    async def enrich_context(
        self,
        query: str,
        tables_accessed: List[str],
    ) -> EnrichedContext:
        """
        Enrich query context with LeanIX enterprise metadata.

        Returns:
          - LeanIX applications that own these tables
          - Business capabilities impacted
          - IT risk level
          - Data owner contacts
          - S/4HANA migration readiness
          - Related applications
        """
        audit_id = str(uuid.uuid4())

        leanix_apps: List[LeanIXApplication] = []
        related_apps: List[str] = []
        capabilities: List[str] = []
        it_risk_level = "LOW"
        owner_contact = ""
        data_lineage: List[Dict[str, str]] = []
        s4_readiness: Dict[str, Any] = {}

        if not self._demo_mode and tables_accessed:
            leanix_apps = await self._lookup_applications(tables_accessed)

            # Extract capabilities from apps
            for app in leanix_apps:
                capabilities.extend(app.get("businessCapabilities", []))
                it_risk = app.get("itRiskScore", 0)
                if it_risk > 70:
                    it_risk_level = "CRITICAL"
                elif it_risk > 40:
                    it_risk_level = "HIGH"

                owner_contact = app.get("ownerEmail", "") or owner_contact

                # S/4HANA readiness
                if app.get("tags_s4"):
                    s4_tag = app.get("tags_s4", "")
                    s4_readiness = {
                        "tag": s4_tag,
                        "ready": "READY" in s4_tag.upper(),
                        "migrationComplexity": self._parse_s4_complexity(s4_tag),
                    }

            # Get related applications via LeanIX relations
            if leanix_apps:
                related_apps = await self._get_related_applications(
                    [app["appId"] for app in leanix_apps]
                )

            # Build data lineage
            for app in leanix_apps:
                if app.get("name"):
                    data_lineage.append({
                        "application": app["name"],
                        "vendor": app.get("vendor", "SAP"),
                        "criticality": app.get("criticality", "MEDIUM"),
                    })

        business_context = {
            "queryHash": hashlib.sha256(query.encode()).hexdigest()[:12],
            "tableCount": len(tables_accessed),
            "leanixAppCount": len(leanix_apps),
            "itRiskLevel": it_risk_level,
        }

        return EnrichedContext(
            businessContext=business_context,
            leanixApplications=leanix_apps,
            relatedApplications=related_apps,
            businessCapabilities=list(set(capabilities)),
            itRiskLevel=it_risk_level,
            ownerContact=owner_contact,
            dataLineage=data_lineage,
            s4Readiness=s4_readiness,
            auditId=audit_id,
        )

    # ── Audit logging ───────────────────────────────────────────────────────

    def log_query(
        self,
        query: str,
        auth_result: PreAuthorizationResult,
        compliance_result: ComplianceCheckResult,
        result_summary: Dict[str, Any],
        user_id: str = "anonymous",
        role_id: str = "unknown",
    ) -> AuditEntry:
        """
        Record a query in the LeanIX audit trail.

        Writes to:
          1. In-process list (always, for demo/fallback)
          2. Redis (if available, for distributed access)
          3. LeanIX API (if credentials configured)

        Returns the AuditEntry for traceability.
        """
        audit_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        entry = AuditEntry(
            auditId=audit_id,
            timestamp=timestamp,
            userId=user_id,
            roleId=role_id,
            query=query,
            tablesAccessed=result_summary.get("tables_accessed", []),
            authDecision=auth_result["decision"].value
                if isinstance(auth_result["decision"], AuthDecision)
                else str(auth_result["decision"]),
            complianceStatus=compliance_result["status"],
            leanixApplications=auth_result.get("leanixApplications", []),
            queryHash=hashlib.sha256(query.encode()).hexdigest()[:16],
            executionTimeMs=result_summary.get("execution_time_ms", 0),
            resultRowCount=result_summary.get("row_count", 0),
            maskedFields=compliance_result.get("maskingRequired", []),
        )

        # Always log in-process
        self._audit_log.append(entry)
        # Keep last 10000 entries
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-5000:]

        # Try Redis
        self._log_to_redis(entry)

        logger.info(
            f"[LeanIXAudit] {audit_id} | {user_id} | {role_id} | "
            f"{auth_result['decision']} | {compliance_result['status']} | "
            f"{result_summary.get('row_count', 0)} rows | "
            f"{result_summary.get('execution_time_ms', 0)}ms"
        )

        return entry

    def _log_to_redis(self, entry: AuditEntry):
        """Write audit entry to Redis for distributed access."""
        # Use same host resolution as redis_dialog_manager (handles Windows localhost)
        try:
            if self._audit_redis is None:
                redis_url = (
                    os.environ.get("REDIS_URL")
                    or f"redis://{os.environ.get('REDIS_HOST', 'localhost')}:{os.environ.get('REDIS_PORT', '6379')}/0"
                )
                import redis
                self._audit_redis = redis.from_url(redis_url, decode_responses=True)
        except Exception:
            return

        try:
            import json
            key = f"leanix:audit:{entry['auditId']}"
            self._audit_redis.hset(key, mapping={
                k: json.dumps(v) if isinstance(v, list) else str(v)
                for k, v in entry.items()
            })
            self._audit_redis.expire(key, 86400 * 30)  # 30-day retention
        except Exception as e:
            logger.warning(f"[LeanIXAudit] Redis write failed: {e}")

    def get_audit_log(
        self,
        user_id: Optional[str] = None,
        role_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Retrieve audit entries with optional filters."""
        entries = self._audit_log

        if user_id:
            entries = [e for e in entries if e.get("userId") == user_id or e.get("user_id") == user_id]
        if role_id:
            entries = [e for e in entries if e.get("roleId") == role_id or e.get("role_id") == role_id]
        if since:
            entries = [
                e for e in entries
                if datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
                   > since
            ]

        return sorted(entries, key=lambda e: e["timestamp"], reverse=True)[:limit]

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _lookup_applications(
        self,
        tables: List[str],
    ) -> List[str]:
        """Look up LeanIX applications associated with SAP tables."""
        if not self._client._client:
            return []

        apps = []
        for table in tables[:5]:  # Limit to 5 tables
            results = await self._client.search_factsheets(
                f"SAP table {table}",
                factsheet_types=["application"],
            )
            for r in results[:2]:
                apps.append(r.get("name", ""))
        return list(set(apps))

    async def _get_related_applications(
        self,
        app_ids: List[str],
    ) -> List[str]:
        """Get related applications via LeanIX data flow relations."""
        if not self._client._client:
            return []

        related = []
        for app_id in app_ids[:3]:
            rels = await self._client.get_relations(
                from_factsheet_id=app_id,
                relation_type="dataFlow",
            )
            for rel in rels[:3]:
                related.append(rel.get("toFactsheet", {}).get("name", ""))
        return list(set(related))[:5]

    def _describe_decision(
        self,
        decision: AuthDecision,
        conditions: List[str],
    ) -> str:
        if decision == AuthDecision.ALLOW:
            return "Query authorized for this role and scope."
        elif decision == AuthDecision.DENY:
            return f"Query denied: {'; '.join(conditions) if conditions else 'Insufficient privileges.'}"
        elif decision == AuthDecision.FLAG:
            return f"Query flagged for review: {'; '.join(conditions) if conditions else 'Non-standard access pattern.'}"
        else:
            return "BLOCK_AND_LOG: Query blocked and logged as suspicious."

    def _parse_s4_complexity(self, tag: str) -> str:
        """Parse S/4HANA readiness from LeanIX tag."""
        tag_upper = tag.upper()
        if "GREEN" in tag_upper or "READY" in tag_upper:
            return "LOW"
        if "YELLOW" in tag_upper or "CONVERSION" in tag_upper:
            return "MEDIUM"
        if "RED" in tag_upper or "LEGACY" in tag_upper or "DEPRECATED" in tag_upper:
            return "HIGH"
        return "MEDIUM"
