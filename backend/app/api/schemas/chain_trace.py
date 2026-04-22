from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChainTraceEntry(BaseModel):
    step: str
    label: Optional[str] = None
    status: Optional[str] = None
    item_count: Optional[int] = None
    score: Optional[float] = None
    gate_verdict: Optional[str] = None
    gate_reason: Optional[str] = None
    decision: Optional[str] = None
    decision_reason: Optional[str] = None
    attempts: Optional[int] = None


class ChainTrace(BaseModel):
    entries: List[Dict[str, Any]] = Field(default_factory=list)
