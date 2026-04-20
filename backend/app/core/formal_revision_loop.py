"""
formal_revision_loop.py — Phase 21: Formal Revision Loop with CoT Trace
========================================================================
Enforces max_iteration discipline on the self-healing loop, generates formal
Chain-of-Thought reasoning traces for audit/compliance, and provides a
structured until/loop construct that the orchestrator can use.

Key design (inspired by V3 / Mastra / KYSM Pattern 16):
  "CoT reasoning traces missing — for SAP audit/compliance, a formal
   reasoning trace is critical."

Components:
  1. FormalRevisionLoop — context manager / loop guard
     - max_iterations cap (prevents infinite loops)
     - until(condition) predicate for early exit
     - Formal trace accumulation (CoT)
     - Convergence detection (result stabilized)

  2. CoTTracer — accumulates formal reasoning steps
     - Step-by-step: WHY this table, WHY this column, WHY this JOIN
     - Tagged with phase (schema, sql_gen, critique, heal, validation)
     - Serializable for audit trail

  3. RevisionPhase enum — categorizes each revision attempt

Usage:
    from app.core.formal_revision_loop import FormalRevisionLoop, CoTTracer, RevisionPhase

    async with FormalRevisionLoop(max_iterations=3) as loop:
        while not loop.converged():
            step = loop.begin_phase(RevisionPhase.HEAL)
            # ... do work ...
            loop.end_phase(step, evidence=["table LFA1 resolved", "JOIN ON LIFNR"])

    trace = loop.get_formal_trace()  # for audit response field
"""

from __future__ import annotations

import time
import logging
import threading
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from threading import Lock

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Revision Phase categorization
# ---------------------------------------------------------------------------

class RevisionPhase(Enum):
    """Categories of revision attempts in the loop."""
    SCHEMA_DISCOVERY = "schema_discovery"        # Table/field resolution
    SQL_GENERATION = "sql_generation"            # Initial SQL assembly
    SELF_CRITIQUE = "self_critique"             # LLM critique pass
    HEAL_ATTEMPT = "heal_attempt"               # Self-healer applied
    VALIDATION_HARNESS = "validation_harness"    # Dry-run validation
    EXECUTION = "execution"                      # SQL execution
    MASKING = "masking"                          # AuthContext masking
    FINAL = "final"                             # Converged / output


# ---------------------------------------------------------------------------
# CoT Step — formal reasoning atom
# ---------------------------------------------------------------------------

@dataclass
class CoTStep:
    """
    One atomic step in the Chain-of-Thought reasoning trace.
    Every meaningful decision in the orchestrator gets logged here.
    """
    phase: RevisionPhase
    step_id: int
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    action: str = ""              # What was done: "JOIN added", "column removed", etc.
    evidence: List[str] = field(default_factory=list)   # Facts supporting the action
    justification: str = ""      # WHY this action was chosen (rule/policy/budget)
    input_snapshot: str = ""      # Hash of input state for audit
    output_snapshot: str = ""     # Hash of output state
    confidence_delta: float = 0.0  # How much this step improved confidence
    tags: List[str] = field(default_factory=list)        # e.g. ["healing", "auto", "sap_hana"]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "step_id": self.step_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "evidence": self.evidence,
            "justification": self.justification,
            "confidence_delta": self.confidence_delta,
            "tags": self.tags,
        }


# ---------------------------------------------------------------------------
# Convergence detection
# ---------------------------------------------------------------------------

@dataclass
class ConvergenceState:
    """Tracks whether the loop has converged (result stabilized)."""
    iteration: int = 0
    last_sql_hash: str = ""
    last_result_hash: str = ""
    last_confidence: float = 0.0
    staleness_count: int = 0       # Consecutive iterations with same result
    max_staleness: int = 2        # Declare converged after 2 stable iterations


# ---------------------------------------------------------------------------
# Formal Revision Loop
# ---------------------------------------------------------------------------

