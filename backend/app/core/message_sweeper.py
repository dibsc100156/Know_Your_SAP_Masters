from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.message_bus import MessageBus, get_message_bus


class MessageSweeper:
    def __init__(self, bus: Optional[MessageBus] = None) -> None:
        self.bus = bus or get_message_bus()

    def sweep_agent(self, agent: str, max_idle_seconds: int = 300) -> Dict[str, Any]:
        reclaimed = self.bus.claim_stale_pending(agent, min_idle_seconds=max_idle_seconds)
        return {
            "agent": agent,
            "reclaimed": len(reclaimed),
            "delivery_ids": [item.get("delivery_id") for item in reclaimed],
        }
