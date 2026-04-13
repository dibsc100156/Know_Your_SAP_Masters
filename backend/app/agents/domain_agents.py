"""
domain_agents.py — Phase 4 Sub-Agent System
=============================================
Each DomainAgent is a focused specialist for one SAP module.
They receive a query fragment + auth context, run their own
Pillar 3+4+5 pipeline, and return results.

Agent lineup:
  BP_AGENT      — Business Partner     (LFA1, KNA1, BUT000, ADRC)
  MM_AGENT     — Material Master      (MARA, MARC, MARD, MBEW, MSKA)
  PUR_AGENT    — Purchasing           (EKKO, EKPO, EINA, EINE, EORD)
  SD_AGENT     — Sales & Distribution (VBAK, VBAP, LIKP, KNVL, KONV)
  QM_AGENT     — Quality Management   (QALS, QMEL, MAPL, QAMV)
  WM_AGENT    — Warehouse Management (LAGP, LQUA, VEKP, MLGT)
  CROSS_AGENT — Cross-Module         (multi-domain JOINs via Graph RAG)

Usage:
  from app.agents.domain_agents import (
      get_domain_agent, list_domain_agents, DomainAgent
  )
  agent = get_domain_agent("business_partner")
  result = agent.run(query="vendor with overdue invoices", auth_context=ctx)
"""

import time
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.agents.orchestrator_tools import call_tool, ToolResult, ToolStatus
from app.core.security import SAPAuthContext
from app.core.memory_layer import sap_memory
from app.agents.swarm.contracts import build_contract


