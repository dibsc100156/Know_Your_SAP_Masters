"""
message_bus.py — Inter-Agent Message Bus
=========================================
Redis-backed pub/sub + streams for agent-to-agent communication.
Enables agents to send structured messages: QUERY, RESPONSE, ASSERTION,
CHALLENGE, NEGOTIATE, COMMIT.

Usage:
    from app.core.message_bus import message_bus, AgentMessage, MessageType

    # Send a message
    message_bus.publish(
        sender="pur_agent",
        receiver="bp_agent", 
        msg_type=MessageType.QUERY,
        content={"question": "vendor name for LIFNR 0000010001", "context": {}}
    )

    # Receive messages
    messages = message_bus.get_messages("pur_agent", since=last_check)
"""

from __future__ import annotations

import json
import uuid
import time
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from threading import Thread
import redis

from app.core.message_delivery import build_delivery_envelope
from app.core.message_types import DeliveryState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MessageType(str, Enum):
    QUERY       = "QUERY"        # Asking another agent for information
    RESPONSE    = "RESPONSE"     # Reply to a QUERY
    ASSERTION   = "ASSERTION"    # I claim this is true
    CHALLENGE   = "CHALLENGE"    # I dispute an assertion
    NEGOTIATE   = "NEGOTIATE"    # Proposing resolution to a conflict
    COMMIT      = "COMMIT"       # Final agreement
    BROADCAST   = "BROADCAST"   # Announce to all agents
    HEARTBEAT   = "HEARTBEAT"   # I'm alive / still processing


class Priority(int, Enum):
    LOW     = 0
    NORMAL  = 1
    HIGH    = 2
    URGENT  = 3


# ---------------------------------------------------------------------------
# Message Dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentMessage:
    msg_id:       str
    sender:       str
    receiver:     Optional[str]   # None = broadcast
    msg_type:     str
    content:      Dict[str, Any]
    conversation: str             # Thread ID tying related messages together
    priority:     int = Priority.NORMAL.value
    ttl_seconds:  int = 300
    timestamp:    str = ""
    reply_to:     Optional[str] = None  # msg_id this is in response to
    delivery_id:  str = ""
    idempotency_key: str = ""
    sequence_no:  int = 0
    causal_parent: Optional[str] = None
    ack_required: bool = True
    delivery_state: str = DeliveryState.PENDING.value
    expires_at: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if not self.delivery_id:
            self.delivery_id = self.msg_id

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["msg_type"] = self.msg_type.value if isinstance(self.msg_type, MessageType) else self.msg_type
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentMessage":
        data = dict(d)
        data["msg_type"] = MessageType(data["msg_type"]) if isinstance(data["msg_type"], str) else data["msg_type"]
        data.setdefault("delivery_id", data.get("msg_id", ""))
        data.setdefault("idempotency_key", "")
        data.setdefault("sequence_no", 0)
        data.setdefault("causal_parent", data.get("reply_to"))
        data.setdefault("ack_required", True)
        data.setdefault("delivery_state", DeliveryState.PENDING.value)
        data.setdefault("expires_at", "")
        return cls(**data)

    def is_replyable(self) -> bool:
        msg_type = self.msg_type.value if isinstance(self.msg_type, MessageType) else self.msg_type
        return msg_type in (MessageType.QUERY.value, MessageType.CHALLENGE.value, MessageType.NEGOTIATE.value)

    def short_summary(self) -> str:
        msg_type = self.msg_type.value if isinstance(self.msg_type, MessageType) else self.msg_type
        return (f"[{msg_type}] {self.sender} → "
                f"{self.receiver or '*'} ({self.conversation[:8]})")


# ---------------------------------------------------------------------------
# Redis Keys
# ---------------------------------------------------------------------------

def _stream_key(agent: str) -> str:
    return f"mb:stream:{agent}"

def _inbox_key(agent: str) -> str:
    return f"mb:inbox:{agent}"

def _negotiations_key() -> str:
    return "mb:negotiations"

def _pubsub_channel(agent: str) -> str:
    return f"mb:channel:{agent}"


