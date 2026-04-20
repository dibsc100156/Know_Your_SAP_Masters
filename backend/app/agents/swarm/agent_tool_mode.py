"""
agent_tool_mode.py — Phase 19: Agent-as-Tool Dynamic Override
===============================================================
When the Security Sentinel issues an ENFORCING verdict OR CIBA has a pending
request, sub-agents are treated as stateless tools — no autonomous revision
loops, no LLM synthesis, no self-critique.

Key insight (Annie Wang, ADK V3 — Agent-as-Tool Pattern):
  "Full system control retained by primary agent. When you want to bypass
   a sub-agent's autonomy, treat it as a tool."

Trigger conditions (any one activates tool mode):
  1. sentinel verdict.threat_detected AND verdict.recommended_action in ("tighten", "block")
  2. SentinelProfile.tightness_level >= 3
  3. CIBA store has a PENDING request for this session

What changes in tool mode:
  - DomainAgent.run() → skips _synthesize() — returns raw data only
  - No self-critique / revision loops in planner or synthesis agent
  - Swarm uses direct pass-through from sub-agents
  - CIBA queries blocked until approval received
  - Logging includes [TOOL_MODE] prefix for audit trail

Usage:
    from app.agents.swarm.agent_tool_mode import AgentToolMode

    mode = AgentToolMode()
    if mode.should_engage(sentinel_verdict, session_id):
        result = mode.execute_as_tool(agent, query, auth_context, tables_hint)
"""

from __future__ import annotations

import time
import logging
from typing import Optional, Any, Dict, List, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from app.core.security_sentinel import SecuritySentinel, ThreatVerdict
    from app.core.ciba_approval_store import CIBAApprovalStore
    from app.agents.domain_agents import DomainAgent

logger = logging.getLogger(__name__)


# ============================================================================
# AgentToolMode — Execution Mode Controller
# ============================================================================

@dataclass
class ToolModeConfig:
    """
    Configuration for Agent-as-Tool mode.
    
    These thresholds determine when agents are treated as stateless tools.
    """
    # Sentinel triggers
    tighten_action_triggers_tool_mode: bool = True   # "tighten" verdict → tool mode
    block_action_triggers_tool_mode: bool = True     # "block" verdict → tool mode
    tightness_threshold: int = 3                     # tightness_level >= 3 → tool mode
    
    # CIBA triggers
    ciba_pending_blocks_tool_mode: bool = True       # CIBA pending request → tool mode
    ciba_approved_allows_tool_mode: bool = True     # Previously approved query → skip CIBA block
    
    # Behavior flags
    skip_synthesis: bool = True          # Don't run LLM synthesis in domain agents
    skip_self_critique: bool = True      # Skip critique/revision loops
    skip_negotiation: bool = True       # Skip inter-agent negotiation
    max_tool_mode_depth: int = 2         # Max recursive tool-mode calls (safety cap)
    tool_mode_ttl_seconds: int = 300     # Auto-expire tool mode after 5 minutes


@dataclass
class ToolModeSession:
    """
    Per-session tool mode state.
    Tracks whether tool mode is active, for how long, and why it was activated.
    """
    session_id: str
    active: bool = False
    reason: str = ""                    # "sentinel_tighten" | "sentinel_block" | "ciba_pending" | "tightness_3"
    sentinel_verdict: Optional[Any] = None
    activated_at: float = 0.0
    expires_at: float = 0.0
    tool_call_depth: int = 0            # Current nested tool calls
    suppress_burst: List[str] = field(default_factory=list)  # agent names suppressed
    
    def remaining_ttl(self) -> float:
        return max(0.0, self.expires_at - time.time())


