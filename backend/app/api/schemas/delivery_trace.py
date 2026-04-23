from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DeliveryTraceEntry(BaseModel):
    event: str
    timestamp: Optional[str] = None
    agent: Optional[str] = None
    reason: Optional[str] = None
    conversation: Optional[str] = None


class DeliveryTraceResponse(BaseModel):
    delivery_id: str
    event_count: int = 0
    last_event: Optional[str] = None
    trace: List[Dict[str, Any]] = Field(default_factory=list)
