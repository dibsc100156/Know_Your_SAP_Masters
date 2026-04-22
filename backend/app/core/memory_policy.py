from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.memory_context import MemoryContext, MemorySlice


@dataclass
class RetentionRule:
    event_type: str
    ttl_seconds: int


@dataclass
class VisibilityRule:
    rule_name: str
    removed_tables: List[str]


class MemoryRedactionPolicy:
    def redact_memory_slice(self, slice_: MemorySlice, auth_context: Any) -> Optional[MemorySlice]:
        metadata = dict(slice_.metadata or {})
        tables = metadata.get("tables") or []
        if not tables:
            return slice_

        allowed_tables = [t for t in tables if auth_context.is_table_allowed(t)]
        removed_tables = [t for t in tables if t not in allowed_tables]
        if not allowed_tables and removed_tables:
            return None

        if removed_tables:
            metadata["tables"] = allowed_tables
            metadata["redacted_tables"] = removed_tables
            content = slice_.content
            for table in removed_tables:
                content = content.replace(table, "[REDACTED_TABLE]")
            return MemorySlice(
                source=slice_.source,
                label=slice_.label,
                content=content,
                metadata=metadata,
                score=slice_.score,
            )
        return slice_


class MemoryPolicy:
    def __init__(self):
        self._redactor = MemoryRedactionPolicy()
        self._retention = {
            "query": RetentionRule(event_type="query", ttl_seconds=3600 * 8),
            "result": RetentionRule(event_type="result", ttl_seconds=3600 * 8),
            "heal": RetentionRule(event_type="heal", ttl_seconds=3600 * 24),
            "feedback": RetentionRule(event_type="feedback", ttl_seconds=3600 * 24 * 7),
        }

    def filter_memory_for_role(self, context: MemoryContext, auth_context: Any) -> MemoryContext:
        filtered: List[MemorySlice] = []
        removed_tables: List[str] = []
        for slice_ in context.slices:
            redacted = self._redactor.redact_memory_slice(slice_, auth_context)
            if redacted is None:
                removed_tables.extend((slice_.metadata or {}).get("tables") or [])
                context.trace.append({
                    "event": "slice_removed_by_policy",
                    "source": slice_.source.value,
                    "label": slice_.label,
                    "reason": "all_tables_denied",
                })
                continue
            if redacted.metadata.get("redacted_tables"):
                removed_tables.extend(redacted.metadata.get("redacted_tables") or [])
                context.trace.append({
                    "event": "slice_redacted_by_policy",
                    "source": redacted.source.value,
                    "label": redacted.label,
                    "removed_tables": redacted.metadata.get("redacted_tables"),
                })
            filtered.append(redacted)

        context.slices = filtered
        prior_tables = context.metadata.get("prior_tables") or []
        context.metadata["prior_tables"] = [t for t in prior_tables if auth_context.is_table_allowed(t)]
        scratchpad = context.metadata.get("scratchpad") or {}
        if isinstance(scratchpad, dict) and isinstance(scratchpad.get("last_tables"), list):
            scratchpad["last_tables"] = [t for t in scratchpad.get("last_tables", []) if auth_context.is_table_allowed(t)]
            context.metadata["scratchpad"] = scratchpad
        if removed_tables:
            context.metadata["policy_redactions"] = sorted(set(removed_tables))
        return context

    def retention_for(self, event_type: str) -> int:
        return self._retention.get(event_type, RetentionRule(event_type=event_type, ttl_seconds=3600)).ttl_seconds


_policy: Optional[MemoryPolicy] = None


def get_memory_policy() -> MemoryPolicy:
    global _policy
    if _policy is None:
        _policy = MemoryPolicy()
    return _policy
