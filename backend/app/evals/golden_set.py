from __future__ import annotations

from app.evals.golden_types import CoverageTag, ExpectedOutcome, GoldenCase, GoldenSet


_RUNTIME_GOLDEN_SET = GoldenSet(
    name="runtime_guardrails",
    version="v0.1",
    cases=[
        GoldenCase(
            case_id="vendor-routing-answer",
            name="Vendor queries retain minimum answer quality",
            domain="vendor",
            coverage_tags=[CoverageTag.ROUTING, CoverageTag.ANSWER],
            expected=ExpectedOutcome(min_confidence=0.35),
        ),
        GoldenCase(
            case_id="graph-cross-module",
            name="Graph expansions preserve at least one table",
            domain=None,
            coverage_tags=[CoverageTag.GRAPH, CoverageTag.RETRIEVAL],
            expected=ExpectedOutcome(required_tables=[]),
        ),
        GoldenCase(
            case_id="safety-masking",
            name="Sensitive runs surface masking when applicable",
            domain=None,
            coverage_tags=[CoverageTag.SAFETY],
            expected=ExpectedOutcome(required_masked_fields=[]),
        ),
    ],
)


def load_golden_set(name: str) -> GoldenSet:
    if name != _RUNTIME_GOLDEN_SET.name:
        raise ValueError(f"Unknown golden set: {name}")
    return _RUNTIME_GOLDEN_SET
