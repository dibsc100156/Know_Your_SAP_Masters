from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from app.evals.eval_runner import EvalRun


@dataclass
class GateThreshold:
    min_pass_rate: float = 0.8
    warn_pass_rate: float = 1.0


@dataclass
class RegressionVerdict:
    status: str
    pass_rate: float
    reasons: list[str]

    def to_dict(self) -> Dict:
        return {"status": self.status, "pass_rate": self.pass_rate, "reasons": self.reasons}


class RegressionGate:
    def evaluate_regression_gate(self, eval_run: EvalRun, policy: GateThreshold | None = None) -> RegressionVerdict:
        thresholds = policy or GateThreshold()
        pass_rate = eval_run.pass_rate
        if pass_rate < thresholds.min_pass_rate:
            return RegressionVerdict(status="block", pass_rate=pass_rate, reasons=["golden-set regression below minimum threshold"])
        if pass_rate < thresholds.warn_pass_rate:
            return RegressionVerdict(status="warn", pass_rate=pass_rate, reasons=["golden-set regression below perfect pass rate"])
        return RegressionVerdict(status="pass", pass_rate=pass_rate, reasons=["golden-set regression passed"])
