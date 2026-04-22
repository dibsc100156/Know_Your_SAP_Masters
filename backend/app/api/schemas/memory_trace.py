from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MemoryTraceEntry(BaseModel):
    event: str
    source: Optional[str] = None
    label: Optional[str] = None
    reason: Optional[str] = None
    score: Optional[float] = None
    chars: Optional[int] = None
    removed_tables: Optional[List[str]] = None
    budget_max_chars: Optional[int] = None


class MemoryTrace(BaseModel):
    entries: List[Dict[str, Any]] = Field(default_factory=list)
