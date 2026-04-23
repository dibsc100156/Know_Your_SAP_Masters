from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.message_bus import MessageBus, get_message_bus


class MessageReplay:
    def __init__(self, bus: Optional[MessageBus] = None) -> None:
        self.bus = bus or get_message_bus()

    def replay_conversation(self, agent: str, conversation_id: str) -> List[Dict[str, Any]]:
        return [msg.to_dict() for msg in self.bus.get_conversation(agent, conversation_id)]

    def replay_pending(self, agent: str, min_idle_seconds: int = 30) -> List[Dict[str, Any]]:
        return self.bus.claim_stale_pending(agent, min_idle_seconds=min_idle_seconds)
