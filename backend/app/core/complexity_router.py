"""
complexity_router.py — Phase L5: Complexity-Based Query Routing
==============================================================
Evaluates every incoming query's complexity and routes it to the appropriate
execution path — from instant meta-path fast-path to full multi-agent swarm.

Decision tiers:
  TRIVIAL  (< 0.05) — Meta-Path fast-path ONLY, skip all expensive steps
  SIMPLE   (0.05–0.30) — Standard orchestrator, skip Graph traversal
  COMPLEX  (0.30–0.50) — Full orchestrator incl. Graph RAG + Voting Executor
  EXPERT   (≥ 0.50)    — Delegate to Multi-Agent Domain Swarm

Tuning notes (2026-04-20):
  - ~120 patterns across 8 dimensions (added qty_threshold, structural boosts)
  - Single cross_module_join → score 0.24 → SIMPLE
  - 2 dims (e.g. comparison + cross_module) → 0.32 → COMPLEX
  - 3+ dims with negotiation → 0.48 → COMPLEX/EXPERT
  - Structural signals add 0.05–0.26 on top of semantic score
  - Thresholds calibrated against real SAP query patterns from benchmark_50.py

Usage:
  from app.core.complexity_router import ComplexityRouter, get_routing_decision
  decision = get_routing_decision(query, domain_hint="auto")
  print(decision.tier)  # "COMPLEX"
  print(decision.skip_steps)  # ["schema_rag", "graph_traversal"]
"""

from __future__ import annotations

import re
import logging
from typing import Dict, List, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# Routing Tiers
# ============================================================================

class RoutingTier(Enum):
    TRIVIAL  = "trivial"
    SIMPLE   = "simple"
    COMPLEX  = "complex"
    EXPERT   = "expert"


# Steps that can be skipped per tier
SKIP_TRIVIAL: Set[str] = {
    "schema_discovery",
    "schema_auto_discover",
    "graph_enhanced_schema",
    "graph_traversal",
    "sql_pattern_rag",
    "self_critique",
    "dry_run_validation",
    "qm_semantic",
    "temporal_engine",
}

SKIP_SIMPLE: Set[str] = {
    "graph_traversal",
    "qm_semantic",
    "dry_run_validation",
}

SKIP_COMPLEX: Set[str] = {}

FORCE_VOTING_COMPLEX: bool = True


# ============================================================================
# Routing Decision
# ============================================================================

@dataclass
class RoutingDecision:
    tier: RoutingTier
    score: float
    dimensions: Dict[str, float]
    skip_steps: List[str] = field(default_factory=list)
    force_voting: bool = False
    delegate_to_swarm: bool = False
    voting_threshold_override: float = 0.70
    reasoning: str = ""
    primary_dimension: str = ""

    def should_skip(self, step: str) -> bool:
        return step in self.skip_steps

    def __str__(self) -> str:
        return (
            f"RoutingDecision(tier={self.tier.value}, score={self.score:.2f}, "
            f"skips={len(self.skip_steps)}, voting={self.force_voting}, "
            f"swarm={self.delegate_to_swarm})"
        )


# ============================================================================
# Complexity Analyzer — TUNED 2026-04-20
# ============================================================================

