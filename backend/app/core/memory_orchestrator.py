from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.episodic_memory import EpisodicMemoryStore, get_memory_store
from app.core.memory_context import MemoryBudget, MemoryContext, MemorySlice, MemorySource
from app.core.memory_layer import sap_memory
from app.core.memory_policy import get_memory_policy


class MemoryOrchestrator:
    def __init__(self, memory_store: Optional[EpisodicMemoryStore] = None):
        self.memory_store = memory_store or get_memory_store()
        self.policy = get_memory_policy()

    def build_context(
        self,
        query: str,
        session_id: str,
        auth_context: Any,
        domain_hint: str = "auto",
        budget: Optional[MemoryBudget] = None,
    ) -> MemoryContext:
        budget = budget or MemoryBudget()
        session_id = session_id or getattr(auth_context, "session_id", None) or f"sess:{auth_context.role_id.lower()}"

        try:
            self.memory_store.update_session_meta(
                session_id,
                role_id=auth_context.role_id,
                user_id=getattr(auth_context, "user_id", None),
            )
        except Exception:
            pass

        context = MemoryContext(
            session_id=session_id,
            query=query,
            role_id=auth_context.role_id,
            budget=budget,
        )
        context.trace.append({"event": "memory_context_start", "session_id": session_id, "query": query[:120]})

        is_dup, dedup_sig = self.memory_store.check_dedup(session_id, query)
        duplicate_record = self.memory_store.find_recent_duplicate(session_id, query, limit=10)
        is_dup = bool(is_dup or duplicate_record is not None)
        history = self.memory_store.get_history(session_id, limit=budget.max_query_pairs)
        recent_query_pairs = self.memory_store.get_recent_query_pairs(session_id, limit=budget.max_query_pairs)
        scratchpad = self.memory_store.get_all_scratchpad(session_id)
        ctx_snippet = self.memory_store.get_recent_context_for_prompt(session_id, max_turns=budget.max_turns)
        meta = self.memory_store.get_session_meta(session_id)

        prior_tables: List[str] = []
        for rec in history:
            prior_tables.extend(list(getattr(rec, "tables_used", []) or []))
        if isinstance(scratchpad.get("last_tables"), list):
            prior_tables.extend(scratchpad.get("last_tables") or [])
        prior_tables = list(dict.fromkeys(prior_tables))

        lookup_domain = domain_hint
        if lookup_domain == "auto" and duplicate_record and getattr(duplicate_record, "domain", None):
            lookup_domain = duplicate_record.domain

        boosted_patterns = sap_memory.get_boosted_patterns(domain=lookup_domain, top_k=budget.max_patterns) if lookup_domain != "auto" else []
        gotchas = sap_memory.get_gotchas(domain=None if lookup_domain == "auto" else lookup_domain)[: budget.max_gotchas]

        context.metadata.update({
            "backend": getattr(self.memory_store, "_backend_name", "unknown"),
            "dedup_hit": is_dup,
            "dedup_signature": dedup_sig,
            "duplicate_of_turn": getattr(duplicate_record, "turn_id", None),
            "prior_turns": len(history),
            "prior_tables": prior_tables,
            "recent_query_pairs": recent_query_pairs,
            "scratchpad": scratchpad,
            "context_window": getattr(self.memory_store, "context_window", budget.max_turns),
            "history_limit": getattr(self.memory_store, "query_history_limit", budget.max_query_pairs),
            "session_ttl_seconds": getattr(self.memory_store, "session_ttl", 0),
            "session_role": getattr(meta, "role_id", auth_context.role_id),
            "resolved_domain_hint": lookup_domain,
        })

        if meta:
            context.add_slice(MemorySlice(
                source=MemorySource.SESSION_META,
                label="Session Meta",
                content=f"Role: {meta.role_id} | Turns: {meta.turn_count} | Tags: {', '.join(meta.tags) or 'none'}",
                metadata={"turn_count": meta.turn_count, "tags": meta.tags},
                score=0.25,
            ))

        if duplicate_record:
            context.add_slice(MemorySlice(
                source=MemorySource.DUPLICATE_TURN,
                label="Duplicate Turn",
                content=(
                    f"Recent duplicate turn #{duplicate_record.turn_id} matched this query. "
                    f"Domain={duplicate_record.domain}; tables={duplicate_record.tables_used}; "
                    f"answer={duplicate_record.answer_excerpt or '?'}"
                ),
                metadata={"tables": duplicate_record.tables_used, "turn_id": duplicate_record.turn_id},
                score=0.95,
            ))

        if ctx_snippet:
            context.add_slice(MemorySlice(
                source=MemorySource.CONVERSATION_CONTEXT,
                label="Recent Conversation",
                content=ctx_snippet,
                metadata={"turns": budget.max_turns},
                score=0.7,
            ))

        if recent_query_pairs:
            lines = []
            for pair in recent_query_pairs[-budget.max_query_pairs:]:
                tables = ", ".join(pair.get("tables_used") or []) or "none"
                lines.append(f"- {pair.get('query')} -> tables:{tables} domain:{pair.get('domain')} conf:{pair.get('confidence')}")
            context.add_slice(MemorySlice(
                source=MemorySource.EPISODIC_HISTORY,
                label="Recent Query Pairs",
                content="\n".join(lines),
                metadata={"tables": prior_tables, "count": len(recent_query_pairs)},
                score=0.8,
            ))

        if scratchpad:
            context.add_slice(MemorySlice(
                source=MemorySource.SCRATCHPAD,
                label="Scratchpad",
                content=", ".join(f"{k}={v}" for k, v in sorted(scratchpad.items())),
                metadata={"tables": scratchpad.get("last_tables", []) if isinstance(scratchpad.get("last_tables"), list) else []},
                score=0.75,
            ))

        if boosted_patterns:
            lines = []
            pattern_tables: List[str] = []
            for pattern in boosted_patterns[: budget.max_patterns]:
                pattern_tables.extend(pattern.get("tables", []) or [])
                lines.append(
                    f"- {pattern.get('pattern_name')} success={pattern.get('success_count', 0)} fail={pattern.get('failure_count', 0)}"
                )
            context.add_slice(MemorySlice(
                source=MemorySource.PERSISTENT_PATTERNS,
                label="Boosted Patterns",
                content="\n".join(lines),
                metadata={"tables": list(dict.fromkeys(pattern_tables)), "count": len(boosted_patterns)},
                score=0.6,
            ))

        if gotchas:
            lines = [f"- [{g.get('severity', 'info')}] {g.get('pattern') or g.get('description') or '?'}" for g in gotchas]
            context.add_slice(MemorySlice(
                source=MemorySource.GOTCHAS,
                label="Known Gotchas",
                content="\n".join(lines),
                metadata={"count": len(gotchas)},
                score=0.5,
            ))

        context = self.policy.filter_memory_for_role(context, auth_context)
        context.trace.append({
            "event": "memory_context_ready",
            "slice_count": len(context.slices),
            "sources": [slice_.source.value for slice_ in context.slices],
        })
        return context


_orchestrator: Optional[MemoryOrchestrator] = None


def get_memory_orchestrator() -> MemoryOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MemoryOrchestrator()
    return _orchestrator
