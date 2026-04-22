from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RetrievalArtifact:
    source: str
    kind: str
    items: List[str] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "kind": self.kind,
            "items": self.items,
            "score": round(self.score, 3),
            "reason": self.reason,
            "payload": self.payload,
        }


@dataclass
class RetrievalQualityContext:
    query: str
    domain: str
    artifacts: List[RetrievalArtifact] = field(default_factory=list)
    recommended_tables: List[str] = field(default_factory=list)
    recommended_pattern: Optional[Dict[str, Any]] = None
    composite_score: float = 0.0
    trace: List[Dict[str, Any]] = field(default_factory=list)

    def add_artifact(self, artifact: RetrievalArtifact) -> None:
        self.artifacts.append(artifact)
        self.trace.append({
            "event": "artifact_added",
            "source": artifact.source,
            "kind": artifact.kind,
            "items": artifact.items,
            "score": round(artifact.score, 3),
            "reason": artifact.reason,
        })

    def summary(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "domain": self.domain,
            "composite_score": round(self.composite_score, 3),
            "recommended_tables": self.recommended_tables,
            "recommended_pattern": self.recommended_pattern.get("intent") if isinstance(self.recommended_pattern, dict) else None,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }
