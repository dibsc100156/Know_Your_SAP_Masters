from typing import Dict, List

from app.core.harness_runs import HarnessRun, PhaseState


class QualityEvaluator:
    """
    Computes Quality Metrics (correctness_score, trajectory_adherence)
    from both persisted phase states and the structured trajectory log.
    """

    EXPECTED_TRAJECTORY_ORDER = [
        "phase_0_meta_path",
        "phase_1_schema_rag",
        "phase_18_exploration",
        "phase_1_5_graph_discovery",
        "phase_2_sql_pattern",
        "phase_4_5_self_critique",
        "phase_5_5_validation_harness",
        "phase_6_execution",
        "phase_8_finalization",
    ]

    @staticmethod
    def evaluate_run(run: HarnessRun) -> Dict[str, float]:
        if not run:
            return {
                "correctness_score": 0.0,
                "trajectory_adherence": 0.0,
                "phase_coverage": 0.0,
                "trajectory_event_count": 0.0,
            }

        adherence = QualityEvaluator._compute_trajectory_adherence(run)
        correctness = QualityEvaluator._compute_correctness_score(run)
        phase_coverage = QualityEvaluator._compute_phase_coverage(run.phase_states)
        trajectory_event_count = float(len(run.trajectory_log or []))

        return {
            "correctness_score": round(correctness, 2),
            "trajectory_adherence": round(adherence, 2),
            "phase_coverage": round(phase_coverage, 2),
            "trajectory_event_count": trajectory_event_count,
        }

    @staticmethod
    def _compute_trajectory_adherence(run: HarnessRun) -> float:
        score = 1.0
        phases = run.phase_states or []
        events = run.trajectory_log or []

        for phase in phases:
            if phase.status == "failed":
                score -= 0.12
            if phase.validator_fired:
                score -= 0.08
            if phase.error and not phase.validator_fired:
                score -= 0.15

        last_idx = -1
        for event in events:
            step = event.get("step", "")
            if step in QualityEvaluator.EXPECTED_TRAJECTORY_ORDER:
                idx = QualityEvaluator.EXPECTED_TRAJECTORY_ORDER.index(step)
                if idx < last_idx:
                    score -= 0.12
                last_idx = max(last_idx, idx)
            decision = str(event.get("decision", "")).lower()
            if decision in {"fail", "error"}:
                score -= 0.08
            elif decision == "skip":
                score -= 0.03

        coverage = QualityEvaluator._compute_phase_coverage(phases)
        if events:
            matched = sum(1 for e in events if e.get("step") in QualityEvaluator.EXPECTED_TRAJECTORY_ORDER)
            coverage = max(coverage, matched / len(QualityEvaluator.EXPECTED_TRAJECTORY_ORDER))

        score = (score * 0.75) + (coverage * 0.25)
        return max(0.0, min(1.0, score))

    @staticmethod
    def _compute_phase_coverage(phases: List[PhaseState]) -> float:
        if not phases:
            return 0.0
        completed = sum(1 for p in phases if p.status in {"completed", "skipped"})
        return max(0.0, min(1.0, completed / 8.0))

    @staticmethod
    def _compute_correctness_score(run: HarnessRun) -> float:
        if run.status == "failed":
            return 0.0

        base_score = float(run.confidence_score) if run.confidence_score else 0.8
        events = run.trajectory_log or []
        phases = run.phase_states or []

        if not phases and not events:
            return 0.0

        if phases:
            last_phase = phases[-1]
            if last_phase.status not in {"completed", "skipped"}:
                base_score -= 0.25

        for phase in phases:
            if "sentinel" in phase.phase.lower() and (phase.status == "failed" or phase.error):
                base_score -= 0.5
            if phase.validator_fired:
                base_score -= 0.05

        for event in events:
            decision = str(event.get("decision", "")).lower()
            if decision in {"fail", "error"}:
                base_score -= 0.06
            if event.get("step") == "phase_8_finalization" and decision == "success":
                base_score += 0.03

        return max(0.0, min(1.0, base_score))
