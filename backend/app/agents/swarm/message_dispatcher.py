"""
message_dispatcher.py — Message Bus Integration Layer
====================================================
Wires the Inter-Agent Message Bus and Negotiation Protocol into the
domain agent execution layer.

When enabled (use_message_bus=True):
  - Agents can QUERY each other during execution
  - Conflicts trigger Negotiation Protocol automatically
  - All inter-agent communication is traced in trajectory_log

Usage:
    from app.agents.swarm.message_dispatcher import MessageDispatcher

    dispatcher = MessageDispatcher()
    
    # Wrap an agent call
    result = dispatcher.execute_agent(
        agent_name="pur_agent",
        query="vendor open POs",
        auth_context=auth_context,
        use_bus=True,
        run_id=run_id,
    )
"""

from __future__ import annotations

import time
import uuid
import logging
from typing import Dict, Any, List, Optional, Set
from threading import Thread

from app.core.message_bus import message_bus, AgentMessage, MessageType, Priority
from app.core.negotiation_protocol import (
    NegotiationEngine, NegotiationPhase, ResolutionStrategy,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Known Domain Agents
# ---------------------------------------------------------------------------

AGENT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "pur_agent": {
        "display_name": "Purchasing Agent",
        "primary_tables": ["EKKO", "EKPO", "EINA", "EINE", "LFA1", "LFB1"],
        "can_answer": ["purchase orders", "contracts", "vendor info", "info records"],
        "subscribes_to": ["query", "vendor", "po", "purchasing", "rfq"],
        "authority_for": ["EKKO", "EKPO", "EINA", "EINE", "LFA1"],
    },
    "bp_agent": {
        "display_name": "Business Partner Agent",
        "primary_tables": ["BUT000", "LFA1", "KNA1", "ADRC", "LFB1"],
        "can_answer": ["vendor master", "customer master", "address", "BP relationships"],
        "subscribes_to": ["query", "vendor", "customer", "address", "business partner"],
        "authority_for": ["BUT000", "LFA1", "KNA1", "ADRC"],
    },
    "mm_agent": {
        "display_name": "Material Master Agent",
        "primary_tables": ["MARA", "MARD", "MBEW", "MAKT", "MARC"],
        "can_answer": ["material", "stock", "valuation", "bom", "routing"],
        "subscribes_to": ["material", "stock", "valuation", "bom", "routing"],
        "authority_for": ["MARA", "MARD", "MBEW", "MAKT", "MARC"],
    },
    "sd_agent": {
        "display_name": "Sales & Distribution Agent",
        "primary_tables": ["VBAK", "VBAP", "LIKP", "VBRK"],
        "can_answer": ["sales order", "delivery", "billing", "customer"],
        "subscribes_to": ["sales", "order", "delivery", "billing"],
        "authority_for": ["VBAK", "VBAP", "LIKP", "VBRK"],
    },
    "qm_agent": {
        "display_name": "Quality Management Agent",
        "primary_tables": ["QALS", "QAVE", "QAMV", "MAPL"],
        "can_answer": ["inspection", "quality", "qm notification"],
        "subscribes_to": ["quality", "inspection", "qm", "quality notification"],
        "authority_for": ["QALS", "QAVE", "QAMV", "MAPL"],
    },
    "wm_agent": {
        "display_name": "Warehouse Management Agent",
        "primary_tables": ["LQUA", "LAGP", "MLGT", "VEKP"],
        "can_answer": ["warehouse", "storage bin", "transfer", "stock"],
        "subscribes_to": ["warehouse", "storage", "transfer", "wm"],
        "authority_for": ["LQUA", "LAGP", "MLGT", "VEKP"],
    },
    "cross_agent": {
        "display_name": "Cross-Module Agent",
        "primary_tables": [],  # Uses all tables
        "can_answer": ["cross module", "joins", "complex", "budget", "project"],
        "subscribes_to": ["cross", "join", "complex", "budget", "project", "financial"],
        "authority_for": [],  # Mediator, lowest authority
    },
}


# ---------------------------------------------------------------------------
# Message Dispatcher
# ---------------------------------------------------------------------------

