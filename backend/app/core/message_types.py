from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class DeliveryState(str, Enum):
    PENDING = "pending"
    DUPLICATE = "duplicate"


@dataclass
class DeliveryEnvelope:
    delivery_id: str
    idempotency_key: str
    sequence_no: int
    causal_parent: Optional[str] = None
    ack_required: bool = True
    delivery_state: str = DeliveryState.PENDING.value
    expires_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "delivery_id": self.delivery_id,
            "idempotency_key": self.idempotency_key,
            "sequence_no": self.sequence_no,
            "causal_parent": self.causal_parent,
            "ack_required": self.ack_required,
            "delivery_state": self.delivery_state,
            "expires_at": self.expires_at,
        }