def _idempotency_key(key: str) -> str:
    return f"mb:idempotency:{key}"


def _pending_key(agent: str) -> str:
    return f"mb:pending:{agent}"


def _trace_key(delivery_id: str) -> str:
    return f"mb:trace:{delivery_id}"


def _dlq_key(agent: str) -> str:
    return f"mb:dlq:{agent}"


def _group_name(agent: str) -> str:
    return f"mb:group:{agent}"


# ---------------------------------------------------------------------------
# Message Bus
# ---------------------------------------------------------------------------

class MessageBus:
    """
    Redis-backed inter-agent message bus.
    
    Uses Redis Streams for message persistence and consumer groups,
    with pub/sub overlay for real-time delivery notifications.
    """

    STREAM_MAXLEN = 10000   # Cap each agent's stream

    def __init__(self, redis_client: Optional[redis.Redis] = None) -> None:
        self._redis = redis_client or self._get_redis()
        self._pubsub_threads: Dict[str, Thread] = {}
        self._handlers: Dict[str, callable] = {}

    def _get_redis(self) -> redis.Redis:
        try:
            import app.core.harness_runs as hr
            return hr.get_redis()
        except Exception:
            return redis.Redis(host="localhost", port=6379, decode_responses=True, socket_connect_timeout=5)

    def _claim_idempotency(self, msg: AgentMessage) -> bool:
        if not msg.idempotency_key:
            return True
        try:
            return bool(self._redis.set(_idempotency_key(msg.idempotency_key), msg.delivery_id, ex=msg.ttl_seconds, nx=True))
        except redis.RedisError:
            return True

    def _record_delivery_event(self, delivery_id: str, event: str, **metadata: Any) -> None:
        try:
            payload = json.dumps({
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                **metadata,
            })
            self._redis.rpush(_trace_key(delivery_id), payload)
        except redis.RedisError:
            return

    def _register_pending(self, msg: AgentMessage, stream_entry_id: Optional[str] = None, consumer: Optional[str] = None) -> None:
        if not msg.receiver or not msg.ack_required:
            return
        try:
            record = json.dumps({
                "message": msg.to_dict(),
                "pending_since": time.time(),
                "attempts": 1,
                "stream_entry_id": stream_entry_id,
                "consumer": consumer,
            })
            self._redis.hset(_pending_key(msg.receiver), msg.delivery_id, record)
            self._record_delivery_event(msg.delivery_id, "pending_registered", receiver=msg.receiver, stream_entry_id=stream_entry_id)
        except redis.RedisError:
            return

    def _ensure_consumer_group(self, agent: str) -> None:
        try:
            self._redis.xgroup_create(_stream_key(agent), _group_name(agent), id="0", mkstream=True)
        except Exception:
            return

    # -------------------------------------------------------------------------
    # Publish / Send
    # -------------------------------------------------------------------------

    def publish(
        self,
        sender: str,
        receiver: str,
        msg_type: MessageType,
        content: Dict[str, Any],
        conversation: Optional[str] = None,
        priority: int = Priority.NORMAL.value,
        ttl_seconds: int = 300,
        reply_to: Optional[str] = None,
    ) -> AgentMessage:
        """
        Send a direct message to a specific agent.
        """
        conversation_id = conversation or str(uuid.uuid4())
        normalized_type = msg_type.value if isinstance(msg_type, MessageType) else msg_type
        envelope = build_delivery_envelope(
            sender=sender,
            receiver=receiver,
            msg_type=normalized_type,
            content=content,
            conversation=conversation_id,
            ttl_seconds=ttl_seconds,
            reply_to=reply_to,
        )
        msg = AgentMessage(
            msg_id=str(uuid.uuid4()),
            sender=sender,
            receiver=receiver,
            msg_type=normalized_type,
            content=content,
            conversation=conversation_id,
            priority=priority,
            ttl_seconds=ttl_seconds,
            reply_to=reply_to,
            delivery_id=envelope.delivery_id,
            idempotency_key=envelope.idempotency_key,
            sequence_no=envelope.sequence_no,
            causal_parent=envelope.causal_parent,
            ack_required=envelope.ack_required,
            delivery_state=envelope.delivery_state,
            expires_at=envelope.expires_at,
        )
        return self._deliver(msg)

    def broadcast(
        self,
        sender: str,
        msg_type: MessageType,
        content: Dict[str, Any],
        conversation: Optional[str] = None,
        priority: int = Priority.NORMAL.value,
    ) -> AgentMessage:
        """
        Broadcast a message to all agents.
        """
        conversation_id = conversation or str(uuid.uuid4())
        normalized_type = msg_type.value if isinstance(msg_type, MessageType) else msg_type
        envelope = build_delivery_envelope(
            sender=sender,
            receiver=None,
            msg_type=normalized_type,
            content=content,
            conversation=conversation_id,
            ttl_seconds=300,
        )
        msg = AgentMessage(
            msg_id=str(uuid.uuid4()),
            sender=sender,
            receiver=None,
            msg_type=normalized_type,
            content=content,
            conversation=conversation_id,
            priority=priority,
            delivery_id=envelope.delivery_id,
            idempotency_key=envelope.idempotency_key,
            sequence_no=envelope.sequence_no,
            causal_parent=envelope.causal_parent,
            ack_required=envelope.ack_required,
            delivery_state=envelope.delivery_state,
            expires_at=envelope.expires_at,
        )
        return self._deliver(msg)

    def reply(
        self,
        original: AgentMessage,
        content: Dict[str, Any],
        msg_type: Optional[MessageType] = None,
    ) -> AgentMessage:
        """
        Reply to a specific message. Infers the correct reply type.
        """
        type_map = {
            MessageType.QUERY:     MessageType.RESPONSE,
            MessageType.CHALLENGE: MessageType.NEGOTIATE,
            MessageType.NEGOTIATE: MessageType.COMMIT,
        }
        reply_type = (msg_type or type_map.get(
            MessageType(original.msg_type)
            if isinstance(original.msg_type, str) else original.msg_type
        ) or MessageType.RESPONSE).value

        return self.publish(
            sender=original.receiver or "unknown",
            receiver=original.sender,
            msg_type=reply_type,
            content=content,
            conversation=original.conversation,
            reply_to=original.msg_id,
        )

    def _deliver(self, msg: AgentMessage) -> AgentMessage:
        """
        Deliver a message: write to receiver's stream + publish via pub/sub.
        """
        try:
            if not self._claim_idempotency(msg):
                msg.delivery_state = DeliveryState.DUPLICATE.value
                self._record_delivery_event(msg.delivery_id, "duplicate_suppressed", receiver=msg.receiver)
                logger.info(f"[MB] Duplicate delivery suppressed: {msg.short_summary()}")
                return msg

            pipe = self._redis.pipeline()

            # 1. Write to receiver's stream (or all streams if broadcast)
            data = msg.to_dict()
            data.pop("msg_id", None)
            stream_entry_id: Optional[str] = None
            
            if msg.receiver:
                self._ensure_consumer_group(msg.receiver)
                stream_key = _stream_key(msg.receiver)
                pipe.xadd(stream_key, data, maxlen=self.STREAM_MAXLEN)
                # Also write to receiver's inbox sorted set
                inbox_key = _inbox_key(msg.receiver)
                pipe.zadd(inbox_key, {json.dumps(data): time.time()})
                # Trim inbox to last 500
                pipe.zremrangebyrank(inbox_key, 0, -501)
            else:
                # Broadcast: write to all known agent streams
                for agent in self._known_agents():
                    self._ensure_consumer_group(agent)
                    pipe.xadd(_stream_key(agent), data, maxlen=self.STREAM_MAXLEN)
                    pipe.zadd(_inbox_key(agent), {json.dumps(data): time.time()})

            # 2. Publish notification via pub/sub channel
            channel = _pubsub_channel(msg.receiver) if msg.receiver else "mb:broadcast"
            pipe.publish(channel, msg.msg_id)
            results = pipe.execute()
            if msg.receiver and isinstance(results, list) and results:
                stream_entry_id = results[0]
            self._record_delivery_event(msg.delivery_id, "published", receiver=msg.receiver, conversation=msg.conversation, stream_entry_id=stream_entry_id)
            self._register_pending(msg, stream_entry_id=stream_entry_id)

            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"[MB] Published: {msg.short_summary()}")

        except redis.RedisError as e:
            logger.error(f"[MB] Redis error delivering message: {e}")

        return msg

    # -------------------------------------------------------------------------
    # Receive / Poll
    # -------------------------------------------------------------------------

    def get_messages(
        self,
        agent: Optional[str] = None,
        since: Optional[float] = None,
        timeout_ms: int = 0,
        max_count: int = 50,
        receiver: Optional[str] = None,
        consumer: Optional[str] = None,
        use_consumer_groups: bool = True,
    ) -> List[AgentMessage]:
        """
        Poll for new messages addressed to `agent`.
        Reads from the agent's Redis Stream since the given Unix timestamp.
        timeout_ms=0 means non-blocking; >0 means block up to that long.
        """
        messages: List[AgentMessage] = []
        target_agent = receiver or agent
        if not target_agent:
            return messages
        try:
            stream_key = _stream_key(target_agent)
            active_consumer = consumer or target_agent

            if use_consumer_groups:
                self._ensure_consumer_group(target_agent)
                try:
                    group_entries = self._redis.xreadgroup(
                        groupname=_group_name(target_agent),
                        consumername=active_consumer,
                        streams={stream_key: ">"},
                        count=max_count,
                        block=timeout_ms if timeout_ms > 0 else None,
                    )
                    entries = group_entries[0][1] if group_entries else []
                except Exception:
                    entries = []
            elif since:
                entries = self._redis.xrange(stream_key, min=f"{since}+", max="+", count=max_count)
            else:
                entries = self._redis.xrevrange(stream_key, "+", "-", count=max_count)

            for entry_id, data in entries:
                try:
                    payload = dict(data)
                    payload.setdefault("msg_id", entry_id)
                    msg = AgentMessage.from_dict(payload)
                    if msg.delivery_id:
                        try:
                            pending_payload = self._redis.hget(_pending_key(target_agent), msg.delivery_id)
                            if pending_payload:
                                pending_data = json.loads(pending_payload)
                                pending_data["stream_entry_id"] = entry_id
                                pending_data["consumer"] = active_consumer
                                pending_data["pending_since"] = time.time()
                                self._redis.hset(_pending_key(target_agent), msg.delivery_id, json.dumps(pending_data))
                        except Exception:
                            pass
                    messages.append(msg)
                except Exception as e:
                    logger.warning(f"[MB] Failed to parse message: {e}")

        except redis.RedisError as e:
            logger.error(f"[MB] Error reading stream for {target_agent}: {e}")

        return messages

    def wait_for_message(
        self,
        agent: str,
        timeout_ms: int = 5000,
        poll_interval_ms: int = 200,
    ) -> Optional[AgentMessage]:
        """
        Block until a message arrives for `agent`.
        Uses pub/sub notification to avoid tight polling loops.
        """
        pubsub = self._redis.pubsub()
        channel = _pubsub_channel(agent)
        pubsub.subscribe(channel)

        deadline = time.time() + (timeout_ms / 1000)
        msg: Optional[AgentMessage] = None

        try:
            while time.time() < deadline:
                remaining = (deadline - time.time()) * 1000
                msg_data = pubsub.get_message(timeout=min(remaining / 1000, 1.0))
                
                if msg_data and msg_data["type"] == "message":
                    # A message notification arrived — now read from stream
                    messages = self.get_messages(agent=agent, consumer=agent, timeout_ms=0, max_count=5, use_consumer_groups=True)
                    if messages:
                        msg = messages[0]
                        break

        finally:
            pubsub.unsubscribe(channel)
            pubsub.close()

        return msg

    def get_pending(self, agent: str) -> List[Dict[str, Any]]:
        try:
            records = self._redis.hgetall(_pending_key(agent))
            result: List[Dict[str, Any]] = []
            for delivery_id, payload in records.items():
                data = json.loads(payload)
                result.append({"delivery_id": delivery_id, **data})
            return result
        except redis.RedisError:
            return []

    def ack_message(self, agent: str, delivery_id: str) -> bool:
        try:
            payload = self._redis.hget(_pending_key(agent), delivery_id)
            if not payload:
                return False
            data = json.loads(payload)
            stream_entry_id = data.get("stream_entry_id")
            if stream_entry_id:
                try:
                    self._redis.xack(_stream_key(agent), _group_name(agent), stream_entry_id)
                except Exception:
                    pass
            self._redis.hdel(_pending_key(agent), delivery_id)
            self._record_delivery_event(delivery_id, "acknowledged", agent=agent, stream_entry_id=stream_entry_id)
            return True
        except redis.RedisError:
            return False

    def move_to_dead_letter(self, agent: str, delivery_id: str, payload: Dict[str, Any], reason: str) -> None:
        try:
            self._redis.hset(_dlq_key(agent), delivery_id, json.dumps({"reason": reason, **payload}))
            self._record_delivery_event(delivery_id, "dead_lettered", agent=agent, reason=reason)
        except redis.RedisError:
            return

    def nack_message(self, agent: str, delivery_id: str, reason: str, requeue: bool = False) -> bool:
        try:
            payload = self._redis.hget(_pending_key(agent), delivery_id)
            if not payload:
                return False
            data = json.loads(payload)
            self._record_delivery_event(delivery_id, "nack", agent=agent, reason=reason, requeue=requeue)
            if requeue:
                data["pending_since"] = time.time()
                data["attempts"] = int(data.get("attempts", 1)) + 1
                self._redis.hset(_pending_key(agent), delivery_id, json.dumps(data))
                self._record_delivery_event(delivery_id, "requeued", agent=agent, attempts=data["attempts"])
            else:
                self._redis.hdel(_pending_key(agent), delivery_id)
                self.move_to_dead_letter(agent, delivery_id, data, reason=reason)
            return True
        except redis.RedisError:
            return False

    def claim_stale_pending(self, agent: str, min_idle_seconds: int = 30) -> List[Dict[str, Any]]:
        reclaimed: List[Dict[str, Any]] = []
        now = time.time()
        try:
            for delivery_id, payload in self._redis.hgetall(_pending_key(agent)).items():
                data = json.loads(payload)
                pending_since = float(data.get("pending_since", now))
                if (now - pending_since) >= min_idle_seconds:
                    stream_entry_id = data.get("stream_entry_id")
                    consumer = data.get("consumer") or f"reclaimer:{agent}"
                    if stream_entry_id:
                        try:
                            self._redis.xautoclaim(
                                _stream_key(agent),
                                _group_name(agent),
                                consumer,
                                int(min_idle_seconds * 1000),
                                "0-0",
                                count=1,
                            )
                        except Exception:
                            pass
                    data["pending_since"] = now
                    data["attempts"] = int(data.get("attempts", 1)) + 1
                    data["consumer"] = consumer
                    self._redis.hset(_pending_key(agent), delivery_id, json.dumps(data))
                    self._record_delivery_event(delivery_id, "stale_claimed", agent=agent, attempts=data["attempts"], consumer=consumer)
                    reclaimed.append({"delivery_id": delivery_id, **data})
        except redis.RedisError:
            return []
        return reclaimed

    def get_delivery_trace(self, delivery_id: str) -> List[Dict[str, Any]]:
        try:
            entries = self._redis.lrange(_trace_key(delivery_id), 0, -1)
            return [json.loads(entry) for entry in entries]
        except redis.RedisError:
            return []

    # -------------------------------------------------------------------------
    # Inbox Management
    # -------------------------------------------------------------------------

    def get_inbox(
        self,
        agent: str,
        limit: int = 50,
        only_types: Optional[List[MessageType]] = None,
    ) -> List[AgentMessage]:
        """
        Get recent messages from agent's inbox (sorted by timestamp desc).
        """
        messages: List[AgentMessage] = []
        try:
            inbox_key = _inbox_key(agent)
            entries = self._redis.zrevrange(inbox_key, 0, limit - 1)
            for entry_json in entries:
                try:
                    data = json.loads(entry_json)
                    msg = AgentMessage.from_dict(data)
                    if only_types and msg.msg_type not in [t.value for t in only_types]:
                        continue
                    messages.append(msg)
                except Exception:
                    continue
        except redis.RedisError as e:
            logger.error(f"[MB] Error reading inbox for {agent}: {e}")

        return messages

    def clear_inbox(self, agent: str) -> int:
        """Clear an agent's inbox. Returns number of messages cleared."""
        try:
            n = self._redis.zcard(_inbox_key(agent))
            self._redis.delete(_inbox_key(agent))
            return n
        except redis.RedisError:
            return 0

    def get_conversation(self, agent: str, conversation_id: str) -> List[AgentMessage]:
        """Get all messages in a specific conversation thread."""
        all_msgs = self.get_inbox(agent, limit=500)
        return [m for m in all_msgs if m.conversation == conversation_id]

    # -------------------------------------------------------------------------
    # Negotiation Registry
    # -------------------------------------------------------------------------

    def register_negotiation(self, neg_id: str, participants: List[str], topic: str) -> None:
        """Register an active negotiation."""
        key = _negotiations_key()
        data = json.dumps({
            "neg_id": neg_id,
            "topic": topic,
            "participants": participants,
            "started_at": datetime.utcnow().isoformat() + "Z",
        })
        self._redis.hset(key, neg_id, data)

    def get_active_negotiations(self, agent: str) -> List[Dict[str, Any]]:
        """Get all negotiations involving `agent`."""
        try:
            all_neg = self._redis.hgetall(_negotiations_key())
            result = []
            for neg_id, data in all_neg.items():
                d = json.loads(data)
                if agent in d.get("participants", []):
                    result.append(d)
            return result
        except redis.RedisError:
            return []

    def resolve_negotiation(self, neg_id: str) -> None:
        """Remove a concluded negotiation from the registry."""
        self._redis.hdel(_negotiations_key(), neg_id)

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------

    def _known_agents(self) -> List[str]:
        """List of agents with active streams/inboxes."""
        try:
            keys = self._redis.keys("mb:stream:*")
            return [k.replace("mb:stream:", "") for k in keys]
        except redis.RedisError:
            return []

    def agent_status(self) -> Dict[str, Any]:
        """Return status of all agents (for debugging/monitoring)."""
        agents = self._known_agents()
        status = {}
        for agent in agents:
            try:
                stream_len = self._redis.xlen(_stream_key(agent))
                inbox_len = self._redis.zcard(_inbox_key(agent))
                pending_len = len(self.get_pending(agent))
                dead_letter_len = len(self._redis.hgetall(_dlq_key(agent)))
                negs = self.get_active_negotiations(agent)
                status[agent] = {
                    "stream_count": stream_len,
                    "inbox_count": inbox_len,
                    "pending_count": pending_len,
                    "dead_letter_count": dead_letter_len,
                    "active_negotiations": len(negs),
                }
            except redis.RedisError:
                status[agent] = {"error": "unavailable"}
        return status

    def flush_all(self) -> None:
        """Flush all message bus data. Use with caution."""
        try:
            keys = self._redis.keys("mb:*")
            if keys:
                self._redis.delete(*keys)
            logger.warning("[MB] All message bus data flushed")
        except redis.RedisError as e:
            logger.error(f"[MB] Error flushing: {e}")


# ---------------------------------------------------------------------------
# Module Singleton
# ---------------------------------------------------------------------------

_message_bus: Optional[MessageBus] = None

def get_message_bus() -> MessageBus:
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus

def set_message_bus(bus: MessageBus) -> None:
    global _message_bus
    _message_bus = bus

# Convenience aliases
message_bus = get_message_bus()
