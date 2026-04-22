from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReasoningTraceEntry(BaseModel):
    phase: str
    decision: Optional[str] = None
    evidence: Optional[List[str]] = None
    detail: Optional[Dict[str, Any]] = None


class ReasoningTraceResponse(BaseModel):
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Optional[Dict[str, Any]] = None
