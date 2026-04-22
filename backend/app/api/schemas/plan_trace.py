from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReplanEvent(BaseModel):
    stage: Optional[str] = None
    reason: Optional[str] = None
    benefit_score: Optional[float] = None
    previous_steps: Optional[List[str]] = None
    revised_steps: Optional[List[str]] = None


class PlanTrace(BaseModel):
    revisions: List[Dict[str, Any]] = Field(default_factory=list)
