from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MemorySource(str, Enum):
    EPISODIC_HISTORY = "episodic_history"
    CONVERSATION_CONTEXT = "conversation_context"
    SCRATCHPAD = "scratchpad"
    DUPLICATE_TURN = "duplicate_turn"
    PERSISTENT_PATTERNS = "persistent_patterns"
    GOTCHAS = "gotchas"
    SESSION_META = "session_meta"


@dataclass
class MemoryBudget:
    max_slices: int = 10
    max_chars: int = 2400
    max_turns: int = 6
    max_query_pairs: int = 5
    max_patterns: int = 3
    max_gotchas: int = 3


@dataclass
class MemorySlice:
    source: MemorySource
    label: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source.value,
            "label": self.label,
            "content": self.content,
            "metadata": self.metadata,
            "score": round(self.score, 3),
            "chars": len(self.content or ""),
        }


@dataclass
class MemoryContext:
    session_id: str
    query: str
    role_id: str
    budget: MemoryBudget = field(default_factory=MemoryBudget)
    slices: List[MemorySlice] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    trace: List[Dict[str, Any]] = field(default_factory=list)

    def add_slice(self, slice_: MemorySlice) -> None:
        if len(self.slices) >= self.budget.max_slices:
            self.trace.append({
                "event": "slice_skipped",
                "source": slice_.source.value,
                "label": slice_.label,
                "reason": "max_slices",
            })
            return
        self.slices.append(slice_)
        self.trace.append({
            "event": "slice_added",
            "source": slice_.source.value,
            "label": slice_.label,
            "score": round(slice_.score, 3),
            "chars": len(slice_.content or ""),
        })

    def prompt_text(self) -> str:
        lines: List[str] = []
        total_chars = 0
        for slice_ in self.slices:
            block = f"[{slice_.label}]\n{slice_.content}".strip()
            projected = total_chars + len(block) + (2 if lines else 0)
            if projected > self.budget.max_chars:
                self.trace.append({
                    "event": "budget_truncate",
                    "source": slice_.source.value,
                    "label": slice_.label,
                    "budget_max_chars": self.budget.max_chars,
                })
                break
            lines.append(block)
            total_chars = projected
        return "\n\n".join(lines)

    def summary(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "role_id": self.role_id,
            "slice_count": len(self.slices),
            "sources": [slice_.source.value for slice_ in self.slices],
            "budget": {
                "max_slices": self.budget.max_slices,
                "max_chars": self.budget.max_chars,
                "max_turns": self.budget.max_turns,
                "max_query_pairs": self.budget.max_query_pairs,
                "max_patterns": self.budget.max_patterns,
                "max_gotchas": self.budget.max_gotchas,
            },
            "metadata": self.metadata,
        }

    def memory_trace(self) -> List[Dict[str, Any]]:
        return list(self.trace)
