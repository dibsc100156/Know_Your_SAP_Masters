# Graph Provenance Recorder — Priority 4 from AI_ENGINEER_TALKS_IMPROVEMENTS.md
# =============================================================
# Adds explainable traversal path to every orchestrator result.
# Based on Stephen Chin's insight: "Give the LLM structured graph context
# instead of text chunks. The reasoning chain becomes auditable."
#
# Each result gets a graph_provenance dict:
#   primary_table, traversal_path, join_reason,
#   tables_explored, tables_excluded, confidence_reason
#
# Usage:
#   from app.core.graph_provenance import GraphProvenanceRecorder
#   rec = GraphProvenanceRecorder()
#   rec.record_step("schema_lookup", tables_found=["LFA1", "LFB1"])
#   rec.record_step("graph_traverse", tables_found=["LFA1","EKKO","EKPO"])
#   provenance = rec.build_provenance()

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class TraversalStep:
    step_name: str          # "schema_lookup", "graph_traverse", "all_paths_explore"
    tables_found: List[str] # tables discovered at this step
    skipped: bool           # whether this step was skipped by routing
    tool: str = ""
    elapsed_ms: float = 0.0


class GraphProvenanceRecorder:
    """
    Records the step-by-step table discovery trail through the orchestrator.

    At the end of query processing, build_provenance() assembles a clean
    graph_provenance dict that explains WHY each table was chosen — making
    the reasoning chain auditable and queryable.

    This addresses Stephen Chin's insight: hallucinations are compounded when
    the LLM's reasoning chain is opaque. With provenance, each table inclusion
    can be questioned: "Why did you include BSEG?" → "Because it appears in
    3 cross-module paths from LFA1 and all have high centrality scores."
    """

    def __init__(self):
        self._steps: List[TraversalStep] = []
        self._routing_tier: str = ""
        self._query: str = ""

    def start_query(self, query: str, routing_tier: str) -> None:
        self._query = query
        self._routing_tier = routing_tier
        self._steps.clear()
        logger.debug(f"[Provenance] start_query: tier={routing_tier}, query='{query[:50]}'")

    def record_step(
        self,
        step_name: str,
        tables_found: List[str],
        *,
        skipped: bool = False,
        tool: str = "",
        elapsed_ms: float = 0.0,
    ) -> None:
        """Record a retrieval step's results."""
        self._steps.append(TraversalStep(
            step_name=step_name,
            tables_found=tables_found,
            skipped=skipped,
            tool=tool,
            elapsed_ms=elapsed_ms,
        ))
        logger.debug(
            f"[Provenance] step={step_name} tables={tables_found} "
            f"skipped={skipped} elapsed={elapsed_ms:.1f}ms"
        )

    def record_skip(self, step_name: str, reason: str) -> None:
        """Record a step that was skipped by the complexity router."""
        self._steps.append(TraversalStep(
            step_name=step_name,
            tables_found=[],
            skipped=True,
            tool="",
            elapsed_ms=0.0,
        ))
        logger.debug(f"[Provenance] SKIPPED step={step_name} reason={reason}")

    def build_provenance(self) -> Dict[str, Any]:
        """
        Assemble all recorded steps into a graph_provenance dict.

        Returns:
            {
                "query": str,
                "routing_tier": str,
                "total_steps": int,
                "skipped_steps": int,
                "primary_table": str,          # First table in final tables_used
                "traversal_path": List[str],   # Ordered tables via graph traversal
                "join_reason": str,             # Human-readable join explanation
                "tables_explored": List[str],   # Union of all tables seen
                "tables_excluded": List[str],   # Tables considered but rejected
                "step_summary": List[Dict],     # Per-step breakdown
                "confidence_reason": str,       # Why this tier was chosen
                "graph_provenance_score": float  # 0-1, based on step coverage
            }
        """
        if not self._steps:
            return {}

        # Collect all tables from non-skipped steps
        all_tables: List[str] = []
        step_summaries: List[Dict[str, Any]] = []

        for step in self._steps:
            s = {
                "step": step.step_name,
                "tables": step.tables_found,
                "skipped": step.skipped,
                "tool": step.tool,
                "elapsed_ms": step.elapsed_ms,
            }
            step_summaries.append(s)

            if not step.skipped:
                for t in step.tables_found:
                    if t not in all_tables:
                        all_tables.append(t)

        # Primary table = first table from first non-skipped step
        primary = ""
        for step in self._steps:
            if not step.skipped and step.tables_found:
                primary = step.tables_found[0]
                break

        # Build traversal path (tables in order of discovery)
        # Cross-module tables discovered later in the path are more "reasoned"
        path = []
        for step in self._steps:
            if step.skipped:
                continue
            for t in step.tables_found:
                if t not in path:
                    path.append(t)

        # Tables excluded = in all_tables but not in final path
        # (populated by the caller via add_excluded)
        excluded: List[str] = []
        # join_reason: build a human-readable explanation from the path
        join_reason = ""
        if len(path) >= 2:
            join_reason = f"{path[0]} → " + " → ".join(path[1:])
        elif len(path) == 1:
            join_reason = f"Single-table query on {path[0]}"
        else:
            join_reason = "No graph traversal performed (query was TRIVIAL/SIMPLE)"

        # Score: fraction of non-skipped steps (higher = more thorough retrieval)
        non_skipped = sum(1 for s in self._steps if not s.skipped)
        total = max(len(self._steps), 1)
        provenance_score = round(non_skipped / total, 2)

        confidence_reason = (
            f"{self._routing_tier.upper()} tier — "
            f"{non_skipped}/{total} retrieval steps used"
        )

        return {
            "query": self._query,
            "routing_tier": self._routing_tier,
            "total_steps": len(self._steps),
            "skipped_steps": sum(1 for s in self._steps if s.skipped),
            "primary_table": primary,
            "traversal_path": path,
            "join_reason": join_reason,
            "tables_explored": all_tables,
            "tables_excluded": excluded,
            "step_summary": step_summaries,
            "confidence_reason": confidence_reason,
            "graph_provenance_score": provenance_score,
        }