class MessageDispatcher:
    """
    Manages inter-agent communication and negotiation for the swarm.

    responsibilities:
      1. ROUTE — Forward cross-domain queries to the correct specialist agent
      2. NEGOTIATE — Detect conflicts and trigger the Negotiation Protocol
      3. INJECT — Add inbox polling and message responses into agent execution
      4. TRACE — Record all inter-agent messages in trajectory_log
    """

    def __init__(self, bus=None, negotiation_engine=None):
        self._bus = bus or message_bus
        self._neg = negotiation_engine or NegotiationEngine(bus=self._bus)
        self._running_threads: Dict[str, Thread] = {}
        self._agent_executors: Dict[str, callable] = {}  # name -> executor function

    # -------------------------------------------------------------------------
    # Agent Executor Registration
    # -------------------------------------------------------------------------

    def register_agent(self, name: str, executor: callable) -> None:
        """
        Register an agent's execute function.
        executor(query, auth_context, **kwargs) -> Dict[str, Any]
        """
        self._agent_executors[name] = executor

    # -------------------------------------------------------------------------
    # Cross-Agent Query
    # -------------------------------------------------------------------------

    def query_agent(
        self,
        sender: str,
        target_agent: str,
        question: Dict[str, Any],
        timeout_seconds: float = 10.0,
        conversation_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Send a QUERY to another agent and wait for a RESPONSE.
        Blocks until response received or timeout.
        
        Args:
            sender: Name of the querying agent
            target_agent: Agent to query
            question: Content dict with 'question' key
            timeout_seconds: Max time to wait for response
            
        Returns:
            Response content dict, or None on timeout/error
        """
        conv_id = conversation_id or str(uuid.uuid4())

        # Publish QUERY to target agent
        msg = self._bus.publish(
            sender=sender,
            receiver=target_agent,
            msg_type=MessageType.QUERY,
            content=question,
            conversation=conv_id,
            priority=Priority.HIGH.value,
            ttl_seconds=int(timeout_seconds),
        )

        logger.info(f"[DISPATCH] {sender} QUERied {target_agent}: {question.get('question', '')[:50]}")

        # Wait for RESPONSE
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            messages = self._bus.get_messages(sender, since=time.time() - 2.0, max_count=10)
            for m in messages:
                if (m.msg_type == MessageType.RESPONSE.value
                        and m.sender == target_agent
                        and m.conversation == conv_id):
                    logger.info(f"[DISPATCH] {target_agent} RESPONSE to {sender}: {str(m.content)[:80]}")
                    return m.content

            time.sleep(0.2)

        logger.warning(f"[DISPATCH] {sender} → {target_agent}: timeout ({timeout_seconds}s)")
        return None

    # -------------------------------------------------------------------------
    # Conflict Detection & Negotiation
    # -------------------------------------------------------------------------

    def detect_and_negotiate(
        self,
        results: Dict[str, Dict[str, Any]],
        topic: str,
        run_id: Optional[str] = None,
        strategy: ResolutionStrategy = ResolutionStrategy.AVERAGE,
    ) -> Dict[str, Any]:
        """
        Given results from multiple agents, detect if there's a field-level
        conflict and trigger the Negotiation Protocol if needed.
        
        Args:
            results: {agent_name: result_dict} from parallel agent execution
            topic: What is being negotiated (e.g. "LIFNR_0001_net_value")
            run_id: Harness run ID for logging
            
        Returns:
            Merged result with conflict resolution notes
        """
        if len(results) < 2:
            return list(results.values())[0] if results else {}

        # Extract numeric/conflict-prone fields
        conflicts = self._find_conflicts(results)
        
        if not conflicts:
            return self._merge_results(results)

        # Log conflict detection in trajectory
        if run_id:
            try:
                from app.core.harness_runs import get_harness_runs
                hr = get_harness_runs()
                hr.add_trajectory_event(
                    run_id=run_id,
                    step="negotiation_initiated",
                    decision="conflict_detected",
                    reasoning=f"Found {len(conflicts)} conflicting fields: {list(conflicts.keys())}",
                    metadata={"conflicts": conflicts, "agents": list(results.keys())},
                )
            except Exception:
                pass

        # Initiate negotiation
        participants = list(results.keys())
        neg_id = self._neg.initiate(
            topic=topic,
            participants=participants,
            initial_assertions={
                agent: self._build_negotiation_record(results[agent])
                for agent in participants
            }
        )

        # Run to completion
        resolution = self._neg.run_to_completion(neg_id, strategy=strategy)

        # Log resolution in trajectory
        if run_id:
            try:
                hr = get_harness_runs()
                hr.add_trajectory_event(
                    run_id=run_id,
                    step="negotiation_resolved",
                    decision="conflict_resolved",
                    reasoning=f"Strategy={strategy.value}, resolved={resolution}",
                    metadata={"neg_id": neg_id, "strategy": strategy.value},
                )
            except Exception:
                pass

        return {
            "data": [resolution],
            "negotiation": {
                "neg_id": neg_id,
                "strategy": strategy.value,
                "resolved": True,
            }
        }

    def _find_conflicts(self, results: Dict[str, Dict[str, Any]]) -> Dict[str, List[Any]]:
        """
        Find field-level conflicts between agent results.
        Returns {field_name: [value1, value2, ...]} for conflicting fields.
        """
        conflicts: Dict[str, List[Any]] = {}
        
        # Get first record from each agent
        records = {}
        for agent, result in results.items():
            data = result.get("data", [])
            if data and isinstance(data, list) and len(data) > 0:
                records[agent] = data[0]
            elif isinstance(data, dict):
                records[agent] = data

        if not records:
            return {}

        # Find all keys
        all_keys: Set[str] = set()
        for rec in records.values():
            all_keys.update(rec.keys())

        for field in all_keys:
            if field.startswith("_") or field in ("agent_name", "source_table", "confidence_score"):
                continue
            values = {}
            for agent, rec in records.items():
                val = rec.get(field)
                if val is not None:
                    values[agent] = val

            if len(values) > 1:
                unique_vals = set(str(v) for v in values.values())
                if len(unique_vals) > 1:
                    # Only flag as conflict if truly different
                    conflicts[field] = list(values.values())

        return conflicts

    def _build_negotiation_record(self, agent_result: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten an agent result dict into a negotiation assertion record."""
        record = {
            "_source_table": agent_result.get("source_table", ""),
            "_confidence": agent_result.get("confidence_score", 0.8),
        }
        data = agent_result.get("data")
        if isinstance(data, list) and data:
            record.update(data[0])
        elif isinstance(data, dict):
            record.update(data)
        return record

    def _merge_results(self, results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Merge non-conflicting results from multiple agents."""
        merged_data: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()

        for agent, result in results.items():
            for record in result.get("data", []):
                key = self._record_key(record)
                if key not in seen_keys:
                    merged_data.append(record)
                    seen_keys.add(key)

        return {
            "data": merged_data,
            "agents_contributed": list(results.keys()),
            "conflict_count": 0,
        }

    def _record_key(self, record: Dict[str, Any]) -> str:
        """Generate a deduplication key from a record."""
        key_fields = ["LIFNR", "KUNNR", "MATNR", "EBELN", "VBELN", "QALS"]
        parts = []
        for f in key_fields:
            if f in record:
                parts.append(f"{f}={record[f]}")
        if parts:
            return "|".join(parts)
        items_str = str(sorted(record.items()))
        return str(abs(hash(items_str)))

    # -------------------------------------------------------------------------
    # Execute with Bus (Full Integration)
    # -------------------------------------------------------------------------

    def execute_with_bus(
        self,
        agent_name: str,
        query: str,
        auth_context,
        run_id: Optional[str] = None,
        inbox_poll_interval_ms: int = 500,
    ) -> Dict[str, Any]:
        """
        Execute an agent with full message bus support.
        Starts inbox listener thread and processes incoming messages.
        """
        executor = self._agent_executors.get(agent_name)
        if not executor:
            return {"error": f"No executor registered for {agent_name}"}

        conv_id = str(uuid.uuid4())
        inbox_thread: Optional[Thread] = None
        pending_queries: Dict[str, AgentMessage] = {}

        def inbox_listener():
            """Background thread that polls the agent's inbox."""
            last_check = time.time()
            while True:
                messages = self._bus.get_messages(agent_name, since=last_check, max_count=20)
                last_check = time.time()

                for msg in messages:
                    if msg.msg_type == MessageType.QUERY.value:
                        # Someone is asking this agent a question
                        answer = self._answer_query(agent_name, msg.content)
                        self._bus.reply(msg, {"answer": answer, "agent": agent_name})

                    elif msg.msg_type == MessageType.CHALLENGE.value:
                        # Someone challenged our assertion — re-evaluate
                        self._handle_challenge(agent_name, msg)

                time.sleep(inbox_poll_interval_ms / 1000)

        # Start inbox listener
        inbox_thread = Thread(target=inbox_listener, daemon=True)
        inbox_thread.start()
        self._running_threads[agent_name] = inbox_thread

        try:
            result = executor(query=query, auth_context=auth_context)
        finally:
            # Stop inbox thread
            if agent_name in self._running_threads:
                del self._running_threads[agent_name]

        return result

    def _answer_query(self, agent_name: str, content: Dict[str, Any]) -> Any:
        """Answer an incoming QUERY message."""
        question = content.get("question", "")
        context = content.get("context", {})
        
        executor = self._agent_executors.get(agent_name)
        if not executor:
            return {"error": f"No executor for {agent_name}"}
        
        try:
            result = executor(query=question, auth_context=context.get("auth_context"))
            return result.get("data", result)
        except Exception as e:
            return {"error": str(e)}

    def _handle_challenge(self, agent_name: str, msg: AgentMessage) -> None:
        """Handle a CHALLENGE message — re-evaluate our assertion."""
        challenge_data = msg.content.get("challenge", {})
        disputed_field = challenge_data.get("target_field")
        
        logger.info(f"[DISPATCH] {agent_name} received CHALLENGE on {disputed_field}: {challenge_data}")
        
        # In v1: just acknowledge. A full re-evaluation would re-run the query.

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------

    def agent_status(self) -> Dict[str, Any]:
        """Return status of all agents on the message bus."""
        return self._bus.agent_status()

    def active_negotiations(self) -> List[Dict[str, Any]]:
        """Return all active negotiations."""
        return [
            neg.to_dict() for neg in self._neg.list_active()
        ]

