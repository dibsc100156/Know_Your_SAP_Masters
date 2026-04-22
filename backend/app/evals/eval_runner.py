from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.evals.golden_types import GoldenSet


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"case_id": self.case_id, "passed": self.passed, "reasons": self.reasons}


@dataclass
class EvalRun:
    golden_set: str
    scope: List[str]
    results: List[EvalResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if not self.results:
            return 1.0
        return sum(1 for result in self.results if result.passed) / len(self.results)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "golden_set": self.golden_set,
            "scope": self.scope,
            "pass_rate": self.pass_rate,
            "results": [result.to_dict() for result in self.results],
        }


class EvalRunner:
    def run_golden_set(self, golden_set: GoldenSet, scope: List[str], observed: Dict[str, Any]) -> EvalRun:
        results: List[EvalResult] = []
        domain = observed.get("domain")
        for case in golden_set.cases:
            if not case.matches_scope(scope, domain):
                continue
            reasons: List[str] = []
            passed = True
            confidence = float(observed.get("confidence", 0.0) or 0.0)
            tables_used = list(observed.get("tables_used", []) or [])
            masked_fields = list(observed.get("masked_fields", []) or [])
            routing_path = observed.get("routing_path")

            if confidence < case.expected.min_confidence:
                passed = False
                reasons.append(f"confidence {confidence:.3f} < {case.expected.min_confidence:.3f}")
            missing_tables = [tbl for tbl in case.expected.required_tables if tbl not in tables_used]
            if missing_tables:
                passed = False
                reasons.append(f"missing tables: {missing_tables}")
            missing_masks = [fld for fld in case.expected.required_masked_fields if fld not in masked_fields]
            if missing_masks:
                passed = False
                reasons.append(f"missing masked fields: {missing_masks}")
            if case.expected.required_routing_path and routing_path != case.expected.required_routing_path:
                passed = False
                reasons.append(f"routing path {routing_path!r} != {case.expected.required_routing_path!r}")
            if passed:
                reasons.append("passed")
            results.append(EvalResult(case_id=case.case_id, passed=passed, reasons=reasons))
        return EvalRun(golden_set=golden_set.name, scope=scope, results=results)
