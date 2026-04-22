from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Set


@dataclass
class EvalScope:
    tags: List[str]

    def to_dict(self):
        return {"tags": self.tags}


class ChangeImpactDetector:
    def detect_eval_scope(self, changed_files: Sequence[str] | None = None, changed_components: Sequence[str] | None = None) -> EvalScope:
        tags: Set[str] = set()
        for component in changed_components or []:
            normalized = component.lower()
            if any(token in normalized for token in ["route", "plan", "meta"]):
                tags.add("routing")
            if any(token in normalized for token in ["retriev", "schema", "memory"]):
                tags.add("retrieval")
            if "graph" in normalized:
                tags.add("graph")
            if any(token in normalized for token in ["sentinel", "guard", "mask", "security", "safety"]):
                tags.add("safety")
            if any(token in normalized for token in ["sql", "critique", "validate", "execution"]):
                tags.add("sql")
            if any(token in normalized for token in ["answer", "response", "synthesis"]):
                tags.add("answer")
        for path in changed_files or []:
            lowered = path.lower()
            if "frontend" in lowered:
                tags.add("answer")
        if not tags:
            tags = {"routing", "sql"}
        return EvalScope(tags=sorted(tags))
