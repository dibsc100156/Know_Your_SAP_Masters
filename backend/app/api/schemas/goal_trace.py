from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GoalTraceEntry(BaseModel):
    phase: str
    status: Optional[str] = None
    detail: Optional[Dict[str, Any]] = None


class GoalTrace(BaseModel):
    entries: List[Dict[str, Any]] = Field(default_factory=list)
