from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.core.message_types import DeliveryEnvelope


def derive_idempotency_key(
    sender: str,
    receiver: Optional[str],
    msg_type: str,
    content: Dict[str, Any],
    conversation: str,
    reply_to: Optional[str] = None,
) -> str:
    payload = {
        "sender": sender,
        "receiver": receiver,
        "msg_type": msg_type,
        "content": content,
        "conversation": conversation,
        "reply_to": reply_to,
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def build_delivery_envelope(
    sender: str,
    receiver: Optional[str],
    msg_type: str,
    content: Dict[str, Any],
    conversation: str,
    ttl_seconds: int = 300,
    reply_to: Optional[str] = None,
    causal_parent: Optional[str] = None,
    ack_required: bool = True,
    idempotency_key: Optional[str] = None,
) -> DeliveryEnvelope:
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)).isoformat().replace("+00:00", "Z")
    return DeliveryEnvelope(
        delivery_id=str(uuid.uuid4()),
        idempotency_key=idempotency_key or derive_idempotency_key(
            sender=sender,
            receiver=receiver,
            msg_type=msg_type,
            content=content,
            conversation=conversation,
            reply_to=reply_to,
        ),
        sequence_no=int(time.time() * 1000),
        causal_parent=causal_parent or reply_to,
        ack_required=ack_required,
        expires_at=expires_at,
    )
