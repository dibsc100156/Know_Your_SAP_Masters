"""
hierarchical_decomposer.py — Phase 18b: Hierarchical Task Decomposition
========================================================================
Key insight (from Google ADK Annie Wang — Coordinator Pattern):
  A router only decides which steps to SKIP. A true coordinator DECOMPOSES
  the problem space — it breaks "plan a full trip to San Francisco" into
  "food_agent + transport_agent as a TEAM", not just "which pipeline steps to run".

  Phase L5 Complexity Router skips steps. Phase 18b Hierarchical Decomposer
  CREATES sub-tasks and assigns them to domain agents.

What it does:
  1. Analyzes query intent → identifies required business dimensions
  2. Groups discovered tables by domain agent authority
  3. Identifies JOIN dependencies between table groups
  4. Assigns table groups to domain agents
  5. Outputs structured sub-task list with dependencies

Why it matters:
  Without decomposition: "vendor risk profile for company code 1010" →
    → returns tables LFA1, LFB1, BSEG (correct)
    → but each agent independently queries its own tables without understanding
      the cross-domain JOIN dependency (LFA1→BSEG via LIFNR needs company-code filter)

  With decomposition:
    → AgentGroup 1 (BP): LFA1 + LFB1 for vendor identity
    → AgentGroup 2 (FI): BSEG open items for this vendor+company code
    → JOIN: LFA1.LIFNR = BSEG.LIFNR AND BSEG.BUKRS = '1010'
    → Synthesis: merge on LIFNR, rank by open-item count

Usage:
  from app.core.hierarchical_decomposer import HierarchicalDecomposer, decompose_query
  plan = decompose_query(
      query="vendor risk profile for company code 1010",
      tables_discovered=["LFA1", "LFB1", "BSEG", "LFC1"],
      auth_context=auth_context,
  )
  print(plan.sub_tasks[0].agent_name)  # "pur_agent"
  print(plan.execution_order)           # ["bp_agent", "fi_agent"]
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ─── Enums ───────────────────────────────────────────────────────────────────

class TaskType(Enum):
    SINGLE = "single"           # One domain, one agent
    PARALLEL = "parallel"       # Multiple domains, independent agents (no JOIN between them)
    CROSS_MODULE = "cross_module"  # Multiple domains, must be JOINed
    NEGOTIATION = "negotiation"   # Conflicting values between agents
    ESCALATE = "escalate"         # Cannot decompose — needs human or swarm


class SubTaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class SubTask:
    """A single sub-task assigned to a domain agent."""
    task_id: str
    agent_name: str              # e.g. "pur_agent", "bp_agent", "fi_agent"
    agent_display: str           # e.g. "Purchasing Agent"
    tables: List[str]            # Tables this subtask covers
    sql_template: str            # Pre-built SQL template for this subtask
    intent_description: str     # Natural language description of what this subtask answers
    depends_on: List[str] = field(default_factory=list)  # task_ids this depends on
    status: SubTaskStatus = SubTaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None  # filled after execution
    join_key: Optional[str] = None  # e.g. "LIFNR" — the FK used to join with previous subtask


@dataclass
class DecompositionPlan:
    """Full plan produced by the hierarchical decomposer."""
    query: str
    task_type: TaskType          # SINGLE / PARALLEX / CROSS_MODULE / NEGOTIATION / ESCALATE
    sub_tasks: List[SubTask]     # Ordered list of sub-tasks
    execution_order: List[str]    # Agent names in execution order
    synthesis_instructions: str  # How to merge results from all sub_tasks
    cross_module_join: Optional[Dict[str, str]] = None  # {from_table.join_col: to_table.join_col}
    primary_agent: Optional[str] = None  # Which agent is the primary (returns the answer)
    exploration_candidates: List[str] = field(default_factory=list)  # tables found by exploration
    confidence: float = 0.0     # Confidence in this decomposition
    reasoning: str = ""          # Why this decomposition was chosen


# ─── Agent Domain Authority ──────────────────────────────────────────────────

AGENT_TABLE_AUTHORITY: Dict[str, List[str]] = {
    "pur_agent": ["EKKO", "EKPO", "EINA", "EINE", "EORD", "EKES", "ESKL", "ESKN"],
    "bp_agent": ["BUT000", "LFA1", "KNA1", "ADRC", "LFB1", "KNB1", "KNVV", "KNVV", "LFBK"],
    "mm_agent": ["MARA", "MARD", "MBEW", "MAKT", "MARC", "MLGN", "MLGT", "MSKA", "MSLB",
                 "MKOL", "MCHA", "MCH1", "MVKE", "MARM"],
    "sd_agent": ["VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "VBRP", "VBPA", "KONV"],
    "qm_agent": ["QALS", "QAVE", "QAMV", "MAPL", "QMEL", "QMIH", "QMSM"],
    "fi_agent": ["BKPF", "BSEG", "BSAK", "BSIK", "BSAD", "BSID", "FBL1N", "FBL5N",
                 "LFC1", "LFCY", "REGUH"],
    "wm_agent": ["LQUA", "LAGP", "MLGT", "LEIN", "LTAK", "LTBP"],
    "ps_agent": ["PRPS", "PROJ", "AFKO", "AFVC", "COSP", "COSS", "PRTE", "RHsys"],
    "pm_agent": ["IHPA", "VIQMEL", "QMEL", "IFLOT", "EQUI", "T001W"],
    "cs_agent": ["CRMD_ORDER", "CRMD_LINK", "BUT050", "JEST"],
    "tm_agent": ["VTTK", "VTTS", "VTFA", "TVRO", "SHP_OID", "TVL_PLT"],
    "re_agent": ["IFLOS", "IREL", "DFKK", "FKKV", "V_FKK_FC_INS"],
}


# ─── Domain Keywords ─────────────────────────────────────────────────────────

DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "pur_agent": ["purchase order", "po ", "purchasing", "rfq", "request for quote",
                   "procure", "info record", "source list", "contract", "outline agreement",
                   "request for quotation", "goods receipt", "gr ", "service entry"],
    "bp_agent": ["vendor master", "customer master", "business partner", "address",
                  "contact person", "bank detail", "account group", "partner", "bp "],
    "mm_agent": ["material master", "material", "stock", "valuation", "inventory",
                  "bom", "routing", "work center", "mrp", "planning", "material type"],
    "sd_agent": ["sales order", "delivery", "billing", "invoice", "sales", "pricing",
                  "customer", "distribution", "shipping", "credit memo", "return order"],
    "qm_agent": ["quality", "inspection", "nonconformance", "qm notification", "defect",
                  "quality notification", "quality issue", "qm ", "q-app", "quality plan"],
    "fi_agent": ["invoice", "payment", "journal entry", "accounting", "g/l", "gl account",
                  "post", "finance", "asset", "depreciation", "cost center", "profit center",
                  "fiscal year", "balance sheet", "p&l", "tax", "withholding"],
    "wm_agent": ["warehouse", "storage location", "storage type", "transfer order",
                  "warehouse management", "pick", "putaway", "quant", "handling unit"],
    "ps_agent": ["project", "wbs", "work breakdown", "network", "activity", "project system",
                 "budget", "commitment", "project cost", "billing rule"],
    "pm_agent": ["equipment", "functional location", "maintenance", "work order",
                  "maintenance plan", "task list", "breakdown", "preventive"],
    "cs_agent": ["service order", "service contract", "warranty", "complaint", "crm"],
    "tm_agent": ["transportation", "shipping", "freight", "route", "carrier", "load plan",
                  "transportation planning"],
    "re_agent": ["lease", "rental", "real estate", "property", "land", "building", "RE-FX"],
}


# ─── CROSS-MODULE JOIN MAPS ──────────────────────────────────────────────────

# Maps table pairs to their JOIN condition
CROSS_MODULE_JOINS: Dict[Tuple[str, str], Dict[str, str]] = {
    # (table_a, table_b) → {from_table: join_col_a, to_table: join_col_b, description}
    ("LFA1", "EKKO"): {"from_table": "LFA1", "join_col": "LIFNR", "to_table": "EKKO", "desc": "Vendor → PO"},
    ("LFA1", "BSEG"): {"from_table": "LFA1", "join_col": "LIFNR", "to_table": "BSEG", "desc": "Vendor → Line Items"},
    ("LFA1", "LFB1"): {"from_table": "LFA1", "join_col": "LIFNR", "to_table": "LFB1", "desc": "Vendor → Company Code"},
    ("MARA", "EKKO"): {"from_table": "MARA", "join_col": "MATNR", "to_table": "EKPO", "desc": "Material → PO Item"},
    ("MARA", "QALS"): {"from_table": "MARA", "join_col": "MATNR", "to_table": "QALS", "desc": "Material → Inspection"},
    ("MARA", "MARC"): {"from_table": "MARA", "join_col": "MATNR", "to_table": "MARC", "desc": "Material → Plant"},
    ("KNA1", "VBAK"): {"from_table": "KNA1", "join_col": "KUNNR", "to_table": "VBAK", "desc": "Customer → Sales Order"},
    ("KNA1", "BSID"): {"from_table": "KNA1", "join_col": "KUNNR", "to_table": "BSID", "desc": "Customer → Open Items"},
    ("EKKO", "LFA1"): {"from_table": "EKKO", "join_col": "LIFNR", "to_table": "LFA1", "desc": "PO → Vendor"},
    ("EKKO", "MARA"): {"from_table": "EKPO", "join_col": "MATNR", "to_table": "MARA", "desc": "PO Item → Material"},
    ("VBAK", "KNA1"): {"from_table": "VBAK", "join_col": "KUNNR", "to_table": "KNA1", "desc": "Sales Order → Customer"},
    ("BKPF", "BSEG"): {"from_table": "BKPF", "join_col": "BELNR", "to_table": "BSEG", "desc": "Header → Line Items"},
    ("PRPS", "COSP"): {"from_table": "PRPS", "join_col": "PSPNR", "to_table": "COSP", "desc": "WBS → Plan Costs"},
    ("PRPS", "COSS"): {"from_table": "PRPS", "join_col": "PSPNR", "to_table": "COSS", "desc": "WBS → Actual Costs"},
    ("MARA", "MBEW"): {"from_table": "MARA", "join_col": "MATNR", "to_table": "MBEW", "desc": "Material → Valuation"},
    ("LFA1", "LFC1"): {"from_table": "LFA1", "join_col": "LIFNR", "to_table": "LFC1", "desc": "Vendor → One-Time Account"},
}


# ─── Hierarchical Decomposer ──────────────────────────────────────────────────

class HierarchicalDecomposer:
    """
    Phase 18b — Hierarchical Task Decomposition.

    Transforms a flat list of discovered tables into a structured plan of
    sub-tasks assigned to domain agents, with JOIN dependencies between them.

    Key algorithm:
      1. Identify which domain each table belongs to (via AGENT_TABLE_AUTHORITY)
      2. Determine task type based on number of domains involved
      3. For CROSS_MODULE: find JOIN paths between table groups
      4. Build sub-tasks with dependencies
      5. Return execution order
    """

    def decompose(
        self,
        query: str,
        tables_discovered: List[str],
        auth_context: Any,           # SAPAuthContext
        exploration_tables: Optional[List[str]] = None,  # Phase 18 exploration candidates
        meta_path_used: bool = False,
        known_meta_path: Optional[str] = None,
    ) -> DecompositionPlan:
        """
        Main decomposition entry point.

        Args:
            query: natural language query
            tables_discovered: tables found by Schema RAG + exploration (Phase 18a)
            auth_context: SAPAuthContext — for denied_tables filtering
            exploration_tables: tables discovered by exploration engine
            meta_path_used: True if this query used a meta-path fast path
            known_meta_path: name of meta-path hit (if any)

        Returns:
            DecompositionPlan with sub_tasks, execution_order, join instructions
        """
        exploration_tables = exploration_tables or []
        query_lower = query.lower()
        all_tables = tables_discovered + [t for t in exploration_tables if t not in tables_discovered]

        # Filter denied tables
        denied = set(getattr(auth_context, "denied_tables", []) or [])
        all_tables = [t for t in all_tables if t not in denied]

        if not all_tables:
            return DecompositionPlan(
                query=query,
                task_type=TaskType.ESCALATE,
                sub_tasks=[],
                execution_order=[],
                synthesis_instructions="No tables accessible. Escalate to human.",
                confidence=0.0,
                reasoning="All candidate tables are denied for this role.",
            )

        # ── Step 1: Identify domains ─────────────────────────────────────────
        domain_groups: Dict[str, List[str]] = {}  # agent_name → [tables]
        unclassified: List[str] = []

        for table in all_tables:
            assigned = False
            for agent_name, authority_tables in AGENT_TABLE_AUTHORITY.items():
                if table in authority_tables:
                    if agent_name not in domain_groups:
                        domain_groups[agent_name] = []
                    domain_groups[agent_name].append(table)
                    assigned = True
                    break
            if not assigned:
                unclassified.append(table)

        # ── Step 2: Determine task type ──────────────────────────────────────
        num_domains = len(domain_groups)
        has_unclassified = bool(unclassified)
        has_comparison = any(kw in query_lower for kw in [
            "compare", "versus", "vs", "difference between", "vs.", "or"
        ])
        has_negotiation = any(kw in query_lower for kw in [
            "negotiate", "batna", "bargain", "leverage", "counter", "offer"
        ])

        if num_domains == 1 and not has_unclassified:
            task_type = TaskType.SINGLE
            reasoning = f"Single domain ({list(domain_groups.keys())[0]}) — no cross-module JOIN needed."
        elif num_domains >= 2 or has_unclassified:
            if has_comparison or has_negotiation:
                task_type = TaskType.NEGOTIATION
                reasoning = "Comparison or negotiation query — multiple agents with value conflict potential."
            else:
                task_type = TaskType.CROSS_MODULE
                reasoning = f"Cross-module query — {num_domains} domains require JOIN: {list(domain_groups.keys())}"
        elif has_negotiation:
            task_type = TaskType.NEGOTIATION
            reasoning = "Negotiation context detected."
        else:
            task_type = TaskType.PARALLEL
            reasoning = f"Parallel execution — {num_domains} independent domains."

        # ── Step 3: Build sub-tasks ───────────────────────────────────────────
        sub_tasks: List[SubTask] = []
        execution_order: List[str] = []
        task_counter = 1

        for agent_name, tables in sorted(domain_groups.items(), key=lambda x: x[0]):
            agent_display = self._agent_display_name(agent_name)
            intent = self._intent_for_agent(agent_name, query_lower)

            task_id = f"task_{task_counter}"
            join_key = self._find_join_key(tables, all_tables, domain_groups)

            sub_task = SubTask(
                task_id=task_id,
                agent_name=agent_name,
                agent_display=agent_display,
                tables=tables,
                sql_template=self._build_agent_sql_template(agent_name, tables, intent, auth_context),
                intent_description=intent,
                depends_on=[],
                status=SubTaskStatus.PENDING,
                join_key=join_key,
            )
            sub_tasks.append(sub_task)
            execution_order.append(agent_name)
            task_counter += 1

        # ── Step 4: Resolve dependencies for CROSS_MODULE ─────────────────────
        cross_module_join: Optional[Dict[str, str]] = None
        synthesis_instructions = ""

        if task_type == TaskType.CROSS_MODULE:
            join_map = self._resolve_join_order(sub_tasks, all_tables)
            cross_module_join = join_map
            synthesis_instructions = (
                f"MERGE {len(sub_tasks)} agent results on join keys: {join_map}. "
                f"Rank by cross-domain relevance. "
                f"Flag any conflicting field values (trigger Negotiation Protocol Phase 13b)."
            )
        elif task_type == TaskType.SINGLE:
            synthesis_instructions = (
                f"Return result directly from {execution_order[0]}. "
                f"No cross-domain synthesis needed."
            )
        elif task_type == TaskType.PARALLEL:
            synthesis_instructions = (
                f"Execute all {len(sub_tasks)} agents in parallel. "
                f"Aggregate results by entity key (LIFNR/KUNNR/MATNR). "
                f"Return unified result set."
            )
        elif task_type == TaskType.NEGOTIATION:
            synthesis_instructions = (
                f"EXECUTE Negotiation Protocol Phase 13b for conflicting values. "
                f"Use SOURCE_AUTHORITY ranking (EKKO=10, BSEG=10, LFA1=7). "
                f"Return resolved value + explanation."
            )
        else:
            synthesis_instructions = "Human review required — query cannot be auto-decomposed."

        # ── Step 5: Identify primary agent ────────────────────────────────────
        primary_agent = self._identify_primary_agent(query_lower, domain_groups, task_type)

        # ── Step 6: Confidence ───────────────────────────────────────────────
        confidence = self._compute_decomposition_confidence(
            task_type, sub_tasks, unclassified, meta_path_used, known_meta_path
        )

        return DecompositionPlan(
            query=query,
            task_type=task_type,
            sub_tasks=sub_tasks,
            execution_order=execution_order,
            cross_module_join=cross_module_join,
            synthesis_instructions=synthesis_instructions,
            primary_agent=primary_agent,
            exploration_candidates=exploration_tables,
            confidence=confidence,
            reasoning=reasoning,
        )

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _agent_display_name(agent_name: str) -> str:
        names = {
            "pur_agent": "Purchasing Agent",
            "bp_agent": "Business Partner Agent",
            "mm_agent": "Material Master Agent",
            "sd_agent": "Sales & Distribution Agent",
            "qm_agent": "Quality Management Agent",
            "fi_agent": "Finance Agent",
            "wm_agent": "Warehouse Management Agent",
            "ps_agent": "Project Systems Agent",
            "pm_agent": "Plant Maintenance Agent",
            "cs_agent": "Customer Service Agent",
            "tm_agent": "Transportation Agent",
            "re_agent": "Real Estate Agent",
        }
        return names.get(agent_name, agent_name.replace("_", " ").title())

    @staticmethod
    def _intent_for_agent(agent_name: str, query_lower: str) -> str:
        intents = {
            "pur_agent": "Purchase orders, contracts, info records, and vendor purchasing data",
            "bp_agent": "Business partner master data, addresses, and bank details",
            "mm_agent": "Material master, stock quantities, valuation, and BOM data",
            "sd_agent": "Sales orders, deliveries, billing, and customer pricing",
            "qm_agent": "Quality inspections, notifications, and defect records",
            "fi_agent": "Accounting documents, line items, payments, and financial balances",
            "wm_agent": "Warehouse quants, storage locations, and handling units",
            "ps_agent": "Project WBS elements, networks, and cost planning",
            "pm_agent": "Equipment, functional locations, and maintenance orders",
            "cs_agent": "Service orders, contracts, and warranty records",
            "tm_agent": "Transportation planning, routes, and freight management",
            "re_agent": "Real estate lease, rental, and property management",
        }
        return intents.get(agent_name, f"Data from {agent_name}")

    @staticmethod
    def _find_join_key(
        tables: List[str],
        all_tables: List[str],
        domain_groups: Dict[str, List[str]],
    ) -> Optional[str]:
        """Find the FK that connects this agent's tables to another domain's tables."""
        join_keys_map: Dict[str, str] = {
            "LIFNR": "LIFNR",   # vendor key
            "KUNNR": "KUNNR",   # customer key
            "MATNR": "MATNR",   # material key
            "VBELN": "VBELN",   # document number
            "BELNR": "BELNR",   # accounting document
            "PSPNR": "PSPNR",   # WBS element
            "WERKS": "WERKS",   # plant
            "BUKRS": "BUKRS",   # company code
        }
        # If this agent's tables contain LIFNR and query has cross-module, return LIFNR
        if "LIFNR" in join_keys_map and any(t in tables for t in ["LFA1", "EKKO", "BSEG"]):
            return "LIFNR"
        if "KUNNR" in join_keys_map and any(t in tables for t in ["KNA1", "VBAK", "BSID"]):
            return "KUNNR"
        if "MATNR" in join_keys_map and any(t in tables for t in ["MARA", "EKPO", "QALS"]):
            return "MATNR"
        return None

    @staticmethod
    def _build_agent_sql_template(
        agent_name: str,
        tables: List[str],
        intent: str,
        auth_context: Any,
    ) -> str:
        """Build a pre-formed SQL template for the agent to execute."""
        primary_table = tables[0] if tables else "LFA1"
        # Use MANDT filter from auth_context
        mandt = getattr(auth_context, "mandt", "'100'") if auth_context else "'100'"
        return (
            f"SELECT * FROM {primary_table} "
            f"WHERE MANDT = {mandt} "
            f"AND EXISTS (SELECT 1 FROM DUMMY)  -- Agent: {intent}"
        ).strip()

    @staticmethod
    def _resolve_join_order(
        sub_tasks: List[SubTask],
        all_tables: List[str],
    ) -> Dict[str, str]:
        """
        Resolve JOIN order for cross-module tasks.
        Returns {table.join_col: next_table.join_col} chain.
        """
        join_chain: Dict[str, str] = {}

        # Priority join order: BP → PUR → MM → FI → SD
        domain_order = ["bp_agent", "pur_agent", "mm_agent", "fi_agent", "sd_agent"]
        ordered_tasks = sorted(
            sub_tasks,
            key=lambda t: domain_order.index(t.agent_name) if t.agent_name in domain_order else 99
        )

        # Build chain of joins
        for i in range(len(ordered_tasks) - 1):
            curr = ordered_tasks[i]
            nxt = ordered_tasks[i + 1]
            if curr.join_key and nxt.join_key:
                join_chain[curr.join_key] = curr.tables[0] if curr.tables else ""
        return join_chain

    @staticmethod
    def _identify_primary_agent(
        query_lower: str,
        domain_groups: Dict[str, List[str]],
        task_type: TaskType,
    ) -> Optional[str]:
        """Identify which agent is the primary (provides the main answer)."""
        # Priority for primary: FI > BP > PUR > MM
        priority_order = ["fi_agent", "bp_agent", "pur_agent", "mm_agent", "sd_agent"]
        if task_type == TaskType.SINGLE:
            return list(domain_groups.keys())[0]
        for agent in priority_order:
            if agent in domain_groups:
                return agent
        return list(domain_groups.keys())[0] if domain_groups else None

    @staticmethod
    def _compute_decomposition_confidence(
        task_type: TaskType,
        sub_tasks: List[SubTask],
        unclassified: List[str],
        meta_path_used: bool,
        known_meta_path: Optional[str],
    ) -> float:
        """Compute confidence in this decomposition (0.0–1.0)."""
        base = 0.9 if meta_path_used else 0.75

        # Penalize unclassified tables
        if unclassified:
            base -= len(unclassified) * 0.05

        # Penalize too many domains (complexity)
        if len(sub_tasks) > 4:
            base -= 0.1

        # Negotiation queries are harder
        if task_type == TaskType.NEGOTIATION:
            base -= 0.15

        # Cross-module confidence
        if task_type == TaskType.CROSS_MODULE:
            base -= 0.05 * (len(sub_tasks) - 2)  # more domains = more risk

        return max(min(base, 1.0), 0.1)


# ─── Convenience function ─────────────────────────────────────────────────────
_decomposer = HierarchicalDecomposer()


def decompose_query(
    query: str,
    tables_discovered: List[str],
    auth_context: Any,
    exploration_tables: Optional[List[str]] = None,
    meta_path_used: bool = False,
    known_meta_path: Optional[str] = None,
) -> DecompositionPlan:
    """Convenience wrapper — delegates to HierarchicalDecomposer singleton."""
    return _decomposer.decompose(
        query=query,
        tables_discovered=tables_discovered,
        auth_context=auth_context,
        exploration_tables=exploration_tables,
        meta_path_used=meta_path_used,
        known_meta_path=known_meta_path,
    )
