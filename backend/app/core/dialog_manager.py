"""
dialog_manager.py — Phase 6 Multi-Turn Dialog Manager
====================================================
Tracks conversation state across turns, detects ambiguity,
and asks one clarifying question before execution.

Supports:
  - Conversation sessions (persisted in memory/sap_sessions/dialog_sessions/)
  - Clarification types: entity, time_range, metric, scope, domain
  - Context carry-over between turns
  - Automatic disambiguation before execution

Usage:
  from app.core.dialog_manager import DialogManager, ConversationState
  dm = DialogManager()
  state = dm.start_session(user_id="sanjeev", role="AP_CLERK")
  result = dm.handle_turn(state, query="show vendor performance")
  if result["needs_clarification"]:
      print(result["question"])  # agent asks user
      # ... wait for user response
      result = dm.handle_turn(state, query="all vendors", clarification_reply=True)
"""

import json
import time
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Literal
from pathlib import Path
from threading import Lock

# ---------------------------------------------------------------------------
# Conversation State & Types
# ---------------------------------------------------------------------------

class ClarificationType(Enum):
    ENTITY = "entity"          # Which vendor/material/customer?
    TIME_RANGE = "time"       # Which time period?
    METRIC = "metric"         # What measure/metric?
    SCOPE = "scope"           # All or specific subset?
    DOMAIN = "domain"         # Which domain did you mean?
    CONFIRM = "confirm"      # Did you mean X?


@dataclass
class Clarification:
    """A pending question to ask the user."""
    clarification_type: ClarificationType
    question: str
    options: List[str] = field(default_factory=list)  # e.g. ["All vendors", "Specific vendor"]
    default: str = "all"
    context_key: str = ""      # key to store the answer under


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""
    turn_number: int
    user_query: str
    agent_response: str = ""
    clarification_requested: Optional[Clarification] = None
    entities_extracted: Dict[str, Any] = field(default_factory=dict)
    domain: str = "auto"
    executed: bool = False
    result: Optional[Dict] = None
    timestamp: str = ""


@dataclass
class ConversationState:
    """Full state for a conversation session."""
    session_id: str
    user_id: str
    role: str
    turns: List[ConversationTurn] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    # Carried-forward context from previous turns
    last_domain: str = "auto"
    last_tables: List[str] = field(default_factory=list)
    last_entities: Dict[str, Any] = field(default_factory=dict)
    pending_clarification: Optional[Clarification] = None
    created_at: str = ""
    updated_at: str = ""


# ---------------------------------------------------------------------------
# Ambiguity Detectors
# ---------------------------------------------------------------------------

