from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.message_bus import MessageBus, get_message_bus


class DeliveryTraceView:
    def __init__(self, bus: Optional[MessageBus] = None) -> None:
        self.bus = bus or get_message_bus()

    def fetch(self, delivery_id: str) -> Dict[str, Any]:
        trace = self.bus.get_delivery_trace(delivery_id)
        return {
            "delivery_id": delivery_id,
            "trace": trace,
            "event_count": len(trace),
            "last_event": trace[-1]["event"] if trace else None,
        }
