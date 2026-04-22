from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RecoveryTraceEntry(BaseModel):
    event: str
    error_class: Optional[str] = None
    severity: Optional[str] = None
    attempt_count: Optional[int] = None
    chosen_lane: Optional[str] = None
    reason: Optional[str] = None


class RecoveryTrace(BaseModel):
    entries: List[Dict[str, Any]] = Field(default_factory=list)