class AmbiguityDetector:
    """
    Analyzes a query and returns a Clarification if the query is ambiguous.
    Returns None if the query is clear enough to execute.
    """

    # Patterns that indicate ambiguity
    SCOPE_ALL_SIGNALS = [
        "all", "every", "any", "each", "total", "overall",
        "global", "complete", "full", "summary",
    ]

    TIME_AMBIGUITY = [
        r"\ball\b", r"\bevery\b", r"\boverall\b", r"\btotal\b",
        r"\bsummary\b", r"\bfull\b",
    ]

    ENTITY_AMBIGUITY = [
        "vendor", "customer", "material", "product", "item",
        "transaction", "order", "invoice",
    ]

    METRIC_AMBIGUITY = [
        "performance", "status", "overview", "summary", "report",
        "analysis", "breakdown", "detail",
    ]

    def __init__(self):
        self._turn_count = 0

    def analyze(
        self,
        query: str,
        domain_hint: str,
        prior_context: Dict[str, Any],
        turn_count: int,
    ) -> Optional[Clarification]:
        """
        Return a Clarification if needed, else None.
        Checks in order of priority: scope > entity > time > metric > domain.
        """
        q_lower = query.lower()
        self._turn_count = turn_count

        # 1. SCOPE: "all" vs "specific" ambiguity
        scope_clarification = self._check_scope(q_lower, prior_context)
        if scope_clarification:
            return scope_clarification

        # 2. ENTITY: missing entity specificity
        entity_clarification = self._check_entity(q_lower, domain_hint, prior_context)
        if entity_clarification:
            return entity_clarification

        # 3. TIME: missing time range when query is broad
        time_clarification = self._check_time_range(q_lower, prior_context)
        if time_clarification:
            return time_clarification

        # 4. METRIC: what exactly to show
        metric_clarification = self._check_metric(q_lower, domain_hint, prior_context)
        if metric_clarification:
            return metric_clarification

        # 5. DOMAIN: query spans multiple domains without being explicitly cross-module
        domain_clarification = self._check_domain_clarity(q_lower, prior_context)
        if domain_clarification:
            return domain_clarification

        return None

    def _check_scope(self, q_lower: str, context: Dict) -> Optional[Clarification]:
        """Detect if scope is ambiguous."""
        # If query uses "all/every/total" for a broad entity, it might be intentional
        # but if it's the SECOND broad query after a clarification, let it pass
        if context.get("_scope_confirmed"):
            return None

        has_all_signal = any(s in q_lower for s in self.SCOPE_ALL_SIGNALS)
        has_specific_id = bool(re.search(r'\b(?:vendor|material|customer)\s+#?\w{3,}\b', q_lower))

        if has_all_signal and not has_specific_id:
            # Broad query — ask about scope
            if "vendor" in q_lower or "supplier" in q_lower:
                return Clarification(
                    clarification_type=ClarificationType.SCOPE,
                    question="Should this cover all vendors, or a specific one?",
                    options=["All vendors", "Specific vendor (provide ID)", "Top N by spend"],
                    default="all vendors",
                    context_key="vendor_scope",
                )
            elif "customer" in q_lower:
                return Clarification(
                    clarification_type=ClarificationType.SCOPE,
                    question="Should this cover all customers, or a specific one?",
                    options=["All customers", "Specific customer (provide ID)"],
                    default="all customers",
                    context_key="customer_scope",
                )
            elif "material" in q_lower or "product" in q_lower:
                return Clarification(
                    clarification_type=ClarificationType.SCOPE,
                    question="Which material(s) — all, a specific one, or a group?",
                    options=["All materials", "Specific material (provide ID)", "Material group"],
                    default="all materials",
                    context_key="material_scope",
                )
        return None

    def _check_entity(self, q_lower: str, domain_hint: str, context: Dict) -> Optional[Clarification]:
        """Detect if a key entity is missing."""
        if context.get("_entity_confirmed"):
            return None

        # If the domain is clear but no entity ID provided
        if domain_hint == "business_partner":
            has_vendor = bool(re.search(r'\b(?:LIFNR|vendor|supplier)\s*[:#]?\s*\w+', q_lower, re.I))
            has_customer = bool(re.search(r'\b(?:KUNNR|customer)\s*[:#]?\s*\w+', q_lower, re.I))
            if "vendor" in q_lower and not has_vendor and "customer" not in q_lower:
                return Clarification(
                    clarification_type=ClarificationType.ENTITY,
                    question="Which vendor? Please provide a vendor code or name.",
                    options=["I don't have a specific vendor — show all", "Provide vendor code"],
                    default="all vendors",
                    context_key="vendor_id",
                )
        elif domain_hint == "material_master":
            has_material = bool(re.search(r'\b(?:MATNR|material)\s*[:#]?\s*\w+', q_lower, re.I))
            if "material" in q_lower and not has_material:
                return Clarification(
                    clarification_type=ClarificationType.ENTITY,
                    question="Which material? Provide a material number or name.",
                    options=["Show all materials", "Provide material code"],
                    default="all materials",
                    context_key="material_id",
                )
        elif domain_hint == "purchasing":
            has_po = bool(re.search(r'\b(?:EBELN|PO|purchase order)\s*[:#]?\s*\w+', q_lower, re.I))
            if "purchase order" in q_lower and not has_po:
                return Clarification(
                    clarification_type=ClarificationType.ENTITY,
                    question="Which purchase order? Provide a PO number, or say 'all open POs'.",
                    options=["All open POs", "Specific PO (provide number)"],
                    default="all open POs",
                    context_key="po_number",
                )
        return None

    def _check_time_range(self, q_lower: str, context: Dict) -> Optional[Clarification]:
        """Detect if a time range is missing for a summary query."""
        if context.get("_time_confirmed"):
            return None

        has_date = bool(re.search(r'\b(?:\d{4}|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|Q[1-4]|FY\d{2})\b', q_lower, re.I))
        has_all_signal = any(s in q_lower for s in self.SCOPE_ALL_SIGNALS)

        if has_all_signal and not has_date:
            # Summary query without time range — ask for clarification
            return Clarification(
                clarification_type=ClarificationType.TIME_RANGE,
                question="Which time period?",
                options=["This month", "This quarter", "This year", "Last 12 months", "All time"],
                default="this month",
                context_key="time_range",
            )
        return None

    def _check_metric(self, q_lower: str, domain_hint: str, context: Dict) -> Optional[Clarification]:
        """Detect if 'what metric' is ambiguous."""
        if context.get("_metric_confirmed"):
            return None

        metric_signals = ["performance", "overview", "summary", "report", "status", "analysis"]
        if any(m in q_lower for m in metric_signals):
            # Map domain + metric to specific options
            if domain_hint == "business_partner":
                return Clarification(
                    clarification_type=ClarificationType.METRIC,
                    question="What aspect of vendor performance?",
                    options=["Payment history", "Open invoices", "Spend analysis", "Quality ratings"],
                    default="payment history",
                    context_key="vendor_metric",
                )
            elif domain_hint == "purchasing":
                return Clarification(
                    clarification_type=ClarificationType.METRIC,
                    question="What purchasing metric?",
                    options=["Open POs", "PO history", "Spend by vendor", "Delivery performance"],
                    default="open POs",
                    context_key="pur_metric",
                )
        return None

    def _check_domain_clarity(self, q_lower: str, context: Dict) -> Optional[Clarification]:
        """Detect if query spans domains without being explicitly cross-module."""
        if context.get("_domain_confirmed"):
            return None

        # Count domain signals in the query
        domain_signals = 0
        domains_mentioned = []

        bp_signals = ["vendor", "customer", "supplier", "business partner", "account"]
        mm_signals = ["material", "stock", "valuation", "inventory", "product"]
        pur_signals = ["purchase order", "PO", "procurement", "rfq", "info record"]
        sd_signals = ["sales order", "delivery", "invoice", "billing", "SO"]
        qm_signals = ["quality", "inspection", "defect", "nonconformance", "certificate"]

        if any(s in q_lower for s in bp_signals):
            domain_signals += 1; domains_mentioned.append("Business Partner")
        if any(s in q_lower for s in mm_signals):
            domain_signals += 1; domains_mentioned.append("Material")
        if any(s in q_lower for s in pur_signals):
            domain_signals += 1; domains_mentioned.append("Purchasing")
        if any(s in q_lower for s in sd_signals):
            domain_signals += 1; domains_mentioned.append("Sales")
        if any(s in q_lower for s in qm_signals):
            domain_signals += 1; domains_mentioned.append("Quality")

        if domain_signals >= 3 and " and " in q_lower:
            # Multi-domain query — check if it looks like a cross-module analysis or confusion
            return Clarification(
                clarification_type=ClarificationType.DOMAIN,
                question=f"Your query spans: {', '.join(domains_mentioned)}. Is this a cross-module analysis, or did you mean one specific area?",
                options=["Cross-module analysis (I'll combine all)", "Just " + domains_mentioned[0], "Just " + domains_mentioned[1] if len(domains_mentioned) > 1 else None],
                default="cross-module",
                context_key="domain_scope",
            )
        return None


