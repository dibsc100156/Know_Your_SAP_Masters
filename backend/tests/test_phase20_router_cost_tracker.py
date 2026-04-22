import time
import unittest

from app.core.complexity_router import RoutingTier
from app.core.router_cost_tracker import RouterCostTracker, DEFAULT_DECISIONS


class Phase20RouterCostTrackerTests(unittest.TestCase):
    def test_trivial_query_stays_cheap_under_budget(self):
        tracker = RouterCostTracker(enable_adaptive_budget=False)
        tracker.set_budget(RoutingTier.TRIVIAL, 50.0)
        tracker._fast_estimate_tier = lambda query: RoutingTier.TRIVIAL
        tracker._router.route = lambda query, domain_hint="auto", verbose=False: DEFAULT_DECISIONS[RoutingTier.TRIVIAL]

        decision = tracker.route_with_budget("ok", "auto")
        stats = tracker.get_cost_stats()

        self.assertEqual(decision.tier, RoutingTier.TRIVIAL)
        self.assertEqual(stats[RoutingTier.TRIVIAL.value]["bypass_count"], 0)
        self.assertIsNone(tracker.get_bypass_alert())

    def test_bypasses_when_routing_exceeds_tier_budget(self):
        tracker = RouterCostTracker(enable_adaptive_budget=False)
        tracker.set_budget(RoutingTier.TRIVIAL, 1.0)
        tracker._fast_estimate_tier = lambda query: RoutingTier.TRIVIAL

        def slow_route(query, domain_hint="auto", verbose=False):
            time.sleep(0.01)
            return DEFAULT_DECISIONS[RoutingTier.TRIVIAL]

        tracker._router.route = slow_route

        decision = tracker.route_with_budget("show vendor", "auto")
        stats = tracker.get_cost_stats()

        self.assertEqual(decision.tier, RoutingTier.TRIVIAL)
        self.assertIn("router bypassed", decision.reasoning.lower())
        self.assertEqual(stats[RoutingTier.TRIVIAL.value]["bypass_count"], 1)
        self.assertIsNotNone(tracker.get_bypass_alert())

    def test_repeated_query_hits_cache_without_extra_routing_cost(self):
        tracker = RouterCostTracker(enable_adaptive_budget=False)
        calls = {"count": 0}

        def fast_route(query, domain_hint="auto", verbose=False):
            calls["count"] += 1
            return DEFAULT_DECISIONS[RoutingTier.SIMPLE]

        tracker._router.route = fast_route
        first = tracker.route_with_budget("vendor master", "auto")
        second = tracker.route_with_budget("vendor master", "auto")
        stats = tracker.get_cost_stats()

        self.assertEqual(first.tier, RoutingTier.SIMPLE)
        self.assertEqual(second.tier, RoutingTier.SIMPLE)
        self.assertEqual(calls["count"], 1)
        self.assertEqual(stats[RoutingTier.SIMPLE.value]["count"], 1)


if __name__ == "__main__":
    unittest.main()
