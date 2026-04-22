from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from app.core.retrieval_context import RetrievalArtifact, RetrievalQualityContext


class RetrievalQualityScorer:
    SOURCE_WEIGHTS = {
        "schema_lookup": 0.72,
        "schema_auto_discover": 0.68,
        "exploration": 0.74,
        "graph_enhanced_schema_discovery": 0.84,
        "sql_pattern_lookup": 0.92,
        "memory_context": 0.58,
    }

    def assess(
        self,
        *,
        query: str,
        domain: str,
        schema_result: Any,
        graph_result: Any,
        sql_result: Any,
        exploration_result: Any = None,
        memory_context: Any = None,
    ) -> RetrievalQualityContext:
        context = RetrievalQualityContext(query=query, domain=domain)
        self._add_schema_artifact(context, schema_result)
        self._add_exploration_artifact(context, exploration_result)
        self._add_graph_artifact(context, graph_result)
        self._add_sql_pattern_artifact(context, sql_result)
        self._add_memory_artifact(context, memory_context)

        table_votes: Dict[str, float] = defaultdict(float)
        for artifact in context.artifacts:
            weight = artifact.score or 0.0
            for item in artifact.items:
                table_votes[item] += weight

        context.recommended_tables = [
            table for table, _ in sorted(table_votes.items(), key=lambda pair: (-pair[1], pair[0]))
        ]

        sql_patterns = (sql_result.data or {}).get("patterns", []) if getattr(sql_result, "data", None) else []
        if sql_patterns:
            context.recommended_pattern = self._choose_pattern(sql_patterns, context.recommended_tables)
            context.trace.append({
                "event": "pattern_selected",
                "intent": context.recommended_pattern.get("intent"),
                "tables": context.recommended_pattern.get("tables", []),
            })

        if context.artifacts:
            context.composite_score = round(sum(a.score for a in context.artifacts) / len(context.artifacts), 3)
        context.trace.append({
            "event": "retrieval_quality_ready",
            "composite_score": context.composite_score,
            "recommended_tables": context.recommended_tables[:5],
        })
        return context

    def _score(self, source: str, count: int, bonus: float = 0.0) -> float:
        base = self.SOURCE_WEIGHTS.get(source, 0.5)
        breadth = min(0.12, max(0, count - 1) * 0.03)
        return round(min(1.0, base + breadth + bonus), 3)

    def _add_schema_artifact(self, context: RetrievalQualityContext, schema_result: Any) -> None:
        tables = ((schema_result.data or {}).get("tables_used", []) if getattr(schema_result, "data", None) else []) or []
        if not tables:
            return
        context.add_artifact(RetrievalArtifact(
            source="schema_lookup",
            kind="tables",
            items=tables,
            score=self._score("schema_lookup", len(tables)),
            reason="semantic schema retrieval produced candidate tables",
        ))

    def _add_exploration_artifact(self, context: RetrievalQualityContext, exploration_result: Any) -> None:
        if not exploration_result:
            return
        tables = list(getattr(exploration_result, "tables_found", []) or getattr(exploration_result, "new_tables", []) or [])
        if not tables:
            return
        bonus = min(0.08, float(getattr(exploration_result, "confidence", 0.0) or 0.0) * 0.1)
        context.add_artifact(RetrievalArtifact(
            source="exploration",
            kind="tables",
            items=tables,
            score=self._score("exploration", len(tables), bonus=bonus),
            reason="exploration expanded low-confidence schema retrieval",
        ))

    def _add_graph_artifact(self, context: RetrievalQualityContext, graph_result: Any) -> None:
        tables = ((graph_result.data or {}).get("tables_discovered", []) if getattr(graph_result, "data", None) else []) or []
        graph_rows = ((graph_result.data or {}).get("tables", []) if getattr(graph_result, "data", None) else []) or []
        if not tables and graph_rows:
            tables = [row.get("table") for row in graph_rows if row.get("table")]
        if not tables:
            return
        bridge_bonus = 0.06 if any((row.get("is_cross_module_bridge") for row in graph_rows if isinstance(row, dict))) else 0.0
        context.add_artifact(RetrievalArtifact(
            source="graph_enhanced_schema_discovery",
            kind="tables",
            items=tables,
            payload={"top_rows": graph_rows[:3]},
            score=self._score("graph_enhanced_schema_discovery", len(tables), bonus=bridge_bonus),
            reason="graph retrieval surfaced structurally central / bridge tables",
        ))

    def _add_sql_pattern_artifact(self, context: RetrievalQualityContext, sql_result: Any) -> None:
        patterns = ((sql_result.data or {}).get("patterns", []) if getattr(sql_result, "data", None) else []) or []
        if not patterns:
            return
        top = patterns[0]
        tables = top.get("tables", []) or []
        bonus = 0.05 if len(patterns) > 1 else 0.0
        context.add_artifact(RetrievalArtifact(
            source="sql_pattern_lookup",
            kind="pattern",
            items=tables,
            payload={"intent": top.get("intent"), "pattern_count": len(patterns)},
            score=self._score("sql_pattern_lookup", max(1, len(tables)), bonus=bonus),
            reason="retrieval found proven SQL pattern candidates",
        ))

    def _add_memory_artifact(self, context: RetrievalQualityContext, memory_context: Any) -> None:
        if not memory_context:
            return
        prior_tables = list((getattr(memory_context, "metadata", {}) or {}).get("prior_tables", []) or [])
        if not prior_tables:
            return
        context.add_artifact(RetrievalArtifact(
            source="memory_context",
            kind="tables",
            items=prior_tables[:5],
            score=self._score("memory_context", len(prior_tables[:5]), bonus=0.02),
            reason="recent session context provides prior table hints",
        ))

    def _choose_pattern(self, patterns: List[Dict[str, Any]], recommended_tables: List[str]) -> Dict[str, Any]:
        if not recommended_tables:
            return patterns[0]

        def pattern_score(pattern: Dict[str, Any]) -> float:
            tables = pattern.get("tables", []) or []
            overlap = len([t for t in tables if t in recommended_tables])
            distance = float(pattern.get("distance", 0.5) or 0.5)
            return overlap * 1.0 + max(0.0, 0.5 - distance)

        return max(patterns, key=pattern_score)
