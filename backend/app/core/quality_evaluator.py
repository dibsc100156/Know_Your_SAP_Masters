from typing import Dict, List
from app.core.harness_runs import HarnessRun, PhaseState

class QualityEvaluator:
    """
    Computes Quality Metrics (correctness_score, trajectory_adherence)
    by running evaluations against the stored trace data of a HarnessRun.
    """

    @staticmethod
    def evaluate_run(run: HarnessRun) -> Dict[str, float]:
        if not run:
            return {"correctness_score": 0.0, "trajectory_adherence": 0.0}
        
        adherence = QualityEvaluator._compute_trajectory_adherence(run.phase_states)
        correctness = QualityEvaluator._compute_correctness_score(run)
        
        return {
            "correctness_score": round(correctness, 2),
            "trajectory_adherence": round(adherence, 2)
        }

    @staticmethod
    def _compute_trajectory_adherence(phases: List[PhaseState]) -> float:
        if not phases:
            return 0.0
        
        score = 1.0
        
        for phase in phases:
            if phase.status == "failed":
                score -= 0.15
            if phase.validator_fired:
                score -= 0.10
            if phase.error and not phase.validator_fired:
                score -= 0.2
                
        # Sequence adherence penalty for out-of-order execution
        phase_order = {
            "phase_1": 1, "phase_1_5": 1.5, "phase_2": 2, "phase_2b": 2.2, 
            "phase_3": 3, "phase_4": 4, "phase_4_5": 4.5, "phase_5": 5, 
            "phase_5_5": 5.5, "phase_6": 6, "phase_7": 7, "phase_8": 8
        }
        
        last_num = -1.0
        for p in phases:
            # map keys like "phase_1.5" to "phase_1_5" just in case
            safe_phase = p.phase.replace(".", "_")
            if safe_phase in phase_order:
                current_num = phase_order[safe_phase]
                if current_num < last_num:
                    score -= 0.2 # Backtracking penalty
                last_num = current_num

        return max(0.0, min(1.0, score))

    @staticmethod
    def _compute_correctness_score(run: HarnessRun) -> float:
        if run.status == "failed":
            return 0.0
            
        base_score = float(run.confidence_score) if run.confidence_score else 0.8
        
        # Penalties based on final phase outcomes
        if not run.phase_states:
            return 0.0
            
        last_phase = run.phase_states[-1]
        if last_phase.status != "completed":
            base_score -= 0.4
            
        # Check sentinel blocks in artifacts or errors
        for p in run.phase_states:
            if p.phase == "sentinel" and p.status == "failed":
                base_score -= 0.8
            if "sentinel" in p.phase.lower() and p.error:
                base_score -= 0.8
                
        return max(0.0, min(1.0, base_score))