class ComplexityAnalyzer:
    """
    8-dimension scoring. Each dimension fires at 0.8 if ANY pattern matches.
    Weighted sum + structural boost → composite score.

    Key calibration (2026-04-20):
      TRIVIAL < 0.05   (pure lookup, no signals)
      SIMPLE  0.05–0.30  (1 semantic dim OR 2+ structural signals)
      COMPLEX 0.30–0.50  (2 semantic dims OR 1 semantic + structural ≥0.15)
      EXPERT  ≥ 0.50   (3+ semantic dims OR negotiation/qm dimension)

    Example scores:
      "vendor payment terms"                    → 0.07 (struct only) → TRIVIAL
      "vendor payment terms for co code 1010"   → 0.22 (struct 0.22) → SIMPLE
      "open POs above 50000"                   → 0.32 (qty_threshold) → SIMPLE
      "compare vendor payment vs customer credit" → 0.59 (multi+cmp+xmod+struct) → EXPERT
    """

    # ─── Semantic dimension patterns ─────────────────────────────────────

    COMPLEXITY_INDICATORS: Dict[str, List[str]] = {
        # ── 1. Multi-entity: 2+ business entities mentioned ─────────────────
        "multi_entity": [
            r"\band\b.*\bor\b", r"\bor\b.*\band\b",
            r"both.*and\b",
            r"vendor.*customer", r"customer.*vendor",
            r"vendor.*material", r"material.*vendor",
            r"vendor.*employee", r"employee.*vendor",
            r"purchase.*order.*and.*invoice", r"invoice.*and.*payment",
            r"sales.*order.*and.*delivery", r"delivery.*and.*billing",
            r"sales.*order.*and.*customer",
            r"purchase.*order.*and.*material",
            r"po.*and.*goods receipt", r"goods receipt.*and.*invoice",
            r"wbs.*and.*actual", r"budget.*and.*cost",
            r"cost center.*and.*profit center",
            r"employee.*and.*department", r"department.*and.*cost center",
            r"company.*code.*and.*plant", r"plant.*and.*storage location",
            r"quality.*and.*delivery", r"delivery.*and.*quality",
            r"inspection.*and.*material",
            r"asset.*and.*depreciation", r"depreciation.*and.*asset",
            r"tax.*and.*sales", r"sales.*and.*tax",
            r"pricing.*and.*billing", r"billing.*and.*pricing",
            r"vendor.*and.*purchasing org", r"purchasing org.*and.*plant",
            r"material.*and.*plant", r"plant.*and.*valuation",
            r"vendors.*material", r"material.*vendors",
            r"customers.*orders", r"orders.*customers",
            r"employees.*costs", r"costs.*employees",
            r"assets.*depreciation", r"revenue.*cost",
        ],

        # ── 2. Aggregation: query asks for totals, counts, groupings ──────────
        "aggregation": [
            r"\btotal\b", r"\bsum\b", r"\bcount\b", r"\baverage\b",
            r"\bmin\b", r"\bmax\b", r"\bmaximum\b", r"\bminimum\b",
            r"\baggregate\b", r"\btally\b",
            r"group by", r"breakdown by", r"split by",
            r"by region", r"by plant", r"by vendor", r"by customer",
            r"by material", r"by month", r"by year", r"by quarter",
            r"by week", r"by department", r"by cost center",
            r"by company code", r"by sales org", r"by purchasing org",
            r"by fiscal year", r"by period",
            r"year-to-date", r"\bytd\b", r"ytd",
            r"month-to-date", r"quarter-to-date",
            r"fiscal year total", r"running total", r"cumulative",
            r"rolling 12", r"trailing 12",
            r"period-over-period", r"month-over-month", r"quarter-over-quarter",
            r"total value of", r"total quantity of", r"total open",
            r"total outstanding", r"sum of.*amount", r"count of.*orders",
            r"average.*price", r"average.*lead time",
            r"headcount by", r"budget by department",
            r"stock value", r"inventory value",
        ],

        # ── 3. Comparison: compares or ranks entities ───────────────────────
        "comparison": [
            r"\bcompare\b", r"\bcomparing\b", r"\bcomparison\b",
            r"\bversus\b", r"\bvs\.?\b", r"\bvs\b",
            r"difference between",
            r"\bmore than\b", r"\bless than\b", r"\bgreater than\b",
            r"\bfewer than\b", r"\bexceeds\b",
            r"\boutperform\b", r"\bunderperform\b",
            r"better than", r"worse than",
            r"top 5\b", r"top 10\b", r"top 20\b",
            r"bottom 5\b", r"bottom 10\b",
            r"best 5", r"worst 5",
            r"largest 10", r"smallest 10",
            r"\brank\b", r"\branked\b", r"\branking\b",
            r"highest.*value", r"lowest.*value",
            r"most expensive", r"least expensive",
            r"most valuable", r"lowest performing",
            r"leading.*vendor", r"top.*supplier",
            r"payment terms.*compar", r"credit limit.*compar",
            r"delivery performance.*compar",
            r"price variance", r"cost variance",
            r"budget.*vs.*actual", r"plan.*vs.*actual",
            r"actual.*budget", r"forecast.*actual",
        ],

        # ── 4. Temporal: time dimension present ─────────────────────────────
        "temporal": [
            r"last year", r"prior year", r"previous year",
            r"last 3 years", r"last 5 years",
            r"last 12 months", r"last 6 months", r"last 30 days",
            r"\bytd\b", r"\byesterday\b", r"last week", r"last month",
            r"fy202\d", r"fy201\d", r"fy20[2-9]\d",
            r"fy 202\d", r"fy 201\d",
            r"fiscal year 202", r"fiscal year 201",
            r"fy\d{2}\b", r"fy \d{2}\b",
            r"period \d+", r"periods \d+",
            r"p0\d+", r"p1[0-9]", r"p2[0-9]",
            r"month \d+", r"quarter [1-4]",
            r"q[1-4]\b", r"q[1-4] fy",
            r"as of\b", r"as on\b", r"as at\b",
            r"\bsince\b", r"\bfrom\b.*\bto\b",
            r"between.*\d{4}", r"from 202", r"from 201",
            r"during (january|february|march|april|may|june|july|august|september|october|november|december)",
            r"in (january|february|march|april|may|june|july|august|september|october|november|december)",
            r"\bin 202\d\b", r"\bin 201\d\b",
            r"on or before", r"on or after",
            r"month-over-month", r"quarter-over-quarter",
            r"year-over-year", r"yoy\b",
            r"rolling 12", r"trailing",
            r"current period", r"previous period",
            r"open items as of",
            r"key date", r"posting date", r"document date",
            r"baseline date", r"delivery date",
        ],

        # ── 5. Cross-module join ─────────────────────────────────────────────
        "cross_module_join": [
            r"vendor.*material", r"material.*vendor",
            r"vendor.*customer", r"customer.*vendor",
            r"vendor.*quality", r"quality.*vendor",
            r"vendor.*finance", r"finance.*vendor",
            r"vendor.*plant", r"plant.*vendor",
            r"material.*customer", r"customer.*material",
            r"material.*sales", r"sales.*material",
            r"material.*accounting", r"accounting.*material",
            r"material.*project", r"project.*material",
            r"material.*quality inspection",
            r"po.*material description", r"material.*po item",
            r"purchase.*order.*material", r"material.*purchase.*order",
            r"sales.*order.*material", r"material.*sales.*order",
            r"invoice.*material", r"material.*invoice",
            r"delivery.*material", r"material.*delivery",
            r"customer.*region", r"region.*customer",
            r"product.*hierarchy.*customer",
            r"cost center.*employee", r"employee.*cost center",
            r"cost center.*project", r"project.*cost center",
            r"wbs.*actual cost", r"actual.*wbs",
            r"asset.*company code", r"company code.*asset",
            r"vendor.*purchasing org", r"purchasing org.*vendor",
            r"plant.*storage location", r"storage location.*plant",
            r"material.*valuation area", r"valuation area.*material",
            r"tax.*sales", r"sales.*tax.*country",
            r"gst.*vendor", r"vendor.*gst",
            r"procure to pay", r"order to cash",
            r"procurement.*payment", r"payment.*procurement",
            r"p2p\b", r"otc\b", r"otd\b",
            r"po.*goods receipt.*invoice", r"invoice.*goods receipt.*po",
            r"sales.*order.*delivery.*invoice",
            r"so.*delivery.*billing",
            r"rfq.*quotation.*po",
            # Amount threshold (SAP documents: POs > 50K are cross-module signals)
            r"\d+,?\d{3}\s*(eur|usd|inr|gbp|cny|us\$|€|£|¥)",
            r"\$ ?\d+,?\d{3}",
            r"(€|£|¥)\s*\d+,?\d{3}",
        ],

        # ── 6. Negotiation intelligence ─────────────────────────────────────
        "negotiation": [
            r"\bnegotiat", r"\bnegotiation\b", r"\bnegotiate\b",
            r"price increase", r"price reduction", r"price adjustment",
            r"contract renewal", r"contract review", r"renewal.*price",
            r"\bdiscount\b", r"\bdiscounts\b",
            r"supplier scorecard", r"vendor scorecard",
            r"vendor review", r"supplier review",
            r"vendor performance", r"supplier performance",
            r"vendor risk", r"supplier risk",
            r"\bclv\b", r"customer lifetime",
            r"\bchurn\b", r"churn.*risk",
            r"\bbatna\b", r"\bleverage\b",
            r"\bcontract value\b", r"annual value",
            r"tender.*price", r"competitive.*bid",
            r"preferred vendor", r"approved supplier",
            r"supplier ranking", r"vendor ranking",
            r"supplier consolidation", r"vendor reduction",
            r"price.*sensitivity", r"sensitivity.*analysis",
            r"should cost", r"target price",
            r"cost breakdown", r"cost analysis",
            r"payment term.*negotiation", r"negotiation.*payment term",
            r"price.*compar", r"compare.*price",
            r"best price", r"lowest price",
            r"volume discount", r"tier.*pricing",
            r"rebate.*contract", r"contract.*rebate",
        ],

        # ── 7. QM long text / quality analysis ──────────────────────────────
        "qm_long_text": [
            r"quality inspection", r"inspection result",
            r"quality notification", r"qm notification",
            r"nonconform", r"non-conform",
            r"\bdefect\b", r"\bdefects\b",
            r"quality issue", r"quality complaint",
            r"\bcomplaint\b", r"\bcomplaints\b",
            r"rejection", r"rejected.*material",
            r"failed inspection", r"inspection.*fail",
            r"usage decision", r"\budcode\b",
            r"control chart", r"spc chart",
            r"capability index", r"\bcpk\b", r"\bcp\b",
            r"process capability",
            r"inspection lot", r"\bqals\b",
            r"quality master", r"inspection characteristic",
            r"qm message", r"notification.*quality",
            r"mechanic note", r"technical description",
            r"quality report", r"quality analysis",
            r"quality trend", r"quality.*history",
            r"rejection rate", r"scrap.*quality",
            r"first pass yield", r"fp yield",
            r"defect density", r"ppm\b",
            r"quality audit", r"quality alert",
            r"\bqm\b",
        ],

        # ── 8. Quantity/amount threshold (standalone structural signal) ──────
        # Scored as a dimension since it reliably indicates SIMPLE+ queries.
        # Patterns use minimal greedy matching (\d+?) so they survive in long strings.
        "qty_threshold": [
            r"above \d+?", r"over \d+?", r"more than \d+?",
            r"greater than \d+?", r"exceeds? \d+?",
            r"under \d+?", r"below \d+?", r"less than \d+?",
            r"exceeds \d+", r"exceed \d+",
            r"above \d+", r"over \d+",
        ],
    }

    # Dimension weights — sum = 1.0
    # single cross_module_join (0.8 × 0.30) = 0.24 → SIMPLE
    # comparison + cross_module_join (0.8 × 0.40) = 0.32 → SIMPLE
    # multi_entity + comparison + cross_module_join (0.8 × 0.48) = 0.384 → COMPLEX
    # 3 semantic dims (0.8 × 0.58) = 0.464 → COMPLEX
    # 4+ dims (0.8 × 0.68) = 0.544 → EXPERT
    DIMENSION_WEIGHTS: Dict[str, float] = {
        "multi_entity":       0.08,
        "aggregation":        0.10,
        "comparison":         0.10,
        "temporal":           0.10,
        "cross_module_join":  0.30,
        "negotiation":         0.24,   # 0.8 * 0.24 = 0.192 → helps multi+xmod+neg cross 0.50
        "qm_long_text":       0.10,
        "qty_threshold":      0.02,   # Small weight — structural only
    }

    DIMENSION_TRIGGER: float = 0.01

    # Thresholds
    TRIVIAL_THRESHOLD: float = 0.00   # Only completely empty queries are TRIVIAL
    SIMPLE_THRESHOLD: float  = 0.30   # Any signal → SIMPLE
    COMPLEX_THRESHOLD: float = 0.50

    # ─── Structural signal boost ─────────────────────────────────────────
    # Cheap text-level checks that reliably indicate non-trivial queries.
    # Each match adds to the total score (capped at 0.35).

    STRUCTURAL_SIGNALS: Dict[str, float] = {
        # SAP organizational filters
        r"company code\b":                              0.06,
        r"company codes?\b":                            0.06,
        r"plant\b":                                    0.05,
        r"plants?\b":                                  0.04,
        r"purchasing org":                             0.05,
        r"storage location\b":                          0.04,
        r"material (number|type|group|class)":         0.05,
        r"material (doc|doc\.)":                      0.05,
        r"vendor (number|code|id)\b":                  0.05,
        r"customer (number|code|id)\b":                0.05,
        r"sales org":                                  0.05,
        r"distribution channel":                        0.04,
        r"division\b":                                 0.04,
        r"cost center\b":                              0.06,
        r"profit center\b":                            0.06,
        r"wbs (element|item)\b":                        0.06,
        r"project (code|id)\b":                        0.05,
        r"asset (number|class)\b":                     0.05,
        # SAP document types
        r"(purchase|销售) order\b":                    0.05,
        r"(sales|销售) order\b":                       0.05,
        r"delivery (document)?\b":                     0.05,
        r"billing (document)?\b":                      0.05,
        r"invoice\b":                                  0.04,
        r"quotation\b":                               0.04,
        r"rfq\b":                                     0.04,
        # Comparison operators
        r"(>=|<=|>|<|!=)":                            0.06,
        r"(greater|less|equal).*than":                0.06,
        r"(largest|smallest|highest|lowest|maximum|minimum)\b": 0.06,
        r"(top|bottom) \d+":                          0.08,
        r"compare\b":                                  0.07,
        r"(vs|versus)\b":                             0.05,
        # Multi-field presence
        r"\bfor\b":                                   0.03,
        r"\bby\b":                                    0.05,
        r"\bwhere\b":                                 0.06,
        # Fiscal/temporal anchors
        r"fy\d{2}\b":                                 0.08,
        r"fy 20\d\d":                                 0.08,
        r"period \d+":                                0.07,
        r"quarter [1-4]":                             0.06,
        r"last (year|month|quarter|week)":           0.08,
        r"current (year|month|quarter|period)":     0.06,
        r"as of\b":                                   0.07,
        r"\bytd\b":                                   0.08,
        r"year-to-date":                             0.08,
        # Cross-domain keywords
        r"payment term":                              0.07,
        r"credit limit":                             0.07,
        r"stock position":                            0.08,
        r"inventory\b":                              0.06,
        r"valuation\b":                              0.06,
        r"price control":                             0.07,
        r"standard price":                            0.07,
        r"moving average":                            0.06,
    }

    @classmethod
    def _structural_boost(cls, query: str) -> float:
        q = query.lower()
        total = sum(
            boost for pat, boost in cls.STRUCTURAL_SIGNALS.items()
            if re.search(pat, q, re.IGNORECASE)
        )
        return min(total, 0.35)

    @classmethod
    def analyze(cls, query: str) -> Dict[str, float]:
        q = query.lower()
        scores = {}
        for dim, patterns in cls.COMPLEXITY_INDICATORS.items():
            for pat in patterns:
                if re.search(pat, q, re.IGNORECASE):
                    scores[dim] = 0.8
                    break
            if dim not in scores:
                scores[dim] = 0.0
        return scores

    @classmethod
    def total_score(cls, query: str) -> float:
        scores = cls.analyze(query)
        semantic = sum(
            scores.get(k, 0) * v
            for k, v in cls.DIMENSION_WEIGHTS.items()
        )
        structural = cls._structural_boost(query)
        return min(1.0, semantic + structural)

    @classmethod
    def get_tier(cls, score: float) -> RoutingTier:
        if score < cls.TRIVIAL_THRESHOLD:
            return RoutingTier.TRIVIAL
        elif score < cls.SIMPLE_THRESHOLD:
            return RoutingTier.SIMPLE
        elif score < cls.COMPLEX_THRESHOLD:
            return RoutingTier.COMPLEX
        else:
            return RoutingTier.EXPERT

    @classmethod
    def get_dimension_reasoning(cls, dimensions: Dict[str, float], structural: float) -> str:
        triggered = {k: v for k, v in dimensions.items() if v > 0}
        if not triggered and structural <= 0:
            return "Simple query"
        parts = [f"{k}=0.8" for k in triggered]
        if structural > 0:
            parts.append(f"+struct={structural:.2f}")
        return ", ".join(parts)


