from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.core.message_bus import MessageBus, _dlq_key, get_message_bus


class DeadLetterQueue:
    def __init__(self, bus: Optional[MessageBus] = None) -> None:
        self.bus = bus or get_message_bus()

    def get_dead_letters(self, agent: str) -> List[Dict[str, Any]]:
        try:
            records = self.bus._redis.hgetall(_dlq_key(agent))
            return [{"delivery_id": delivery_id, **json.loads(payload)} for delivery_id, payload in records.items()]
        except Exception:
            return []
