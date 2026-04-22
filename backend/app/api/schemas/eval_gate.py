from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvalGateSummary(BaseModel):
    golden_set: Optional[str] = None
    scope: List[str] = Field(default_factory=list)
    result_count: int = 0
    pass_rate: float = 1.0
    verdict: str = "pass"
    reasons: List[str] = Field(default_factory=list)
    results: Optional[List[Dict[str, Any]]] = None
