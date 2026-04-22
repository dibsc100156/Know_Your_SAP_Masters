from __future__ import annotations

from typing import Any, Dict

from app.evals.eval_runner import EvalRun
from app.evals.regression_gate import RegressionVerdict


def to_eval_gate_summary(eval_run: EvalRun, verdict: RegressionVerdict) -> Dict[str, Any]:
    return {
        "golden_set": eval_run.golden_set,
        "scope": eval_run.scope,
        "result_count": len(eval_run.results),
        "pass_rate": eval_run.pass_rate,
        "verdict": verdict.status,
        "reasons": verdict.reasons,
    }