# ============================================================================
# Complexity Router
# ============================================================================

class ComplexityRouter:
    def __init__(self):
        self._analyzer = ComplexityAnalyzer()

    def route(
        self,
        query: str,
        domain_hint: str = "auto",
        verbose: bool = False,
    ) -> RoutingDecision:
        dimensions = self._analyzer.analyze(query)
        semantic = sum(
            dimensions.get(k, 0) * v
            for k, v in self._analyzer.DIMENSION_WEIGHTS.items()
        )
        structural = self._analyzer._structural_boost(query)
        score = min(1.0, semantic + structural)
        tier = self._analyzer.get_tier(score)
        reasoning_base = self._analyzer.get_dimension_reasoning(dimensions, structural)

        primary_dim = ""
        if dimensions:
            primary_dim = max(dimensions.items(), key=lambda x: x[1])[0]

        # Domain hint boosts
        if domain_hint in ("cross_module", "procure_to_pay", "order_to_cash"):
            score = min(1.0, score + 0.15)
            dimensions["cross_module_join"] = max(dimensions.get("cross_module_join", 0), 0.5)
            tier = self._analyzer.get_tier(score)

        if domain_hint in ("temporal", "financial_accounting"):
            score = min(1.0, score + 0.10)
            dimensions["temporal"] = max(dimensions.get("temporal", 0), 0.5)
            tier = self._analyzer.get_tier(score)

        if domain_hint in ("quality_management", "qm"):
            score = min(1.0, score + 0.20)
            dimensions["qm_long_text"] = max(dimensions.get("qm_long_text", 0), 0.5)
            tier = self._analyzer.get_tier(score)

        if domain_hint in ("negotiation", "vendor_negotiation"):
            score = min(1.0, score + 0.20)
            dimensions["negotiation"] = max(dimensions.get("negotiation", 0), 0.5)
            tier = self._analyzer.get_tier(score)

        tier = self._analyzer.get_tier(score)
        skip_steps = {
            RoutingTier.TRIVIAL: list(SKIP_TRIVIAL),
            RoutingTier.SIMPLE: list(SKIP_SIMPLE),
            RoutingTier.COMPLEX: list(SKIP_COMPLEX),
            RoutingTier.EXPERT: [],
        }.get(tier, [])

        force_voting = tier in (RoutingTier.COMPLEX, RoutingTier.EXPERT)

        voting_override = {
            RoutingTier.TRIVIAL: 0.80,
            RoutingTier.SIMPLE: 0.75,
            RoutingTier.COMPLEX: 0.60,
            RoutingTier.EXPERT:  0.50,
        }.get(tier, 0.70)

        delegate_swarm = (tier == RoutingTier.EXPERT)

        reasoning = (
            f"[ComplexityRouter] tier={tier.value} score={score:.3f} "
            f"(semantic={semantic:.3f}+struct={structural:.2f}) | {reasoning_base}"
        )

        if verbose:
            logger.info(reasoning)

        return RoutingDecision(
            tier=tier,
            score=round(score, 4),
            dimensions={k: round(v, 4) for k, v in dimensions.items()},
            skip_steps=skip_steps,
            force_voting=force_voting,
            delegate_to_swarm=delegate_swarm,
            voting_threshold_override=voting_override,
            reasoning=reasoning,
            primary_dimension=primary_dim,
        )


# ============================================================================
# Singleton
# ============================================================================

_router: ComplexityRouter | None = None

def get_complexity_router() -> ComplexityRouter:
    global _router
    if _router is None:
        _router = ComplexityRouter()
    return _router


def get_routing_decision(
    query: str,
    domain_hint: str = "auto",
    verbose: bool = False,
) -> RoutingDecision:
    return get_complexity_router().route(query, domain_hint, verbose)