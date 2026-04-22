from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class RetryBudget:
    max_retries: int = 0


@dataclass
class StopCondition:
    halt_on_error: bool = False
    halt_on_retry_exhausted: bool = False


@dataclass
class QualityGate:
    min_items: int = 0
    min_score: Optional[float] = None
    allow_empty: bool = True


@dataclass
class ChainStep:
    name: str
    label: str
    quality_gate: QualityGate = field(default_factory=QualityGate)
    retry_budget: RetryBudget = field(default_factory=RetryBudget)
    stop_condition: StopCondition = field(default_factory=StopCondition)
    required: bool = False


@dataclass
class ChainOutput:
    status: str
    item_count: int = 0
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