# ---------------------------------------------------------------------------
# Domain Agent Registry
# ---------------------------------------------------------------------------
class DomainAgent(ABC):
    """Base class for all domain specialists."""

    name: str = "base"
    display_name: str = "Base Agent"
    domain: str = "base"

    # Tables this agent specializes in (ordered by importance)
    primary_tables: List[str] = []
    # Related domains this agent can collaborate with
    related_domains: List[str] = []

    # Keywords that indicate this agent should handle the query
    trigger_keywords: List[str] = []

    def __init__(self):
        self._call_count = 0

    @abstractmethod
    def can_handle(self, query: str, domain_hint: str = "auto") -> float:
        """
        Return confidence 0.0-1.0 that this agent handles the query.
        0.0 = cannot handle, 1.0 = perfect match.
        """

    def get_contract_class(self) -> type:
        """Return the typed output contract class for this agent."""
        from app.agents.swarm.contracts import AgentOutputContract
        return AgentOutputContract

    def run(
        self,
        query: str,
        auth_context: SAPAuthContext,
        tables_hint: Optional[List[str]] = None,
        verbose: bool = False,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run this agent's domain-specific pipeline.
        Returns dict with: {agent_name, tables_used, sql, data, answer, execution_time_ms}
        
        If run_id is provided, wraps output in a typed AgentOutputContract
        (via build_contract) for structured validation by the Synthesis Agent.
        """
        start = time.time()
        self._call_count += 1

        if verbose:
            print(f"\n[{self.name}] Starting — query: '{query[:60]}'")

        # Step 1: Schema lookup within this domain
        tables = tables_hint or self._resolve_tables(query)

        # Step 2: SQL pattern lookup
        sql = self._resolve_sql(query, tables, auth_context)

        # Step 3: AuthContext injection
        sql = self._inject_auth(sql, auth_context)

        # Step 4: Execute (mock)
        exec_result = self._execute(sql, auth_context)

        # Step 5: Mask sensitive fields
        data, masked = self._mask_results(exec_result, auth_context)

        elapsed = int((time.time() - start) * 1000)

        result = {
            "agent": self.name,
            "domain": self.domain,
            "query": query,
            "run_id": run_id or "",
            "tables_used": tables,
            "executed_sql": sql,
            "data": data,
            "masked_fields": masked,
            "answer": self._synthesize(data, query),
            "execution_time_ms": elapsed,
            "record_count": len(data),
        }

        # [Harness] Wrap in typed contract for structured validation
        if run_id:
            result = build_contract(self.name, result)
            # build_contract returns a Pydantic model — convert to dict for API compat
            if hasattr(result, "model_dump"):
                result = result.model_dump()

        # Log to memory layer
        sap_memory.log_query(
            query=query,
            role=auth_context.role_id,
            domain=self.domain,
            sql=sql,
            tables_used=tables,
            critique_score=0.8,  # domain agents self-score
            result="success" if data else "empty",
            execution_time_ms=elapsed,
        )

        if verbose:
            print(f"[{self.name}] Done — {len(data)} rows, {elapsed}ms")

        return result

    def _resolve_tables(self, query: str) -> List[str]:
        """Use schema lookup for this domain only."""
        result = call_tool("schema_lookup", {
            "query": query,
            "domain": self.domain,
            "n_results": 3,
        }, auth_context=None)
        if result.status == ToolStatus.SUCCESS:
            return result.data.get("tables_used", self.primary_tables[:2])
        return self.primary_tables[:2]

    def _resolve_sql(
        self,
        query: str,
        tables: List[str],
        auth_context: SAPAuthContext,
    ) -> str:
        """Use SQL pattern lookup for this domain."""
        result = call_tool("sql_pattern_lookup", {
            "query": query,
            "domain": self.domain,
            "n_results": 1,
        }, auth_context=auth_context)
        if result.status == ToolStatus.SUCCESS and result.data.get("patterns"):
            return result.data["patterns"][0]["sql"]
        # Fallback: simple SELECT from primary table
        return f"SELECT * FROM {tables[0]} WHERE MANDT = '100' LIMIT 100"

    def _inject_auth(self, sql: str, auth_context: SAPAuthContext) -> str:
        """Inject AuthContext filters into the SQL."""
        injected = sql.replace("{MANDT}", "'100'")

        # Company code filter
        if any(t in sql.upper() for t in ["LFB1", "BSIK", "BSAK"]):
            if auth_context.allowed_company_codes and "*" not in auth_context.allowed_company_codes:
                b = "', '".join(auth_context.allowed_company_codes)
                where = f"BUKRS IN ('{b}')"
                if "WHERE" in injected.upper():
                    injected += f"\n  AND {where}"
                else:
                    injected += f"\n WHERE {where}"

        # Plant filter
        if any(t in sql.upper() for t in ["MARC", "MARD", "MBEW"]):
            if auth_context.allowed_plants and "*" not in auth_context.allowed_plants:
                w = "', '".join(auth_context.allowed_plants)
                where = f"WERKS IN ('{w}')"
                if "WHERE" in injected.upper():
                    injected += f"\n  AND {where}"
                else:
                    injected += f"\n WHERE {where}"

        # Purchasing org filter
        if any(t in sql.upper() for t in ["EKKO", "EKPO"]):
            if auth_context.allowed_purchasing_orgs and "*" not in auth_context.allowed_purchasing_orgs:
                e = "', '".join(auth_context.allowed_purchasing_orgs)
                where = f"EKORG IN ('{e}')"
                if "WHERE" in injected.upper():
                    injected += f"\n  AND {where}"
                else:
                    injected += f"\n WHERE {where}"

        # Add LIMIT if missing
        if "LIMIT" not in injected.upper() and "TOP" not in injected.upper():
            injected = injected.rstrip().rstrip(";") + "\n LIMIT 100"

        return injected

    def _execute(self, sql: str, auth_context: SAPAuthContext) -> ToolResult:
        """Execute SQL against mock executor."""
        return call_tool("sql_execute", {
            "sql": sql,
            "dry_run": True,
            "max_rows": 100,
        }, auth_context=auth_context)

    def _mask_results(
        self,
        exec_result: ToolResult, auth_context: SAPAuthContext
    ) -> tuple[List[Dict], List[str]]:
        """Apply column masking based on AuthContext."""
        if exec_result.status != ToolStatus.SUCCESS or not exec_result.data.get("rows"):
            return [], []
        rows = exec_result.data["rows"]
        masked = []
        table = self.primary_tables[0] if self.primary_tables else ""
        for row in rows:
            for col, val in list(row.items()):
                if table and auth_context.is_column_masked(table, col):
                    row[col] = "***MASKED***"
                    masked.append(f"{col}")
        return rows, list(set(masked))

    def _synthesize(self, data: List[Dict], query: str) -> str:
        """Generate a natural language answer from results."""
        if not data:
            return f"No records found for your query in the {self.domain} domain."
        return f"Found {len(data)} record(s) in {self.domain}."

    @property
    def call_count(self) -> int:
        return self._call_count


# ---------------------------------------------------------------------------
# Concrete Domain Agents
# ---------------------------------------------------------------------------

class BPAgent(DomainAgent):
    """Business Partner — vendors (LFA1) and customers (KNA1)."""

    name = "bp_agent"
    display_name = "Business Partner Agent"
    domain = "business_partner"
    primary_tables = ["LFA1", "KNA1", "BUT000", "ADRC"]
    related_domains = ["purchasing", "sales_distribution"]

    trigger_keywords = [
        "vendor", "customer", "supplier", "business partner", "credit limit",
        "partner function", "account group", "address", "contact", "bank details",
        "tax number", "reconciliation account", "payment terms", "vendor master",
        "customer master", "blocked vendor", "blocked customer", "duns number",
        "n丧", "विकेendra", "לקוח", "fournisseur", "cliente"
    ]

    def can_handle(self, query: str, domain_hint: str = "auto") -> float:
        query_lower = query.lower()
        score = 0.0

        for kw in self.trigger_keywords:
            if kw.lower() in query_lower:
                score = max(score, 0.7)

        # Strong signals
        if any(w in query_lower for w in ["vendor master", "lfa1", "duns", "reconciliation"]):
            score = max(score, 0.9)
        if any(w in query_lower for w in ["customer master", "kna1", "credit limit"]):
            score = max(score, 0.9)

        # Domain hint bonus
        if domain_hint in ["business_partner", "bp", "vendor", "customer"]:
            score = max(score, 0.8)

        # Negative signals (likely other domains)
        if any(w in query_lower for w in ["purchase order", "sales order", "quality inspection",
                                           "warehouse", "inspection lot", "movement type"]):
            score = min(score, 0.3)

        return min(score, 1.0)
    def get_contract_class(self) -> type:
        """Return the typed output contract class for this agent."""
        from app.agents.swarm.contracts import BPAgentContract
        return BPAgentContract



class MMAgent(DomainAgent):
    """Material Master — materials, stocks, valuations."""

    name = "mm_agent"
    display_name = "Material Master Agent"
    domain = "material_master"
    primary_tables = ["MARA", "MARC", "MARD", "MBEW", "MSKA"]
    related_domains = ["purchasing", "warehouse_management", "quality_management"]

    trigger_keywords = [
        "material", "stock", "valuation", "price", "unit of measure", "material type",
        "industry sector", "material group", "mrp", "abc classification", "stock quantity",
        "warehouse stock", "unrestricted stock", "blocked stock", "quality stock",
        "valuation price", "moving price", "standard price", "material master",
        "bill of material", "routing", "work center", "inspection type", "spare part",
        "raw material", "semifinished", "traded goods", "packaging"
    ]

    def can_handle(self, query: str, domain_hint: str = "auto") -> float:
        query_lower = query.lower()
        score = 0.0

        for kw in self.trigger_keywords:
            if kw.lower() in query_lower:
                score = max(score, 0.7)

        if any(w in query_lower for w in ["mara", "marc", "mard", "mbew", "mska"]):
            score = max(score, 0.95)

        # Strong signals
        if any(w in query_lower for w in ["material master", "stock quantity", "valuation price"]):
            score = max(score, 0.9)

        if domain_hint in ["material_master", "mm", "material"]:
            score = max(score, 0.85)

        # Negative signals
        if any(w in query_lower for w in ["purchase order", "sales order", "invoice", "vendor"]):
            score = min(score, 0.3)

        return min(score, 1.0)
    def get_contract_class(self) -> type:
        """Return the typed output contract class for this agent."""
        from app.agents.swarm.contracts import MMAgentContract
        return MMAgentContract



class PURAgent(DomainAgent):
    """Purchasing — POs, info records, scheduling agreements."""

    name = "pur_agent"
    display_name = "Purchasing Agent"
    domain = "purchasing"
    primary_tables = ["EKKO", "EKPO", "EINA", "EINE", "EORD"]
    related_domains = ["business_partner", "material_master"]

    trigger_keywords = [
        "purchase order", "po", "rfq", "request for quote", "quotation",
        "info record", "source list", "vendor evaluation", "scheduling agreement",
        "outline agreement", "contract", "consignment", "release order",
        "goods receipt", "invoice verification", "厄", "تبويب مشتريات",
        "po history", "open po", "po value", "purchasing group", "purchasing org",
        "lifetime value", "contract release"
    ]

    def can_handle(self, query: str, domain_hint: str = "auto") -> float:
        query_lower = query.lower()
        score = 0.0

        for kw in self.trigger_keywords:
            if kw.lower() in query_lower:
                score = max(score, 0.7)

        if any(w in query_lower for w in ["ekko", "ekpo", "eina", "eine"]):
            score = max(score, 0.95)

        if any(w in query_lower for w in ["open po", "purchase order", "po value",
                                            "vendor evaluation", "contract"]):
            score = max(score, 0.9)

        if domain_hint in ["purchasing", "procurement", "pur"]:
            score = max(score, 0.85)

        # Negative signals
        if any(w in query_lower for w in ["sales order", "delivery", "billing"]):
            score = min(score, 0.3)

        return min(score, 1.0)
    def get_contract_class(self) -> type:
        """Return the typed output contract class for this agent."""
        from app.agents.swarm.contracts import PURAgentContract
        return PURAgentContract



class SDAgent(DomainAgent):
    """Sales & Distribution — orders, deliveries, billing."""

    name = "sd_agent"
    display_name = "Sales & Distribution Agent"
    domain = "sales_distribution"
    primary_tables = ["VBAK", "VBAP", "LIKP", "KNVL", "KONV"]
    related_domains = ["business_partner", "material_master"]

    trigger_keywords = [
        "sales order", "delivery", "billing", "invoice", "quotation",
        "sales deal", "pricing", "discount", "cash discount", "credit memo",
        "debit memo", "returns", "cancellations", "order reason",
        "sales district", "sales office", "sales group", "shipping condition",
        "incoterm", "partial delivery", "full delivery", "pick pack",
        "packing instruction", "_route", "ROUTE", "transit", "forwarder"
    ]

    def can_handle(self, query: str, domain_hint: str = "auto") -> float:
        query_lower = query.lower()
        score = 0.0

        for kw in self.trigger_keywords:
            if kw.lower() in query_lower:
                score = max(score, 0.7)

        if any(w in query_lower for w in ["vbak", "vbap", "likp", "vbrk"]):
            score = max(score, 0.95)

        if any(w in query_lower for w in ["sales order", "open delivery", "billing"]):
            score = max(score, 0.9)

        if domain_hint in ["sales_distribution", "sd", "sales"]:
            score = max(score, 0.85)

        # Negative signals
        if any(w in query_lower for w in ["purchase order", "goods receipt", "warehouse"]):
            score = min(score, 0.3)

        return min(score, 1.0)
    def get_contract_class(self) -> type:
        """Return the typed output contract class for this agent."""
        from app.agents.swarm.contracts import SDAgentContract
        return SDAgentContract



class QMAgent(DomainAgent):
    """Quality Management — inspection lots, notifications."""

    name = "qm_agent"
    display_name = "Quality Management Agent"
    domain = "quality_management"
    primary_tables = ["QALS", "QMEL", "MAPL", "QAMV", "QAVE"]
    related_domains = ["material_master", "purchasing"]

    trigger_keywords = [
        "quality", "inspection", "quality notification", "nonconformance",
        "defect", "usage decision", "ud code", "certificate", "qm lot",
        "qa", "qc", "quality audit", "reference defect", "customer complaint",
        "notification", "task list", "inspection characteristic", "sample drawing",
        "test report", "capability", "control chart", "quality score"
    ]

    def can_handle(self, query: str, domain_hint: str = "auto") -> float:
        query_lower = query.lower()
        score = 0.0

        for kw in self.trigger_keywords:
            if kw.lower() in query_lower:
                score = max(score, 0.7)

        if any(w in query_lower for w in ["qals", "qmel", "mapl"]):
            score = max(score, 0.95)

        if any(w in query_lower for w in ["inspection lot", "quality notification",
                                            "nonconformance", "usage decision"]):
            score = max(score, 0.9)

        if domain_hint in ["quality_management", "qm", "quality"]:
            score = max(score, 0.85)

        return min(score, 1.0)
    def get_contract_class(self) -> type:
        """Return the typed output contract class for this agent."""
        from app.agents.swarm.contracts import QMAgentContract
        return QMAgentContract



class WMAgent(DomainAgent):
    """Warehouse Management — storage bins, handling units, transfers."""

    name = "wm_agent"
    display_name = "Warehouse Management Agent"
    domain = "warehouse_management"
    primary_tables = ["LAGP", "LQUA", "VEKP", "MLGT"]
    related_domains = ["material_master"]

    trigger_keywords = [
        "warehouse", "storage", "bin", "storage location", "storage type",
        "handling unit", "transfer order", "physical inventory", "cycle counting",
        "stock removal", "stock placement", "quarantine", "fifo", "lifo",
        "storage bin", "warehouse stock", "stock in transit", "pick",
        "putaway", "internal transfer", "goods movement", "wm", "tcode"
    ]

    def can_handle(self, query: str, domain_hint: str = "auto") -> float:
        query_lower = query.lower()
        score = 0.0

        for kw in self.trigger_keywords:
            if kw.lower() in query_lower:
                score = max(score, 0.7)

        if any(w in query_lower for w in ["lagp", "lqua", "vekp", "mlgt"]):
            score = max(score, 0.95)

        if any(w in query_lower for w in ["storage bin", "handling unit",
                                            "transfer order", "physical inventory"]):
            score = max(score, 0.9)

        if domain_hint in ["warehouse_management", "wm", "warehouse"]:
            score = max(score, 0.85)

        return min(score, 1.0)
    def get_contract_class(self) -> type:
        """Return the typed output contract class for this agent."""
        from app.agents.swarm.contracts import WMAgentContract
        return WMAgentContract



class CROSSAgent(DomainAgent):
    """Cross-Module — handles multi-domain JOINs using Graph RAG."""

    name = "cross_agent"
    display_name = "Cross-Module Agent"
    domain = "cross_module"
    primary_tables = []  # Determined dynamically based on graph traversal
    related_domains = ["business_partner", "material_master", "purchasing",
                       "sales_distribution", "quality_management", "warehouse_management"]

    trigger_keywords = [
        "spend", "spend analysis", "vendor performance", "material traceability",
        "procurement analysis", "delivery performance", "quality vs delivery",
        "vendor quality", "customer lifetime value", "material cost rollup",
        "procure to pay", "order to cash", "procurement cycle", "supply chain",
        "multi-entity", "cross-company", "consolidation", "intercompany"
    ]

    def can_handle(self, query: str, domain_hint: str = "auto") -> float:
        query_lower = query.lower()
        score = 0.0

        # Cross-module keywords are strong signals
        cross_signals = [
            "spend", "vendor performance", "material traceability",
            "procure to pay", "order to cash", "material cost rollup",
            "procurement analysis", "delivery performance", "vendor quality",
            "multi-entity", "intercompany", "supply chain"
        ]
        for sig in cross_signals:
            if sig in query_lower:
                score = max(score, 0.85)

        # If multiple domain keywords appear, likely cross-module
        domain_signals = 0
        for agent_cls in [BPAgent, MMAgent, PURAgent, SDAgent, QMAgent, WMAgent]:
            agent = agent_cls()
            for kw in agent.trigger_keywords[:5]:
                if kw.lower() in query_lower:
                    domain_signals += 1
                    break

        if domain_signals >= 2:
            score = max(score, 0.8)

        # If domain_hint is "cross_module"
        if domain_hint in ["cross_module", "multi", "cross"]:
            score = max(score, 0.9)

        return min(score, 1.0)
    def get_contract_class(self) -> type:
        """Return the typed output contract class for this agent."""
        from app.agents.swarm.contracts import CROSSAgentContract
        return CROSSAgentContract


    def _resolve_tables(self, query: str) -> List[str]:
        """Use Graph RAG to dynamically discover cross-module tables."""
        result = call_tool("all_paths_explore", {
            "start_table": "LFA1",
            "end_table": "MARA",
            "max_depth": 5,
            "top_k": 3,
        })
        if result.status == ToolStatus.SUCCESS:
            return result.data.get("tables_involved", ["LFA1", "EKKO", "MARA"])
        return ["LFA1", "MARA"]


# ---------------------------------------------------------------------------
# Agent Registry
# ---------------------------------------------------------------------------
_AGENTS: Dict[str, DomainAgent] = {
    "bp_agent": BPAgent(),
    "mm_agent": MMAgent(),
    "pur_agent": PURAgent(),
    "sd_agent": SDAgent(),
    "qm_agent": QMAgent(),
    "wm_agent": WMAgent(),
    "cross_agent": CROSSAgent(),
}


def get_domain_agent(name: str) -> Optional[DomainAgent]:
    return _AGENTS.get(name)


def list_domain_agents() -> List[Dict[str, str]]:
    return [
        {"name": a.name, "display_name": a.display_name, "domain": a.domain}
        for a in _AGENTS.values()
    ]


def route_query(query: str, domain_hint: str = "auto", top_k: int = 2) -> List[tuple[DomainAgent, float]]:
    """
    Route a query to the top-k most appropriate domain agents.
    Returns list of (agent, confidence_score) sorted by confidence descending.
    Agents with score < 0.4 are excluded.
    """
    scored = []
    for agent in _AGENTS.values():
        score = agent.can_handle(query, domain_hint)
        if score >= 0.4:
            scored.append((agent, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:top_k]


def run_agents_parallel(
    queries: List[tuple[str, DomainAgent, SAPAuthContext]],
    max_workers: int = 4,
) -> List[Dict[str, Any]]:
    """
    Run multiple domain agents in parallel threads.
    queries: list of (query, agent, auth_context)
    Returns list of results in the same order.
    """
    results: Dict[int, Dict[str, Any]] = {}

    def run_single(idx: int, query: str, agent: DomainAgent,
                   auth_context: SAPAuthContext) -> tuple[int, Dict[str, Any]]:
        result = agent.run(query=query, auth_context=auth_context, verbose=False)
        return idx, result

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(run_single, i, q, a, ctx): i
            for i, (q, a, ctx) in enumerate(queries)
        }
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx] = result

    return [results[i] for i in range(len(queries))]