class FormalRevisionLoop:
    """
    Structured until/loop construct for the orchestrator.

    Enforces:
      - max_iterations cap (safety guard against infinite loops)
      - until() predicate for early exit when convergence detected
      - Formal CoT trace accumulation for every revision step
      - Per-phase timing budget tracking

    Usage as context manager:
        async with FormalRevisionLoop(max_iterations=3) as loop:
            while not loop.converged():
                step = loop.begin_phase(RevisionPhase.HEAL)
                # ... healing work ...
                loop.end_phase(step, evidence=[...], confidence_delta=+0.05)

    Usage as generator:
        for attempt in FormalRevisionLoop(max_iterations=2):
            result = attempt.run_critique(sql)
            if attempt.converged():
                break
    """

    DEFAULT_MAX_ITERATIONS = 3      # Conservative; EXPERT queries get 5
    PHASE_BUDGET_MS = {
        RevisionPhase.SCHEMA_DISCOVERY: 2000,
        RevisionPhase.SQL_GENERATION: 1500,
        RevisionPhase.SELF_CRITIQUE: 3000,
        RevisionPhase.HEAL_ATTEMPT: 1000,
        RevisionPhase.VALIDATION_HARNESS: 2000,
        RevisionPhase.EXECUTION: 5000,
        RevisionPhase.MASKING: 500,
        RevisionPhase.FINAL: 200,
    }

    def __init__(
        self,
        max_iterations: Optional[int] = None,
        query_signature: str = "",
        enable_cot_trace: bool = True,
        convergence_threshold: float = 0.90,
    ):
        self.max_iterations = max_iterations or self.DEFAULT_MAX_ITERATIONS
        self.query_signature = query_signature
        self.enable_cot_trace = enable_cot_trace
        self.convergence_threshold = convergence_threshold

        self._lock = Lock()
        self._iterations: List[Dict[str, Any]] = []
        self._cot_trace: List[CoTStep] = []
        self._current_phase: Optional[RevisionPhase] = None
        self._phase_start: Optional[float] = None
        self._step_counter = 0
        self._converged = False
        self._convergence_state = ConvergenceState()
        self._aborted = False
        self._abortion_reason: Optional[str] = None
        self._until_predicates: List[Callable[[], bool]] = []

        # Per-phase budget tracking
        self._phase_timings: Dict[str, List[float]] = {p.value: [] for p in RevisionPhase}
        self._total_time_ms = 0.0

    # ── Context manager ─────────────────────────────────────────────────────

    def __enter__(self) -> "FormalRevisionLoop":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is not None:
            logger.warning(f"[FormalRevisionLoop] Exception during loop: {exc_val}")
            self._aborted = True
            self._abortion_reason = f"{exc_type.__name__}: {exc_val}"
        self._finalize_trace()
        return None

    # ── Iteration interface (for synchronous usage) ──────────────────────────

    def __iter__(self):
        """Allow: for attempt in FormalRevisionLoop(max_iterations=3):"""
        return self

    def __next__(self) -> "FormalRevisionLoop":
        """Returns self for each iteration; raises StopIteration when done."""
        if self._convergence_state.iteration >= self.max_iterations:
            raise StopIteration
        return self

    # ── Phase demarcation ───────────────────────────────────────────────────

    def begin_phase(self, phase: RevisionPhase) -> int:
        """
        Mark the start of a revision phase.
        Returns the step_id for this phase's first step.
        """
        with self._lock:
            self._current_phase = phase
            self._phase_start = time.perf_counter()
            self._step_counter += 1
            return self._step_counter

    def end_phase(
        self,
        step_id: int,
        action: str = "",
        evidence: Optional[List[str]] = None,
        justification: str = "",
        confidence_delta: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> None:
        """
        Record a CoT step within the current phase.

        The combination of begin_phase + end_phase creates a complete
        CoT step that gets added to the formal trace.
        """
        if not self.enable_cot_trace:
            return

        elapsed_ms = (time.perf_counter() - self._phase_start) * 1000 if self._phase_start else 0.0

        step = CoTStep(
            phase=self._current_phase or RevisionPhase.FINAL,
            step_id=step_id,
            action=action,
            evidence=evidence or [],
            justification=justification,
            confidence_delta=confidence_delta,
            tags=tags or [],
        )

        with self._lock:
            self._cot_trace.append(step)
            if self._current_phase:
                self._phase_timings[self._current_phase.value].append(elapsed_ms)

        self._current_phase = None
        self._phase_start = None

    def record_step(
        self,
        phase: RevisionPhase,
        action: str,
        evidence: Optional[List[str]] = None,
        justification: str = "",
        confidence_delta: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> int:
        """
        Record a CoT step in one call (convenience wrapper over begin_phase + end_phase).
        Returns step_id.
        """
        step_id = self.begin_phase(phase)
        self.end_phase(
            step_id,
            action=action,
            evidence=evidence,
            justification=justification,
            confidence_delta=confidence_delta,
            tags=tags,
        )
        return step_id

    # ── Convergence detection ───────────────────────────────────────────────

    def check_convergence(
        self,
        sql_hash: Optional[str] = None,
        result_hash: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> bool:
        """
        Check if the loop has converged.
        Convergence = result stabilized (same sql + same confidence trend).

        Call this after each iteration to determine whether to continue.
        """
        with self._lock:
            state = self._convergence_state

            if sql_hash:
                if sql_hash == state.last_sql_hash:
                    state.staleness_count += 1
                else:
                    state.staleness_count = 0
                state.last_sql_hash = sql_hash

            if confidence is not None:
                state.last_confidence = confidence

            # Converged if: same result for max_staleness consecutive iterations
            # OR confidence >= convergence_threshold
            if state.staleness_count >= state.max_staleness:
                self._converged = True
                logger.debug(f"[FormalRevisionLoop] Converged after {state.iteration} iterations (result stabilized)")
                return True

            if confidence is not None and confidence >= self.convergence_threshold:
                self._converged = True
                logger.debug(f"[FormalRevisionLoop] Converged after {state.iteration} iterations (confidence {confidence:.2f} >= {self.convergence_threshold})")
                return True

            return self._converged

    def converged(self) -> bool:
        """Returns True if the loop has reached convergence."""
        return self._converged

    def should_continue(self) -> bool:
        """Returns True if the loop should continue (not converged, iterations remaining)."""
        if self._converged:
            return False
        if self._convergence_state.iteration >= self.max_iterations:
            logger.debug("[FormalRevisionLoop] Max iterations reached")
            return False
        if self._aborted:
            return False
        # Check until predicates
        for pred in self._until_predicates:
            if pred():
                self._converged = True
                return False
        return True

    def record_iteration(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Record that one iteration completed."""
        with self._lock:
            self._convergence_state.iteration += 1
            self._iterations.append({
                "iteration": self._convergence_state.iteration,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "metadata": metadata or {},
            })

    # ── Until predicates ────────────────────────────────────────────────────

    def add_until(self, predicate: Callable[[], bool]) -> None:
        """Add an until() predicate — loop exits when predicate returns True."""
        self._until_predicates.append(predicate)

    def until_confidence(self, threshold: float) -> "FormalRevisionLoop":
        """Add until-confidence predicate: exit when confidence >= threshold."""
        self.add_until(lambda: self._convergence_state.last_confidence >= threshold)
        return self

    def until_result_stable(self, stable_count: int = 2) -> "FormalRevisionLoop":
        """Add until-stable predicate: exit when result unchanged for stable_count iterations."""
        self._convergence_state.max_staleness = stable_count
        return self

    # ── CoT Trace API ───────────────────────────────────────────────────────

    def get_formal_trace(self) -> List[Dict[str, Any]]:
        """
        Return the full formal CoT trace as a list of dicts.
        This is what gets stored in result['formal_trace'] for audit/compliance.
        """
        with self._lock:
            return [step.to_dict() for step in self._cot_trace]

    def get_summary(self) -> Dict[str, Any]:
        """Human-readable summary of the revision loop."""
        with self._lock:
            phase_counts: Dict[str, int] = {}
            for step in self._cot_trace:
                phase_counts[step.phase.value] = phase_counts.get(step.phase.value, 0) + 1

            total_time = sum(sum(timings) for timings in self._phase_timings.values())

            return {
                "total_iterations": self._convergence_state.iteration,
                "max_iterations": self.max_iterations,
                "converged": self._converged,
                "aborted": self._aborted,
                "abortion_reason": self._abortion_reason,
                "total_cot_steps": len(self._cot_trace),
                "phase_distribution": phase_counts,
                "phase_timings_ms": {
                    phase: round(sum(timings), 2)
                    for phase, timings in self._phase_timings.items()
                    if timings
                },
                "total_time_ms": round(total_time, 2),
                "convergence_confidence": self._convergence_state.last_confidence,
                "convergence_staleness": self._convergence_state.staleness_count,
            }

    def _finalize_trace(self) -> None:
        """Add final convergence step to trace."""
        if self._converged and not self._aborted:
            self.record_step(
                phase=RevisionPhase.FINAL,
                action=f"Converged after {self._convergence_state.iteration} iteration(s)",
                evidence=[
                    f"confidence={self._convergence_state.last_confidence:.3f}",
                    f"steps={len(self._cot_trace)}",
                ],
                justification="Result stabilized or confidence threshold met",
                tags=["converged"],
            )

    # ── Phase budget checking ──────────────────────────────────────────────

    def check_phase_budget(self, phase: RevisionPhase) -> bool:
        """
        Returns True if phase is within budget.
        Call at begin_phase to enforce per-phase time budgets.
        """
        if self._phase_start is None:
            return True  # No active phase

        elapsed_ms = (time.perf_counter() - self._phase_start) * 1000
        budget = self.PHASE_BUDGET_MS.get(phase, 1000)
        return elapsed_ms <= budget

    def get_phase_timing_report(self) -> str:
        """Human-readable phase timing report."""
        lines = ["[FormalRevisionLoop] Phase Timing Report", "=" * 50]
        summary = self.get_summary()
        for phase, total_ms in summary.get("phase_timings_ms", {}).items():
            budget = self.PHASE_BUDGET_MS.get(RevisionPhase(phase), 0)
            status = "OK" if total_ms <= budget else "OVER"
            lines.append(f"  {phase:30} {total_ms:8.2f}ms / {budget:.0f}ms [{status}]")
        lines.append(f"  Total: {summary['total_time_ms']:.2f}ms")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# CoT Tracer — standalone tracer for sub-components
# ---------------------------------------------------------------------------

class CoTTracer:
    """
    Lightweight Chain-of-Thought tracer for use inside DomainAgents,
    synthesis agents, and other sub-components.

    Unlike FormalRevisionLoop (which is orchestrator-level), CoTTracer
    can be instantiated per-agent to track local reasoning.

    Usage:
        tracer = CoTTracer(agent_id="pur_agent", query_id="q-123")
        tracer.add_step("schema_lookup", "LFA1 selected as anchor",
                        justification="LFA1 is hub node for vendor domain with highest degree centrality")
    """

    def __init__(
        self,
        agent_id: str = "",
        query_id: str = "",
        session_id: str = "",
    ):
        self.agent_id = agent_id
        self.query_id = query_id
        self.session_id = session_id
        self._steps: List[CoTStep] = []
        self._lock = Lock()

    def add_step(
        self,
        phase: RevisionPhase,
        action: str,
        evidence: Optional[List[str]] = None,
        justification: str = "",
        confidence_delta: float = 0.0,
        tags: Optional[List[str]] = None,
    ) -> int:
        """Add a CoT step. Returns step_id."""
        with self._lock:
            self._steps.append(CoTStep(
                phase=phase,
                step_id=len(self._steps) + 1,
                action=action,
                evidence=evidence or [],
                justification=justification,
                confidence_delta=confidence_delta,
                tags=tags or [],
            ))
            return len(self._steps)

    def get_trace(self) -> List[Dict[str, Any]]:
        """Return all steps as list of dicts."""
        with self._lock:
            return [s.to_dict() for s in self._steps]

    def merge(self, other: "CoTTracer") -> None:
        """Merge another tracer's steps into this one (for synthesis agents)."""
        with self._lock:
            for step in other._steps:
                step.step_id = len(self._steps) + 1
                self._steps.append(step)

    def to_formal_trace(self) -> List[Dict[str, Any]]:
        """Alias for get_trace() for API compatibility."""
        return self.get_trace()


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_revision_loop(
    query_signature: str,
    max_iterations: int = 3,
    enable_cot_trace: bool = True,
    convergence_threshold: float = 0.90,
) -> FormalRevisionLoop:
    """Factory for creating a properly configured FormalRevisionLoop."""
    return FormalRevisionLoop(
        max_iterations=max_iterations,
        query_signature=query_signature,
        enable_cot_trace=enable_cot_trace,
        convergence_threshold=convergence_threshold,
    )