# ---------------------------------------------------------------------------
# Dialog Manager
# ---------------------------------------------------------------------------

class DialogManager:
    """
    Orchestrates multi-turn dialog with clarification loops.
    Wraps the supervisor/orchestrator and can interrupt execution to ask questions.
    """

    SESSION_DIR = Path(__file__).parent.parent.parent / "memory" / "sap_sessions" / "dialog_sessions"
    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def __init__(self):
        self._sessions: Dict[str, ConversationState] = {}
        self._lock = Lock()
        self._detector = AmbiguityDetector()
        self._max_turns = 20

    def start_session(
        self,
        user_id: str,
        role: str,
        session_id: Optional[str] = None,
    ) -> ConversationState:
        """Start a new dialog session."""
        from datetime import datetime, timezone
        sid = session_id or f"{user_id}_{int(time.time())}"
        state = ConversationState(
            session_id=sid,
            user_id=user_id,
            role=role,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._sessions[sid] = state
        return state

    def resume_session(self, session_id: str) -> Optional[ConversationState]:
        """Resume an existing session from disk."""
        session_file = self.SESSION_DIR / f"{session_id}.json"
        if session_file.exists():
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                state = self._deserialize_state(data)
                with self._lock:
                    self._sessions[session_id] = state
                return state
            except Exception:
                return None
        return None

    def handle_turn(
        self,
        state: ConversationState,
        query: str,
        orchestrator_fn=None,  # Pass in run_agent_loop or supervisor.execute
        clarification_reply: bool = False,
    ) -> Dict[str, Any]:
        """
        Main entry point for a dialog turn.

        If `clarification_reply=True`, the query is treated as an answer
        to the pending clarification.

        Returns:
            {
                "executed": bool,
                "needs_clarification": bool,
                "question": str,
                "options": list,       # if needs_clarification
                "result": dict,        # if executed
                "turn_number": int,
            }
        """
        from datetime import datetime, timezone

        turn_num = len(state.turns) + 1
        if turn_num > self._max_turns:
            return {
                "executed": False,
                "needs_clarification": False,
                "result": None,
                "error": "Max turns exceeded. Please start a new session.",
                "turn_number": turn_num,
            }

        turn = ConversationTurn(
            turn_number=turn_num,
            user_query=query,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # ------------------------------------------------------------------
        # If this is a clarification reply — apply it and re-execute
        # ------------------------------------------------------------------
        if clarification_reply and state.pending_clarification:
            answer_lower = query.lower()
            clarification = state.pending_clarification

            # Parse the user's answer
            resolved_value = self._resolve_clarification_answer(answer_lower, clarification)

            # Store in context
            state.context[clarification.context_key] = resolved_value
            state.context[f"_{clarification.clarification_type.value}_confirmed"] = True

            # Mark clarification as answered
            turn.clarification_requested = clarification
            clarification_answered = clarification
            state.pending_clarification = None

            # Modify the previous query to include the answer
            # Re-run with the clarified context
            if orchestrator_fn:
                result = self._execute_with_context(
                    state=state,
                    query=query,  # original broad query
                    orchestrator_fn=orchestrator_fn,
                )
                turn.result = result
                turn.executed = True
                turn.agent_response = result.get("answer", "")
                state.last_domain = result.get("domain", state.last_domain)
                state.last_tables = result.get("tables_used", state.last_tables)
            else:
                turn.result = {"clarification_applied": clarification.context_key, "value": resolved_value}
                turn.executed = True

            state.turns.append(turn)
            state.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_session(state)

            return {
                "executed": turn.executed,
                "needs_clarification": False,
                "question": None,
                "options": None,
                "result": turn.result,
                "turn_number": turn_num,
                "clarification_applied": clarification.context_key,
            }

        # ------------------------------------------------------------------
        # Normal turn — detect ambiguity first
        # ------------------------------------------------------------------
        # Update domain hint from prior context
        domain_hint = state.last_domain if state.last_domain != "auto" else self._infer_domain(query)

        clarification = self._detector.analyze(
            query=query,
            domain_hint=domain_hint,
            prior_context=state.context,
            turn_count=turn_num,
        )

        if clarification:
            # Store pending clarification and ask the user
            state.pending_clarification = clarification
            turn.clarification_requested = clarification
            state.turns.append(turn)
            state.updated_at = datetime.now(timezone.utc).isoformat()
            self._save_session(state)

            return {
                "executed": False,
                "needs_clarification": True,
                "clarification_type": clarification.clarification_type.value,
                "question": clarification.question,
                "options": clarification.options,
                "default": clarification.default,
                "context_key": clarification.context_key,
                "result": None,
                "turn_number": turn_num,
            }

        # ------------------------------------------------------------------
        # No ambiguity — execute
        # ------------------------------------------------------------------
        if orchestrator_fn:
            result = self._execute_with_context(state=state, query=query, orchestrator_fn=orchestrator_fn)
            turn.executed = True
            turn.result = result
            turn.agent_response = result.get("answer", "")
            state.last_domain = result.get("domain", state.last_domain)
            state.last_tables = result.get("tables_used", state.last_tables)
        else:
            turn.executed = False
            turn.agent_response = "(No orchestrator function provided — set orchestrator_fn to execute)"

        state.turns.append(turn)
        state.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_session(state)

        return {
            "executed": turn.executed,
            "needs_clarification": False,
            "question": None,
            "options": None,
            "result": turn.result,
            "turn_number": turn_num,
        }

    def _execute_with_context(
        self,
        state: ConversationState,
        query: str,
        orchestrator_fn,
    ) -> Dict[str, Any]:
        """Execute query with dialog context injected."""
        from app.core.security import security_mesh

        auth = security_mesh.get_context(state.role)

        # Inject context into query for better routing
        enriched_query = self._enrich_query_with_context(query, state)

        try:
            result = orchestrator_fn(
                query=enriched_query,
                auth_context=auth,
                domain=state.last_domain,
                verbose=False,
            )
            return result
        except Exception as e:
            return {"answer": f"Execution error: {e}", "error": str(e), "tables_used": []}

    def _enrich_query_with_context(self, query: str, state: ConversationState) -> str:
        """Add context from prior turns to the query."""
        # If context has time_range, inject it
        time_range = state.context.get("time_range", "")
        if time_range and time_range not in query.lower():
            query = f"{query} — period: {time_range}"

        # If context has entity scope, inject it
        scope = state.context.get("vendor_scope") or state.context.get("customer_scope")
        if scope and scope not in query.lower() and "all" in scope.lower():
            query = f"{query} (all {scope})"

        return query

    def _resolve_clarification_answer(
        self,
        answer_lower: str,
        clarification: Clarification,
    ) -> str:
        """Parse the user's answer to a clarification question."""
        # Check options for exact/partial match
        for option in clarification.options:
            if option.lower() in answer_lower or answer_lower in option.lower():
                return option

        # Default keyword detection
        if any(w in answer_lower for w in ["all", "every", "total", "overall"]):
            return "all"
        elif any(w in answer_lower for w in ["specific", "particular", "give", "provide", "id"]):
            return "specific"
        elif any(w in answer_lower for w in ["month", "quarter", "year", "jan", "feb", "mar"]):
            # Extract time period
            for opt in clarification.options:
                if any(w in answer_lower for w in opt.lower().split()):
                    return opt
            return clarification.default
        else:
            return clarification.default

    def _infer_domain(self, query: str) -> str:
        """Infer domain from query keywords."""
        q_lower = query.lower()
        if any(w in q_lower for w in ["vendor", "customer", "supplier", "business partner"]):
            return "business_partner"
        if any(w in q_lower for w in ["material", "stock", "valuation", "inventory"]):
            return "material_master"
        if any(w in q_lower for w in ["purchase order", "PO", "procurement", "rfq"]):
            return "purchasing"
        if any(w in q_lower for w in ["sales order", "delivery", "invoice", "SO"]):
            return "sales_distribution"
        if any(w in q_lower for w in ["quality", "inspection", "defect", "qm"]):
            return "quality_management"
        return "auto"

    def end_session(self, session_id: str) -> bool:
        """End and clean up a session."""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
            return True

    # -------------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------------
    def _save_session(self, state: ConversationState):
        try:
            self.SESSION_DIR.mkdir(parents=True, exist_ok=True)
            session_file = self.SESSION_DIR / f"{state.session_id}.json"
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(self._serialize_state(state), f, indent=2, ensure_ascii=False)
        except Exception:
            pass  # Non-critical

    def _serialize_state(self, state: ConversationState) -> Dict:
        return {
            "session_id": state.session_id,
            "user_id": state.user_id,
            "role": state.role,
            "context": state.context,
            "last_domain": state.last_domain,
            "last_tables": state.last_tables,
            "last_entities": state.last_entities,
            "pending_clarification": {
                "clarification_type": state.pending_clarification.clarification_type.value if state.pending_clarification else None,
                "question": state.pending_clarification.question if state.pending_clarification else None,
                "options": state.pending_clarification.options if state.pending_clarification else None,
                "context_key": state.pending_clarification.context_key if state.pending_clarification else None,
            } if state.pending_clarification else None,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "turn_count": len(state.turns),
        }

    def _deserialize_state(self, data: Dict) -> ConversationState:
        pending = None
        if data.get("pending_clarification"):
            p = data["pending_clarification"]
            if p:
                pending = Clarification(
                    clarification_type=ClarificationType(p["clarification_type"]),
                    question=p["question"] or "",
                    options=p.get("options", []),
                    context_key=p.get("context_key", ""),
                )
        return ConversationState(
            session_id=data["session_id"],
            user_id=data["user_id"],
            role=data["role"],
            context=data.get("context", {}),
            last_domain=data.get("last_domain", "auto"),
            last_tables=data.get("last_tables", []),
            last_entities=data.get("last_entities", {}),
            pending_clarification=pending,
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )
