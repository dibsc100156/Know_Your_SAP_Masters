"""
agent_inbox.py — Async Agent Inbox + Message Router
====================================================
Dedicated inbox listener for each domain agent in the swarm.
Polls the message bus for incoming messages (QUERY, CHALLENGE, NEGOTIATE, etc.)
and dispatches them to the registered agent executor or negotiation engine.

Designed for multi-agent swarm scalability — each agent runs its own inbox
thread independently, with graceful start/stop and error recovery.

Usage:
    # Per-agent inbox
    inbox = AgentInbox(agent_name="pur_agent", dispatcher=dispatcher)
    inbox.start()
    # ... agent runs ...
    inbox.stop()

    # Manager for all agents
    manager = InboxManager(dispatcher)
    manager.start_all(agent_names=["pur_agent", "bp_agent", "mm_agent", ...])
    manager.stop_all()
"""

from __future__ import annotations

import time
import logging
import threading
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from app.core.message_bus import message_bus, AgentMessage, MessageType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Dataclasses
# ---------------------------------------------------------------------------

class InboxState(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED  = "paused"
    ERROR   = "error"


@dataclass
class InboxStats:
    """Runtime statistics for an agent's inbox."""
    messages_processed: int = 0
    queries_answered:   int = 0
    challenges_handled:  int = 0
    negotiations_tracked: int = 0
    errors: int = 0
    last_message_at: Optional[str] = None
    last_answer_at: Optional[str] = None
    uptime_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "messages_processed": self.messages_processed,
            "queries_answered":   self.queries_answered,
            "challenges_handled": self.challenges_handled,
            "negotiations_tracked": self.negotiations_tracked,
            "errors": self.errors,
            "last_message_at": self.last_message_at,
            "last_answer_at": self.last_answer_at,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }


# ---------------------------------------------------------------------------
# AgentInbox — Per-Agent Inbox Listener
# ---------------------------------------------------------------------------

class AgentInbox:
    """
    Dedicated inbox listener for a single agent.

    Responsibilities:
      1. POLL — Continuously poll Redis stream for incoming messages
      2. ROUTE — Dispatch each message to the right handler (QUERY → answer, CHALLENGE → re-evaluate, etc.)
      3. REPLY — Send RESPONSE/NEGOTIATE/COMMIT replies back via the message bus
      4. TRACE — Log all message activity to the trajectory_log
      5. METRICS — Track processing stats (messages/sec, error rate, latency)

    Args:
        agent_name: Unique identifier for this agent (e.g. "pur_agent", "bp_agent")
        dispatcher: MessageDispatcher instance with registered agent executors
        poll_interval_ms: How often to poll the Redis stream (default 500ms)
        run_id: Optional harness run ID for trajectory logging
    """

    def __init__(
        self,
        agent_name: str,
        dispatcher,           # MessageDispatcher instance
        poll_interval_ms: int = 500,
        run_id: Optional[str] = None,
    ):
        self.agent_name = agent_name
        self._dispatcher = dispatcher
        self._poll_interval_s = poll_interval_ms / 1000.0
        self._run_id = run_id

        self._state = InboxState.STOPPED
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_check = time.time() - 2.0  # Start with 2s lookback to catch queued messages
        self._started_at: Optional[float] = None

        self.stats = InboxStats()

        # Query handler — uses dispatcher's registered agent executor
        self._query_handler: Optional[Callable] = None

        # Custom message handlers (override point for specialized agents)
        self._custom_handlers: Dict[str, Callable[[AgentMessage], None]] = {}

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start the inbox polling thread. Idempotent — safe to call if already running."""
        if self._state == InboxState.RUNNING:
            logger.debug(f"[{self.agent_name}] inbox already running")
            return

        self._stop_event.clear()
        self._state = InboxState.RUNNING
        self._started_at = time.time()
        self._thread = threading.Thread(target=self._run_loop, name=f"inbox-{self.agent_name}", daemon=True)
        self._thread.start()
        logger.info(f"[{self.agent_name}] inbox started (poll={self._poll_interval_s}s)")

    def stop(self, timeout: float = 5.0) -> None:
        """Gracefully stop the inbox thread."""
        if self._state == InboxState.STOPPED:
            return

        logger.info(f"[{self.agent_name}] inbox stopping...")
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._state = InboxState.STOPPED
        if self._started_at:
            self.stats.uptime_seconds = time.time() - self._started_at
        logger.info(f"[{self.agent_name}] inbox stopped (processed {self.stats.messages_processed} msgs)")

    def pause(self) -> None:
        """Pause polling without stopping the thread."""
        self._state = InboxState.PAUSED

    def resume(self) -> None:
        """Resume polling after a pause."""
        self._state = InboxState.RUNNING

    def register_query_handler(self, handler: Callable[[str, Dict], Any]) -> None:
        """
        Register a custom query handler function.

        handler(question: str, context: Dict) -> Any

        If not registered, uses the dispatcher's registered executor for this agent.
        """
        self._query_handler = handler

    def register_custom_handler(self, msg_type: str, handler: Callable[[AgentMessage], None]) -> None:
        """
        Register a custom handler for a specific message type.

        handler(message: AgentMessage) -> None
        """
        self._custom_handlers[msg_type] = handler

    # -------------------------------------------------------------------------
    # Main polling loop
    # -------------------------------------------------------------------------

    def _run_loop(self) -> None:
        """Main loop: poll for messages, dispatch to handlers, send replies."""
        while not self._stop_event.is_set():
            if self._state == InboxState.PAUSED:
                time.sleep(self._poll_interval_s)
                continue

            try:
                self._poll_and_dispatch()
            except Exception as e:
                self.stats.errors += 1
                logger.error(f"[{self.agent_name}] inbox poll error: {e}")
                # Back off slightly on errors to avoid spinning
                time.sleep(1.0)

            time.sleep(self._poll_interval_s)

    def _poll_and_dispatch(self) -> None:
        """Poll the message bus for new messages and dispatch each one."""
        messages = message_bus.get_messages(
            receiver=self.agent_name,
            since=self._last_check,
            max_count=20,
        )

        if not messages:
            return

        self._last_check = time.time()
        self.stats.last_message_at = datetime.utcnow().isoformat() + "Z"

        for msg in messages:
            self.stats.messages_processed += 1

            try:
                self._dispatch_message(msg)
            except Exception as e:
                self.stats.errors += 1
                logger.error(f"[{self.agent_name}] dispatch error for {msg.msg_type}: {e}")

    def _dispatch_message(self, msg: AgentMessage) -> None:
        """
        Route a single message to the appropriate handler and send a reply if needed.
        """
        msg_type = msg.msg_type.value if hasattr(msg.msg_type, 'value') else str(msg.msg_type)

        # Custom handler takes priority
        if msg_type in self._custom_handlers:
            self._custom_handlers[msg_type](msg)
            return

        if msg_type == MessageType.QUERY.value:
            self._handle_query(msg)
        elif msg_type == MessageType.CHALLENGE.value:
            self._handle_challenge(msg)
        elif msg_type == MessageType.NEGOTIATE.value:
            self._handle_negotiate(msg)
        elif msg_type == MessageType.BROADCAST.value:
            self._handle_broadcast(msg)
        elif msg_type == MessageType.HEARTBEAT.value:
            self._handle_heartbeat(msg)
        elif msg_type in (MessageType.RESPONSE.value, MessageType.ASSERTION.value, MessageType.COMMIT.value):
            # Silently absorb — not directed at this agent's inbox action
            logger.debug(f"[{self.agent_name}] absorbed {msg_type} from {msg.sender}")
        else:
            logger.warning(f"[{self.agent_name}] unknown msg_type: {msg_type}")

    # -------------------------------------------------------------------------
    # Message Handlers
    # -------------------------------------------------------------------------

    def _handle_query(self, msg: AgentMessage) -> None:
        """
        Handle a QUERY: compute answer via executor or custom handler, send RESPONSE.
        """
        question = msg.content.get("question", "")
        context = msg.content.get("context", {})

        logger.info(f"[{self.agent_name}] QUERY from {msg.sender}: {question[:80]}")

        try:
            if self._query_handler:
                answer = self._query_handler(question, context)
            else:
                # Use dispatcher's registered executor
                executor = self._dispatcher._agent_executors.get(self.agent_name)
                if not executor:
                    answer = {"error": f"No executor for {self.agent_name}"}
                else:
                    result = executor(query=question, auth_context=context.get("auth_context"))
                    answer = result.get("data", result)

            # Send reply back to sender
            message_bus.reply(msg, {"answer": answer, "agent": self.agent_name})
            self.stats.queries_answered += 1
            self.stats.last_answer_at = datetime.utcnow().isoformat() + "Z"

            # Trace in harness run
            self._trace_event("query_answered", {
                "from": msg.sender,
                "question": question[:100],
                "agent": self.agent_name,
            })

        except Exception as e:
            logger.error(f"[{self.agent_name}] query handler error: {e}")
            message_bus.reply(msg, {"error": str(e), "agent": self.agent_name})

    def _handle_challenge(self, msg: AgentMessage) -> None:
        """
        Handle a CHALLENGE: re-evaluate our assertion and respond with updated claim.
        """
        challenge_data = msg.content.get("challenge", {})
        disputed_field = challenge_data.get("target_field", "unknown")

        logger.info(f"[{self.agent_name}] CHALLENGE from {msg.sender} on field={disputed_field}")

        self.stats.challenges_handled += 1

        try:
            # Re-run the query if we have context
            original_question = challenge_data.get("original_question", "")
            if original_question:
                executor = self._dispatcher._agent_executors.get(self.agent_name)
                if executor:
                    result = executor(query=original_question, auth_context={})
                    updated_record = result.get("data", [{}])[0] if result.get("data") else {}

                    message_bus.reply(msg, {
                        "re_evaluation": True,
                        "field": disputed_field,
                        "updated_value": updated_record.get(disputed_field),
                        "agent": self.agent_name,
                    })
                    return

            # Fallback: acknowledge the challenge
            message_bus.reply(msg, {
                "re_evaluation": False,
                "field": disputed_field,
                "agent": self.agent_name,
                "note": "Re-evaluation requires original question context",
            })

            self._trace_event("challenge_handled", {
                "from": msg.sender,
                "field": disputed_field,
                "re_evaluated": bool(original_question),
            })

        except Exception as e:
            logger.error(f"[{self.agent_name}] challenge handler error: {e}")
            message_bus.reply(msg, {"error": str(e)})

    def _handle_negotiate(self, msg: AgentMessage) -> None:
        """
        Handle a NEGOTIATE: participate in an active negotiation session
        using the NegotiationEngine API (submit_assertion, submit_challenge, submit_proposal).
        """
        negotiation_content = msg.content.get("negotiation", {})
        topic = negotiation_content.get("topic", "unknown")
        action = negotiation_content.get("action", "assert")  # assert | challenge | propose | commit

        logger.info(f"[{self.agent_name}] NEGOTIATE from {msg.sender}: topic={topic}, action={action}")
        self.stats.negotiations_tracked += 1

        try:
            neg_engine = self._dispatcher._neg
            if not neg_engine:
                logger.warning(f"[{self.agent_name}] no negotiation engine available")
                return

            neg_id = negotiation_content.get("neg_id", "")
            if not neg_id:
                logger.warning(f"[{self.agent_name}] NEGOTIATE msg missing neg_id")
                return

            # Route to the right NegotiationEngine method based on action
            if action == "assert":
                assertion_data = msg.content.get("assertion", {})
                neg_engine.submit_assertion(
                    neg_id=neg_id,
                    agent=self.agent_name,
                    field=assertion_data.get("field"),
                    value=assertion_data.get("value"),
                    confidence=assertion_data.get("confidence", 0.8),
                    source_table=assertion_data.get("source_table", ""),
                )
                logger.info(f"[{self.agent_name}] submitted assertion to neg={neg_id}")

            elif action == "challenge":
                target_agent = negotiation_content.get("target_agent", msg.sender)
                neg_engine.submit_challenge(
                    neg_id=neg_id,
                    challenger=self.agent_name,
                    target_agent=target_agent,
                    field=negotiation_content.get("field"),
                    reason=negotiation_content.get("reason", "Value mismatch"),
                )
                logger.info(f"[{self.agent_name}] submitted challenge to neg={neg_id}")

            elif action == "propose":
                proposal_value = negotiation_content.get("proposal_value")
                neg_engine.submit_proposal(
                    neg_id=neg_id,
                    agent=self.agent_name,
                    field=negotiation_content.get("field"),
                    value=proposal_value,
                    confidence=negotiation_content.get("confidence", 0.8),
                )
                logger.info(f"[{self.agent_name}] submitted proposal to neg={neg_id}")

            elif action == "commit":
                resolved_value = negotiation_content.get("resolved_value")
                neg_engine.commit(
                    neg_id=neg_id,
                    agent=self.agent_name,
                    resolved_value=resolved_value,
                )
                logger.info(f"[{self.agent_name}] committed to neg={neg_id}")

            else:
                logger.warning(f"[{self.agent_name}] unknown negotiation action: {action}")

            self._trace_event("negotiation_participated", {
                "from": msg.sender,
                "topic": topic,
                "action": action,
                "neg_id": neg_id,
            })

        except Exception as e:
            logger.error(f"[{self.agent_name}] negotiate handler error: {e}")

    def _handle_broadcast(self, msg: AgentMessage) -> None:
        """
        Handle a BROADCAST: log it, possibly react if it's a system announcement.
        """
        logger.info(f"[{self.agent_name}] BROADCAST from {msg.sender}: {msg.content}")
        self._trace_event("broadcast_received", {
            "from": msg.sender,
            "content_keys": list(msg.content.keys()),
        })

    def _handle_heartbeat(self, msg: AgentMessage) -> None:
        """Handle a HEARTBEAT: update agent presence, no reply needed."""
        logger.debug(f"[{self.agent_name}] HEARTBEAT from {msg.sender}")

    # -------------------------------------------------------------------------
    # Trajectory Tracing
    # -------------------------------------------------------------------------

    def _trace_event(self, step: str, metadata: Dict[str, Any]) -> None:
        """Log an event to the harness run trajectory log."""
        if not self._run_id:
            return
        try:
            from app.core.harness_runs import get_harness_runs
            hr = get_harness_runs()
            hr.add_trajectory_event(
                run_id=self._run_id,
                step=f"inbox_{step}",
                decision=self.agent_name,
                reasoning=metadata.get("reasoning", ""),
                metadata=metadata,
            )
        except Exception:
            pass  # Never fail a message handler due to tracing errors

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------

    @property
    def state(self) -> InboxState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state == InboxState.RUNNING and self._thread is not None and self._thread.is_alive()

    def get_stats(self) -> Dict[str, Any]:
        """Return runtime statistics for this inbox."""
        stats = self.stats.to_dict()
        stats["state"] = self._state.value
        stats["is_running"] = self.is_running
        stats["agent_name"] = self.agent_name
        return stats


# ---------------------------------------------------------------------------
# InboxManager — Manage Multiple Agent Inboxes
# ---------------------------------------------------------------------------

class InboxManager:
    """
    Manages the lifecycle of multiple AgentInbox instances.
    Provides start_all / stop_all / restart operations for the entire swarm.

    Usage:
        manager = InboxManager(dispatcher)
        manager.start_all(["pur_agent", "bp_agent", "mm_agent", "sd_agent", "qm_agent", "wm_agent", "cross_agent"])
        # ... swarm runs ...
        manager.stop_all()
    """

    def __init__(self, dispatcher):
        self._dispatcher = dispatcher
        self._inboxes: Dict[str, AgentInbox] = {}

    def create_inbox(
        self,
        agent_name: str,
        poll_interval_ms: int = 500,
        run_id: Optional[str] = None,
    ) -> AgentInbox:
        """
        Create (or return existing) inbox for a given agent.
        Idempotent — safe to call multiple times.
        """
        if agent_name in self._inboxes:
            return self._inboxes[agent_name]

        inbox = AgentInbox(
            agent_name=agent_name,
            dispatcher=self._dispatcher,
            poll_interval_ms=poll_interval_ms,
            run_id=run_id,
        )
        self._inboxes[agent_name] = inbox
        return inbox

    def start(self, agent_name: str, **kwargs) -> AgentInbox:
        """Create and start an inbox for an agent."""
        inbox = self.create_inbox(agent_name, **kwargs)
        inbox.start()
        return inbox

    def start_all(
        self,
        agent_names: List[str],
        poll_interval_ms: int = 500,
        run_id: Optional[str] = None,
    ) -> Dict[str, AgentInbox]:
        """
        Create and start inboxes for all listed agents.
        Returns dict of agent_name -> AgentInbox.
        """
        for name in agent_names:
            self.start(name, poll_interval_ms=poll_interval_ms, run_id=run_id)

        logger.info(f"[InboxManager] started {len(agent_names)} inboxes: {agent_names}")
        return self._inboxes

    def stop(self, agent_name: str, timeout: float = 5.0) -> None:
        """Stop and remove a single agent's inbox."""
        if agent_name in self._inboxes:
            self._inboxes[agent_name].stop(timeout=timeout)
            del self._inboxes[agent_name]

    def stop_all(self, timeout: float = 5.0) -> None:
        """Stop all active inboxes."""
        agent_names = list(self._inboxes.keys())
        for name in agent_names:
            try:
                self._inboxes[name].stop(timeout=timeout)
            except Exception as e:
                logger.error(f"[InboxManager] error stopping {name}: {e}")

        self._inboxes.clear()
        logger.info(f"[InboxManager] stopped all inboxes: {agent_names}")

    def get_inbox(self, agent_name: str) -> Optional[AgentInbox]:
        """Get a running inbox by agent name."""
        return self._inboxes.get(agent_name)

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all active inboxes."""
        return {
            name: inbox.get_stats()
            for name, inbox in self._inboxes.items()
        }

    def restart(self, agent_name: str, **kwargs) -> AgentInbox:
        """Stop and restart a single agent's inbox."""
        self.stop(agent_name)
        return self.start(agent_name, **kwargs)

    @property
    def active_count(self) -> int:
        return sum(1 for ib in self._inboxes.values() if ib.is_running)