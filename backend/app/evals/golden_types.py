from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CoverageTag(str, Enum):
    ROUTING = "routing"
    RETRIEVAL = "retrieval"
    GRAPH = "graph"
    SAFETY = "safety"
    SQL = "sql"
    ANSWER = "answer"


@dataclass
class ExpectedOutcome:
    min_confidence: float = 0.0
    required_tables: List[str] = field(default_factory=list)
    required_masked_fields: List[str] = field(default_factory=list)
    required_routing_path: Optional[str] = None


@dataclass
class GoldenCase:
    case_id: str
    name: str
    domain: Optional[str]
    coverage_tags: List[CoverageTag]
    expected: ExpectedOutcome

    def matches_scope(self, scope_tags: List[str], domain: Optional[str]) -> bool:
        if self.domain and domain and self.domain.lower() != domain.lower():
            return False
        return any(tag.value in scope_tags for tag in self.coverage_tags)


@dataclass
class GoldenSet:
    name: str
    version: str
    cases: List[GoldenCase]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "case_count": len(self.cases),
        }