class AgentToolMode:
    """
    Agent-as-Tool Dynamic Override Controller.
    
    Singleton per orchestrator session. Evaluates trigger conditions and
    enforces tool-mode constraints on agent execution.
    
    Usage:
        mode = AgentToolMode()
        
        # At the start of each query:
        mode.evaluate_triggers(query, auth_context, sentinel_verdict, session_id)
        
        # Before calling a sub-agent:
        if mode.should_engage(sentinel_verdict, session_id):
            result = mode.execute_as_tool(agent, query, auth_context, tables_hint)
        else:
            result = agent.run(query, auth_context, tables_hint)
    """

    def __init__(
        self,
        config: Optional[ToolModeConfig] = None,
        sentinel: Optional[Any] = None,
        ciba_store: Optional[Any] = None,
    ):
        self.config = config or ToolModeConfig()
        
        # Lazy-load dependencies
        self._sentinel = sentinel
        self._ciba_store = ciba_store
        self._ciba_store_class: Optional[type] = None  # for lazy init
        
        # Per-session state (session_id → ToolModeSession)
        self._sessions: Dict[str, ToolModeSession] = {}
    
    # ── Dependency Accessors ─────────────────────────────────────────────────

    @property
    def sentinel(self) -> Any:
        if self._sentinel is None:
            try:
                from app.core.security_sentinel import get_sentinel
                self._sentinel = get_sentinel()
            except Exception as e:
                logger.warning(f"[AgentToolMode] Could not load sentinel: {e}")
        return self._sentinel

    @property
    def ciba_store(self) -> Any:
        if self._ciba_store is None:
            try:
                from app.core.ciba_approval_store import get_ciba_store
                self._ciba_store = get_ciba_store()
            except Exception as e:
                logger.warning(f"[AgentToolMode] Could not load CIBA store: {e}")
        return self._ciba_store

    # ── Trigger Evaluation ──────────────────────────────────────────────────

    def should_engage(
        self,
        sentinel_verdict: Optional[Any] = None,
        session_id: Optional[str] = None,
        session_tightness: int = 0,
    ) -> bool:
        """
        Returns True if Agent-as-Tool mode should be engaged for this session.
        
        Checks (in order):
          1. Sentinel verdict: "tighten" or "block" action
          2. Sentinel tightness_level >= config.tightness_threshold
          3. CIBA store: has a PENDING request for this session
          4. Session already in tool mode (from activate())
        """
        # Check active session override
        if session_id:
            sess = self._sessions.get(session_id)
            if sess and sess.active:
                if sess.remaining_ttl() <= 0:
                    # TTL expired — deactivate
                    sess.active = False
                    logger.info(f"[AgentToolMode] Session {session_id[:8]} tool mode TTL expired")
                else:
                    return True

        # Check Sentinel verdict
        if sentinel_verdict is not None:
            action = getattr(sentinel_verdict, "recommended_action", "allow")
            if action in ("tighten", "block"):
                if self.config.tighten_action_triggers_tool_mode:
                    return True

        # Check Sentinel tightness level
        if session_tightness >= self.config.tightness_threshold:
            return True

        return False

    def activate(
        self,
        session_id: str,
        reason: str,
        sentinel_verdict: Optional[Any] = None,
    ) -> ToolModeSession:
        """
        Explicitly activate tool mode for a session.
        Called by the orchestrator when Sentinel/CIBA trigger is confirmed.
        """
        sess = self._sessions.setdefault(session_id, ToolModeSession(session_id=session_id))
        sess.active = True
        sess.reason = reason
        sess.sentinel_verdict = sentinel_verdict
        sess.activated_at = time.time()
        sess.expires_at = time.time() + self.config.tool_mode_ttl_seconds
        
        logger.warning(
            f"[AgentToolMode] ACTIVATED for session {session_id[:8]} — reason={reason} "
            f"(TTL={self.config.tool_mode_ttl_seconds}s)"
        )
        return sess

    def deactivate(self, session_id: str) -> None:
        """Explicitly deactivate tool mode for a session."""
        if session_id in self._sessions:
            self._sessions[session_id].active = False
            logger.info(f"[AgentToolMode] DEACTIVATED for session {session_id[:8]}")

    # ── Sentinel Integration ─────────────────────────────────────────────────

    def evaluate_sentinel(
        self,
        verdict: Any,
        profile: Any,
        session_id: str,
    ) -> Optional[ToolModeSession]:
        """
        Evaluate a Sentinel ThreatVerdict and SessionThreatProfile.
        Returns activated ToolModeSession if triggered, else None.
        
        Call this in the orchestrator after sentinel.evaluate().
        """
        if not verdict or not verdict.threat_detected:
            return None

        reason = None
        action = getattr(verdict, "recommended_action", "allow")

        if action == "block" and self.config.block_action_triggers_tool_mode:
            reason = "sentinel_block"
        elif action == "tighten" and self.config.tighten_action_triggers_tool_mode:
            reason = "sentinel_tighten"
        
        if reason:
            return self.activate(session_id, reason, verdict)

        # Also check tightness level
        if profile is not None:
            tightness = getattr(profile, "tightness_level", 0)
            if tightness >= self.config.tightness_threshold:
                return self.activate(session_id, "tightness_3", verdict)

        return None

    # ── CIBA Integration ─────────────────────────────────────────────────────

    def evaluate_ciba(
        self,
        session_id: str,
        query: str,
        role_id: str,
    ) -> Optional[ToolModeSession]:
        """
        Evaluate CIBA store for pending requests.
        Returns activated ToolModeSession if a pending request blocks execution, else None.
        
        Call this in the orchestrator before allowing query execution.
        """
        if not self.config.ciba_pending_blocks_tool_mode:
            return None

        try:
            store = self.ciba_store
            if store is None:
                return None

            # Check if query was already approved (auto-pass)
            if self.config.ciba_approved_allows_tool_mode:
                if store.is_query_approved(session_id, query):
                    logger.info(f"[AgentToolMode] CIBA: query already approved for session {session_id[:8]} — proceeding")
                    return None

            # Check if query was denied (hard reject)
            if store.is_query_denied(session_id, query):
                logger.warning(f"[AgentToolMode] CIBA: query DENIED for session {session_id[:8]} — blocking")
                # Don't activate tool mode — just block the query
                return None

            # Check for pending requests
            pending = store.get_pending_for_session(session_id)
            if pending:
                # Activate tool mode — agent runs as tool until CIBA resolved
                reason = f"ciba_pending:{pending[0].request_id}"
                sess = self.activate(session_id, reason)
                logger.warning(
                    f"[AgentToolMode] CIBA: pending request {pending[0].request_id} for "
                    f"session {session_id[:8]} — tool mode engaged"
                )
                return sess

        except Exception as e:
            logger.warning(f"[AgentToolMode] CIBA evaluation error (non-fatal): {e}")

        return None

    # ── Execute as Tool ──────────────────────────────────────────────────────

    def execute_as_tool(
        self,
        agent: "DomainAgent",
        query: str,
        auth_context: Any,
        tables_hint: Optional[List[str]] = None,
        verbose: bool = False,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a domain agent in Agent-as-Tool mode.
        
        In tool mode:
          - No LLM synthesis — returns raw masked data
          - No self-critique loops
          - No negotiation with other agents
          - Short-circuit execution path
          - All outputs tagged with tool_mode=True
        
        This is the key Phase 19 primitive — it is the "bypass autonomy" operation.
        """
        if verbose:
            logger.debug(f"\n[TOOL_MODE] {agent.name} executing as stateless tool")

        start = time.time()

        # ── Step 1: Table resolution (no agent "thinking") ─────────────────
        tables = tables_hint or []
        if not tables:
            try:
                tables = agent._resolve_tables(query) if hasattr(agent, "_resolve_tables") else []
            except Exception as e:
                logger.warning(f"[TOOL_MODE] {agent.name} table resolution error: {e}")
                tables = []

        # ── Step 2: SQL pattern lookup (direct pass-through) ────────────────
        sql = None
        try:
            if hasattr(agent, "_resolve_sql"):
                sql = agent._resolve_sql(query, tables, auth_context)
        except Exception as e:
            logger.warning(f"[TOOL_MODE] {agent.name} SQL resolution error: {e}")

        if not sql:
            return {
                "agent": agent.name,
                "tool_mode": True,
                "status": "no_sql",
                "error": "Could not resolve SQL in tool mode",
                "execution_time_ms": int((time.time() - start) * 1000),
            }

        # ── Step 3: AuthContext injection ───────────────────────────────────
        try:
            if hasattr(agent, "_inject_auth"):
                sql = agent._inject_auth(sql, auth_context)
        except Exception as e:
            logger.warning(f"[TOOL_MODE] {agent.name} auth injection error: {e}")

        # ── Step 4: Execute (mock or real) ─────────────────────────────────
        exec_result = []
        try:
            if hasattr(agent, "_execute"):
                exec_result = agent._execute(sql, auth_context) or []
        except Exception as e:
            logger.warning(f"[TOOL_MODE] {agent.name} execution error: {e}")

        # ── Step 5: Mask sensitive fields (always do this) ─────────────────
        data, masked = [], []
        try:
            if hasattr(agent, "_mask_results"):
                data, masked = agent._mask_results(exec_result, auth_context)
            else:
                data = exec_result
        except Exception as e:
            logger.warning(f"[TOOL_MODE] {agent.name} masking error: {e}")
            data = exec_result

        # ── Step 6: SKIP synthesis — direct return in tool mode ────────────
        # This is the key difference from normal agent.run():
        # No agent._synthesize() call — no LLM involved

        elapsed = int((time.time() - start) * 1000)

        result = {
            "agent": agent.name,
            "domain": getattr(agent, "domain", ""),
            "query": query,
            "run_id": run_id or "",
            "tables_used": tables,
            "executed_sql": sql,
            "data": data,
            "masked_fields": masked,
            # NO "answer" field in tool mode — raw data only
            "tool_mode": True,
            "tool_mode_reason": self._sessions.get(
                getattr(auth_context, "session_id", "unknown"), ToolModeSession(session_id="")
            ).reason if hasattr(auth_context, "session_id") else "unknown",
            "execution_time_ms": elapsed,
            "record_count": len(data),
            "status": "success" if data else "empty",
        }

        if verbose:
            logger.debug(
                f"[TOOL_MODE] {agent.name} done — {len(data)} rows, {elapsed}ms "
                f"(no synthesis, no critique)"
            )

        return result

    # ── Planner Integration Hooks ────────────────────────────────────────────

    def wrap_agent_execution(
        self,
        agent: "DomainAgent",
        query: str,
        auth_context: Any,
        tables_hint: Optional[List[str]] = None,
        verbose: bool = False,
        run_id: Optional[str] = None,
        sentinel_verdict: Optional[Any] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Main entry point for the planner/dispatcher.
        
        Wraps agent execution — if tool mode is active, calls execute_as_tool().
        Otherwise calls agent.run() normally.
        
        This is the single place where tool mode intercepts agent execution
        in the swarm pipeline.
        """
        session_id = session_id or getattr(auth_context, "session_id", "unknown")

        # Check if tool mode should be engaged for this call
        engage = self.should_engage(
            sentinel_verdict=sentinel_verdict,
            session_id=session_id,
            session_tightness=0,
        )

        if engage:
            # Enforce tool mode depth cap
            sess = self._sessions.get(session_id)
            if sess and sess.tool_call_depth >= self.config.max_tool_mode_depth:
                logger.warning(
                    f"[AgentToolMode] Max tool mode depth ({self.config.max_tool_mode_depth}) "
                    f"reached for session {session_id[:8]} — blocking recursive call"
                )
                return {
                    "agent": getattr(agent, "name", "unknown"),
                    "tool_mode": True,
                    "status": "depth_limit_reached",
                    "error": "Max recursive tool mode calls reached",
                }
            
            if sess:
                sess.tool_call_depth += 1

            result = self.execute_as_tool(
                agent=agent,
                query=query,
                auth_context=auth_context,
                tables_hint=tables_hint,
                verbose=verbose,
                run_id=run_id,
            )
            
            if sess:
                sess.tool_call_depth -= 1
                
            return result
        else:
            # Normal agent.run() — full autonomy
            return agent.run(
                query=query,
                auth_context=auth_context,
                tables_hint=tables_hint,
                verbose=verbose,
                run_id=run_id,
            )

    # ── Synthesis Agent Hook ────────────────────────────────────────────────

    def synthesize_in_tool_mode(
        self,
        agent_results: List[Dict[str, Any]],
        query: str,
        auth_context: Any,
    ) -> Dict[str, Any]:
        """
        Called by SynthesisAgent when tool mode is active.
        
        In tool mode, synthesis is a dumb merge — no LLM involved.
        Just deduplicate and return raw combined data.
        """
        merged_data: List[Dict[str, Any]] = []
        seen_keys: set = set()

        for res in agent_results:
            is_tool = res.get("tool_mode", False)
            if not is_tool:
                logger.warning(
                    f"[AgentToolMode] Synthesis received non-tool-mode result "
                    f"for tool-mode session — audit flag"
                )

            for record in res.get("data", []):
                # Deduplicate by key entity
                key_fields = ["LIFNR", "KUNNR", "MATNR", "EBELN", "VBELN", "QALS"]
                parts = []
                for f in key_fields:
                    if f in record:
                        parts.append(f"{f}={record[f]}")
                key = "|".join(parts) if parts else str(abs(hash(str(sorted(record.items())))))
                
                if key not in seen_keys:
                    merged_data.append(record)
                    seen_keys.add(key)

        return {
            "data": merged_data,
            "record_count": len(merged_data),
            "tool_mode": True,
            "synthesis_method": "dedup_only",
            "agents_contributed": [r.get("agent", "?") for r in agent_results],
        }

    # ── Session Management ───────────────────────────────────────────────────

    def get_session_state(self, session_id: str) -> Optional[ToolModeSession]:
        """Return tool mode state for a session."""
        return self._sessions.get(session_id)

    def clear_session(self, session_id: str) -> None:
        """Clear tool mode state for a session (called on session end/timeout)."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"[AgentToolMode] Session state cleared: {session_id[:8]}")


# ============================================================================
# Module-level singleton (orchestrator injects sentinel + CIBA at init)
# ============================================================================

_agent_tool_mode: Optional[AgentToolMode] = None


def get_agent_tool_mode() -> AgentToolMode:
    global _agent_tool_mode
    if _agent_tool_mode is None:
        _agent_tool_mode = AgentToolMode()
    return _agent_tool_mode


def set_agent_tool_mode(mode: AgentToolMode) -> None:
    """Inject a configured AgentToolMode instance (called by orchestrator init)."""
    global _agent_tool_mode
    _agent_tool_mode = mode
    logger.info("[AgentToolMode] Module singleton updated via set_agent_tool_mode()")
