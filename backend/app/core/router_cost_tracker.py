"""
router_cost_tracker.py — Phase 20: Resource-Aware Cost Router
============================================================
Tracks per-tier routing latency. Bypasses the complexity router when routing
overhead exceeds the per-tier budget — preventing the cure from being worse
than the disease.

Key insight (Mark Kashef / V1 Pattern 15 — Resource-Aware):
  "Router overhead for TRIVIAL could exceed query cost itself."
  Phase 20 measures this and short-circuits before the overhead accumulates.

Acceptance criteria:
  - TRIVIAL queries: routing decision < 5ms (bypass if exceeded)
  - SIMPLE queries: routing decision < 15ms (bypass if exceeded)
  - COMPLEX queries: routing decision < 50ms (bypass if exceeded)
  - EXPERT queries: always route (cost is justified by swarm overhead)
  - Per-tier latency stats exposed via get_cost_stats()
  - Bypass events logged with reason

Usage:
    from app.core.router_cost_tracker import RouterCostTracker, route_with_cost

    tracker = RouterCostTracker()
    decision = tracker.route_with_budget(query, domain_hint)
    # If overhead > budget for tier, returns DEFAULT_DECISION for that tier
"""

from __future__ import annotations

import re
import time
import threading
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
from threading import Lock

from app.core.complexity_router import (
    ComplexityRouter, RoutingTier, RoutingDecision, get_routing_decision,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Per-Tier Cost Budgets (milliseconds)
# ============================================================================

# Maximum acceptable routing overhead per tier.
# If routing takes longer than this, we bypass the router and use a default.
TIER_BUDGET_MS: Dict[RoutingTier, float] = {
    RoutingTier.TRIVIAL: 5.0,   # Near-instant; router overhead dominates
    RoutingTier.SIMPLE:  15.0,  # Should be fast; Schema RAG already skipped
    RoutingTier.COMPLEX: 50.0,  # 50ms budget for full routing work
    RoutingTier.EXPERT:  999999.0,  # Never bypass — swarm cost is 100ms+
}

# Default fallback decisions when bypassing (pre-computed, no LLM needed)
DEFAULT_DECISIONS: Dict[RoutingTier, RoutingDecision] = {
    RoutingTier.TRIVIAL: RoutingDecision(
        tier=RoutingTier.TRIVIAL,
        score=0.0,
        dimensions={},
        skip_steps=[
            "schema_discovery", "schema_auto_discover",
            "graph_enhanced_schema", "graph_traversal",
            "sql_pattern_rag", "self_critique",
            "dry_run_validation", "qm_semantic", "temporal_engine",
        ],
        enabled_tools=["sql_pattern_lookup", "sql_execute"],
        force_voting=False,
        delegate_to_swarm=False,
        voting_threshold_override=0.80,
        reasoning="[RouterCostTracker] TRIVIAL default — router bypassed (overhead > 5ms budget)",
        primary_dimension="",
    ),
    RoutingTier.SIMPLE: RoutingDecision(
        tier=RoutingTier.SIMPLE,
        score=0.15,
        dimensions={},
        skip_steps=[
            "graph_traversal", "qm_semantic", "dry_run_validation",
        ],
        enabled_tools=["sql_pattern_lookup", "sql_execute", "schema_lookup", "mask_results"],
        force_voting=False,
        delegate_to_swarm=False,
        voting_threshold_override=0.75,
        reasoning="[RouterCostTracker] SIMPLE default — router bypassed (overhead > 15ms budget)",
        primary_dimension="",
    ),
    RoutingTier.COMPLEX: RoutingDecision(
        tier=RoutingTier.COMPLEX,
        score=0.40,
        dimensions={},
        skip_steps=[],
        enabled_tools=[
            "schema_lookup", "sql_pattern_lookup",
            "graph_enhanced_schema_discovery",
            "all_paths_explore", "steiner_tree_explore",
            "self_critique", "sql_execute", "mask_results", "meta_path_match",
        ],
        force_voting=True,
        delegate_to_swarm=False,
        voting_threshold_override=0.60,
        reasoning="[RouterCostTracker] COMPLEX default — router bypassed (overhead > 50ms budget)",
        primary_dimension="",
    ),
    RoutingTier.EXPERT: RoutingDecision(
        tier=RoutingTier.EXPERT,
        score=0.60,
        dimensions={},
        skip_steps=[],
        enabled_tools=[
            "schema_lookup", "sql_pattern_lookup",
            "graph_enhanced_schema_discovery",
            "all_paths_explore", "steiner_tree_explore",
            "self_critique", "dry_run_validation",
            "sql_execute", "mask_results", "meta_path_match",
            "temporal_graph_search", "qm_semantic_search",
            "negotiation_brief", "voting_sql_generate",
        ],
        force_voting=True,
        delegate_to_swarm=True,
        voting_threshold_override=0.50,
        reasoning="[RouterCostTracker] EXPERT default — router always runs (cost justified)",
        primary_dimension="",
    ),
}


# ============================================================================
# Tier Cost Statistics
# ============================================================================

@dataclass
class TierLatencyStats:
    """Running statistics for a routing tier's latency."""
    tier: RoutingTier
    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float('inf')
    max_ms: float = 0.0
    bypass_count: int = 0       # How many times we bypassed for this tier
    error_count: int = 0       # Routing errors

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count > 0 else 0.0

    @property
    def bypass_rate(self) -> float:
        return self.bypass_count / self.count if self.count > 0 else 0.0

    def record(self, latency_ms: float, bypassed: bool = False) -> None:
        self.count += 1
        self.total_ms += latency_ms
        self.min_ms = min(self.min_ms, latency_ms)
        self.max_ms = max(self.max_ms, latency_ms)
        if bypassed:
            self.bypass_count += 1

    def record_error(self) -> None:
        self.error_count += 1


# ============================================================================
# Per-Tier Budget Thresholds (for adaptive bypass)
# ============================================================================

# How many recent queries to track for adaptive thresholding
_ADAPTIVE_WINDOW = 20


# ============================================================================
# Router Cost Tracker
# ============================================================================

class RouterCostTracker:
    """
    Wraps ComplexityRouter with per-tier latency budgets.

    Tracks:
      - Per-tier routing latency (min/avg/max/count)
      - Bypass events (when overhead > tier budget)
      - Cache hit rate for repeated queries

    Key methods:
      route_with_budget():  Route + measure overhead. Returns default if over budget.
      get_cost_stats():      Return per-tier latency stats
      get_cost_report():     Human-readable summary
      get_bypass_alert():    Returns bypass reason if last route was bypassed
    """

    def __init__(
        self,
        budget_ms: Optional[Dict[RoutingTier, float]] = None,
        cache_size: int = 1024,
        enable_adaptive_budget: bool = True,
    ):
        self._budget_ms = budget_ms or dict(TIER_BUDGET_MS)
        self._router = ComplexityRouter()
        self._lock = Lock()

        # Per-tier stats
        self._stats: Dict[RoutingTier, TierLatencyStats] = {
            tier: TierLatencyStats(tier=tier) for tier in RoutingTier
        }

        # Recent latencies for adaptive thresholding (ring buffer)
        self._recent: Dict[RoutingTier, deque] = {
            tier: deque(maxlen=_ADAPTIVE_WINDOW) for tier in RoutingTier
        }

        # LRU cache for routing decisions (query → decision)
        self._cache: Dict[str, Tuple[RoutingDecision, float]] = {}  # query → (decision, timestamp)
        self._cache_ttl_ms: float = 60000.0  # Cache decisions for 60 seconds
        self._cache_size = cache_size

        # Last bypass reason (for API response)
        self._last_bypass: Optional[str] = None

        # Track if adaptive budget is enabled
        self._enable_adaptive = enable_adaptive_budget

    # ── Core routing with budget enforcement ─────────────────────────────────

    def route_with_budget(
        self,
        query: str,
        domain_hint: str = "auto",
        verbose: bool = False,
    ) -> RoutingDecision:
        """
        Route a query with cost awareness.

        Steps:
          1. Check cache — return cached decision if valid
          2. Measure routing latency
          3. If over budget for estimated tier → return default decision (bypass)
          4. Otherwise → return real routing decision

        The estimated tier is determined by a fast pre-check before full routing.
        """
        query_key = f"{query.lower().strip()}|{domain_hint}"
        now_ms = time.time() * 1000

        # Step 1: Cache check
        cached = self._cache.get(query_key)
        if cached is not None:
            decision, cached_at = cached
            if (now_ms - cached_at) < self._cache_ttl_ms:
                # Cache hit — no routing cost at all
                self._last_bypass = None
                return decision
            else:
                # Expired — remove
                del self._cache[query_key]

        # Step 2: Fast tier pre-estimation (cheap — just count signal keywords)
        estimated_tier = self._fast_estimate_tier(query)
        budget = self._get_adaptive_budget(estimated_tier)

        # Step 3: Time the full routing
        start = time.perf_counter()
        try:
            decision = self._router.route(query, domain_hint, verbose=verbose)
        except Exception as e:
            logger.warning(f"[RouterCostTracker] Routing error: {e}")
            # On error, fall back to estimated tier default
            self._stats[estimated_tier].record_error()
            default = self._get_default(estimated_tier, f"routing_error:{e}")
            self._cache_result(query_key, default, now_ms)
            return default

        latency_ms = (time.perf_counter() - start) * 1000

        # Step 4: Check against budget
        bypassed = latency_ms > budget
        actual_tier = decision.tier

        self._stats[actual_tier].record(latency_ms, bypassed=bypassed)
        self._recent[actual_tier].append(latency_ms)

        if bypassed:
            self._last_bypass = (
                f"tier={actual_tier.value} latency={latency_ms:.1f}ms "
                f"budget={budget:.1f}ms query='{query[:40]}...'"
            )
            logger.warning(
                f"[RouterCostTracker] BYPASS {actual_tier.value.upper()} — "
                f"{latency_ms:.1f}ms > {budget:.1f}ms budget "
                f"(query: '{query[:30]}...')"
            )
            default = self._get_default(actual_tier, self._last_bypass)
            self._cache_result(query_key, default, now_ms)
            return default
        else:
            self._last_bypass = None
            self._cache_result(query_key, decision, now_ms)
            return decision

    # ── Fast tier pre-estimation ────────────────────────────────────────────

    def _fast_estimate_tier(self, query: str) -> RoutingTier:
        """
        Estimate routing tier WITHOUT running the full complexity router.
        Uses only lightweight keyword counting — ~0.1ms per query.

        This is the fast-path check before spending budget on the real router.
        """
        q = query.lower()
        score = 0.0

        # Count dimension keywords (fast approximate scoring)
        dim_keywords = [
            (r'\band\b.*\bor\b|\bor\b.*\band\b|\bboth\b.*\bboth\b', 0.3),  # multi_entity
            (r'\btotal\b|\bsum\b|\bcount\b|\bgroup by\b|\bby\b.*\bplant\b', 0.2),  # aggregation
            (r'\bcompare\b|\bversus\b|\bvs\b|\btop\b|\bbottom\b', 0.2),  # comparison
            (r'\blast year\b|\blast month\b|\bfy\d|\bytd\b|\bsince\b', 0.2),  # temporal
            (r'\bvendor\b.*\bmaterial\b|\bmaterial\b.*\bvendor\b|\bcustomer\b.*\bvendor\b', 0.4),  # cross_module
            (r'\bnegotiat\b|\bdiscount\b|\bclv\b|\bchurn\b|\bbatna\b', 0.3),  # negotiation
            (r'\bquality\b|\binspection\b|\bdefect\b|\bqm\b', 0.2),  # qm
            (r'\babove\b|\bover\b|\bexceeds\b|\bgreater than\b', 0.1),  # qty threshold
        ]

        for pat, weight in dim_keywords:
            if re.search(pat, q):
                score += weight

        # Structural signal count
        struct_count = len(re.findall(
            r'\bfor\b|\bby\b|\bwhere\b|\bcompany code\b|\bplant\b|\bfiscal\b',
            q
        ))
        score += min(struct_count * 0.04, 0.15)

        if score < 0.05:
            return RoutingTier.TRIVIAL
        elif score < 0.30:
            return RoutingTier.SIMPLE
        elif score < 0.50:
            return RoutingTier.COMPLEX
        else:
            return RoutingTier.EXPERT

    # ── Adaptive budget ──────────────────────────────────────────────────────

    def _get_adaptive_budget(self, tier: RoutingTier) -> float:
        """
        Get the effective budget for a tier.
        If adaptive budgeting is enabled, adjusts based on recent latency p75.
        """
        if not self._enable_adaptive:
            return self._budget_ms.get(tier, TIER_BUDGET_MS[tier])

        recent = list(self._recent[tier])
        if len(recent) < 5:
            # Not enough data — use static budget
            return self._budget_ms.get(tier, TIER_BUDGET_MS[tier])

        # Adaptive: use p75 of recent measurements as the budget
        # This auto-adjusts if the machine is slow
        sorted_latencies = sorted(recent)
        p75_idx = int(len(sorted_latencies) * 0.75)
        p75 = sorted_latencies[p75_idx]

        static = self._budget_ms.get(tier, TIER_BUDGET_MS[tier])
        # Use the slower of (static budget, p75 * 1.5) — ensures we don't thrash
        adaptive = max(static, p75 * 1.5)
        return adaptive

    # ── Default decision helpers ─────────────────────────────────────────────

    def _get_default(self, tier: RoutingTier, bypass_reason: str) -> RoutingDecision:
        """Return the pre-computed default decision for a tier."""
        default = DEFAULT_DECISIONS.get(tier, DEFAULT_DECISIONS[RoutingTier.SIMPLE])
        # Attach the bypass reason to the reasoning
        default.reasoning = (
            f"[RouterCostTracker] BYPASS — {bypass_reason} | "
            f"{default.reasoning}"
        )
        return default

    # ── Cache ────────────────────────────────────────────────────────────────

    def _cache_result(self, key: str, decision: RoutingDecision, now_ms: float) -> None:
        """Cache a routing decision, evicting oldest if over capacity."""
        with self._lock:
            if len(self._cache) >= self._cache_size:
                # Evict oldest 10%
                evict_count = max(1, self._cache_size // 10)
                oldest_keys = sorted(self._cache.items(), key=lambda x: x[1][1])[:evict_count]
                for k, _ in oldest_keys:
                    del self._cache[k]
            self._cache[key] = (decision, now_ms)

    # ── Statistics API ─────────────────────────────────────────────────────

    def get_cost_stats(self) -> Dict[str, Any]:
        """
        Return per-tier latency statistics for monitoring.
        """
        stats = {}
        for tier, stat in self._stats.items():
            stats[tier.value] = {
                "count": stat.count,
                "avg_ms": round(stat.avg_ms, 3),
                "min_ms": round(stat.min_ms, 3) if stat.min_ms < float('inf') else 0,
                "max_ms": round(stat.max_ms, 3),
                "bypass_count": stat.bypass_count,
                "bypass_rate": round(stat.bypass_rate, 4),
                "error_count": stat.error_count,
                "budget_ms": self._budget_ms.get(tier, 0),
            }
        stats["cache_size"] = len(self._cache)
        stats["cache_ttl_ms"] = self._cache_ttl_ms
        stats["adaptive_enabled"] = self._enable_adaptive
        stats["last_bypass"] = self._last_bypass
        return stats

    def get_cost_report(self) -> str:
        """Human-readable cost report."""
        lines = ["[RouterCostTracker] Per-Tier Cost Report", "=" * 50]
        stats = self.get_cost_stats()
        for tier_name, s in stats.items():
            if tier_name in ("cache_size", "cache_ttl_ms", "adaptive_enabled", "last_bypass"):
                continue
            budget = s["budget_ms"]
            avg = s["avg_ms"]
            status = "OK" if avg < budget else "OVER BUDGET"
            lines.append(
                f"  {tier_name.upper():10} n={s['count']:4}  "
                f"avg={avg:6.2f}ms  max={s['max_ms']:6.2f}ms  "
                f"bypass={s['bypass_count']:3} ({s['bypass_rate']:.1%})  "
                f"[{status}]"
            )
        lines.append(f"  Cache: {stats['cache_size']} entries, TTL={stats['cache_ttl_ms']}ms")
        if stats.get("last_bypass"):
            lines.append(f"  Last bypass: {stats['last_bypass']}")
        return "\n".join(lines)

    def get_bypass_alert(self) -> Optional[str]:
        """Return the bypass reason from the last route_with_budget() call, if any."""
        return self._last_bypass

    def reset_stats(self) -> None:
        """Reset all statistics (keeps cache intact)."""
        with self._lock:
            for tier in RoutingTier:
                self._stats[tier] = TierLatencyStats(tier=tier)
                self._recent[tier].clear()
        logger.info("[RouterCostTracker] Statistics reset")

    def clear_cache(self) -> None:
        """Clear the routing decision cache."""
        with self._lock:
            self._cache.clear()
        logger.info("[RouterCostTracker] Cache cleared")

    # ── Budget configuration ────────────────────────────────────────────────

    def set_budget(self, tier: RoutingTier, budget_ms: float) -> None:
        """Override the budget for a specific tier."""
        self._budget_ms[tier] = budget_ms
        logger.info(f"[RouterCostTracker] Budget for {tier.value}: {budget_ms}ms")


# ============================================================================
# Module-level convenience function
# ============================================================================

_tracker: Optional[RouterCostTracker] = None


def get_router_cost_tracker() -> RouterCostTracker:
    global _tracker
    if _tracker is None:
        _tracker = RouterCostTracker()
    return _tracker


def route_with_cost(
    query: str,
    domain_hint: str = "auto",
    verbose: bool = False,
) -> RoutingDecision:
    """
    Convenience function: route with cost awareness.
    Uses the module-level RouterCostTracker singleton.
    """
    return get_router_cost_tracker().route_with_budget(query, domain_hint, verbose)
