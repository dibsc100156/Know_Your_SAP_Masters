"""
eval_dashboard.py — Phase 5 Eval Metrics Dashboard
=================================================
Generates a structured eval report from memory/sap_sessions/ data.
Can be triggered on-demand or scheduled weekly via cron.

Usage:
  from app.core.eval_dashboard import EvalDashboard
  dashboard = EvalDashboard()
  report = dashboard.generate_report(period="last_7_days")
  print(report["summary"]["total_queries"])

  # Pretty print
  print(dashboard.format_text(report))
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict

from app.core.memory_layer import (
    sap_memory,
    QUERY_HISTORY,
    PATTERN_SUCCESS,
    PATTERN_FAILURES,
    GOTCHAS,
    _load_jsonl,
    _load_json,
)


class EvalDashboard:
    """
    Generates eval reports from the persistent memory layer.
    Covers: query volume, success rates, pattern hit rates, gotcha triggers,
    slowest queries, most-used domains, and weekly trends.
    """

    def __init__(self):
        self.now = datetime.now(timezone.utc)

    # -------------------------------------------------------------------------
    # Report Generation
    # -------------------------------------------------------------------------
    def generate_report(
        self,
        period: str = "all",
        domain_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a full eval report.

        Args:
            period: "last_24h" | "last_7d" | "last_30d" | "all"
            domain_filter: Optional domain to filter on

        Returns:
            Structured dict with: summary, by_domain, by_role, by_pattern,
            gotchas, slowest_queries, weekly_trend
        """
        records = self._load_records(period)

        if domain_filter:
            records = [r for r in records if r.get("domain") == domain_filter]

        if not records:
            return {"error": "No queries found for this period", "period": period}

        # Build report sections
        summary = self._build_summary(records)
        by_domain = self._build_by_domain(records)
        by_role = self._build_by_role(records)
        by_pattern = self._build_by_pattern(records)
        gotchas = self._build_gotchas_report()
        slowest = self._build_slowest_queries(records, top_n=10)
        weekly_trend = self._build_weekly_trend(records)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": period,
            "domain_filter": domain_filter,
            "summary": summary,
            "by_domain": by_domain,
            "by_role": by_role,
            "by_pattern": by_pattern,
            "gotchas": gotchas,
            "slowest_queries": slowest,
            "weekly_trend": weekly_trend,
        }

    def generate_weekly_report(self) -> Dict[str, Any]:
        """
        Generate a weekly report with trend comparisons vs prior week.
        """
        this_week = self.generate_report(period="last_7d")
        # For comparison, filter records from last 14 days and split
        return {
            "this_week": this_week,
            "recommendations": self._generate_recommendations(this_week),
        }

    # -------------------------------------------------------------------------
    # Section Builders
    # -------------------------------------------------------------------------
    def _build_summary(self, records: List[Dict]) -> Dict[str, Any]:
        total = len(records)
        if total == 0:
            return {"total_queries": 0}

        success = sum(1 for r in records if r.get("result") == "success")
        empty = sum(1 for r in records if r.get("result") == "empty")
        errors = sum(1 for r in records if r.get("result") == "error")
        partial = sum(1 for r in records if r.get("result") == "partial")

        times = [r.get("execution_time_ms", 0) for r in records if r.get("execution_time_ms")]
        critique_scores = [r.get("critique_score", 0) for r in records if r.get("critique_score")]

        return {
            "total_queries": total,
            "successful": success,
            "empty_results": empty,
            "errors": errors,
            "partial": partial,
            "success_rate": round(success / total, 3),
            "empty_rate": round(empty / total, 3),
            "error_rate": round(errors / total, 3),
            "avg_execution_ms": round(sum(times) / max(len(times), 1), 1),
            "p95_execution_ms": (
                round(sorted(times)[int(len(times) * 0.95)], 1)
                if len(times) > 5 else
                round(max(times, default=0), 1)
            ),
            "avg_critique_score": round(sum(critique_scores) / max(len(critique_scores), 1), 3),
        }

    def _build_by_domain(self, records: List[Dict]) -> Dict[str, Any]:
        by_domain = defaultdict(lambda: {
            "total": 0, "success": 0, "errors": 0, "avg_time_ms": 0, "times": []
        })
        for r in records:
            d = r.get("domain", "unknown")
            by_domain[d]["total"] += 1
            if r.get("result") == "success":
                by_domain[d]["success"] += 1
            elif r.get("result") == "error":
                by_domain[d]["errors"] += 1
            if r.get("execution_time_ms"):
                by_domain[d]["times"].append(r["execution_time_ms"])

        result = {}
        for d, stats in sorted(by_domain.items(), key=lambda x: x[1]["total"], reverse=True):
            times = stats["times"]
            result[d] = {
                "total": stats["total"],
                "success": stats["success"],
                "errors": stats["errors"],
                "rate": round(stats["success"] / max(stats["total"], 1), 3),
                "avg_time_ms": round(sum(times) / max(len(times), 1), 1) if times else 0,
            }
        return result

    def _build_by_role(self, records: List[Dict]) -> Dict[str, Any]:
        by_role = defaultdict(lambda: {"total": 0, "success": 0, "errors": 0})
        for r in records:
            role = r.get("role", "unknown")
            by_role[role]["total"] += 1
            if r.get("result") == "success":
                by_role[role]["success"] += 1
            elif r.get("result") == "error":
                by_role[role]["errors"] += 1
        return {
            role: {**stats, "rate": round(stats["success"] / max(stats["total"], 1), 3)}
            for role, stats in sorted(by_role.items(), key=lambda x: x[1]["total"], reverse=True)
        }

    def _build_by_pattern(self, records: List[Dict]) -> Dict[str, Any]:
        """Analyze SQL pattern usage from query history."""
        pattern_data = _load_json(PATTERN_SUCCESS, {})

        # Build ranking: patterns by success ratio
        rankings = []
        for key, entry in pattern_data.items():
            total = entry.get("success_count", 0) + entry.get("failure_count", 0)
            if total == 0:
                continue
            ratio = entry["success_count"] / total
            rankings.append({
                "pattern": entry["pattern_name"],
                "domain": entry["domain"],
                "success_count": entry["success_count"],
                "failure_count": entry.get("failure_count", 0),
                "total_uses": total,
                "success_ratio": round(ratio, 3),
                "avg_critique_score": entry.get("avg_critique_score", 0),
                "last_used": entry.get("last_used"),
            })

        rankings.sort(key=lambda x: (x["success_ratio"], x["total_uses"]), reverse=True)
        return {"top_patterns": rankings[:20], "total_patterns": len(rankings)}

    def _build_gotchas_report(self) -> Dict[str, Any]:
        """Show top triggered gotchas and their hit counts."""
        data = _load_json(GOTCHAS, {"gotchas": []})
        gotchas = sorted(
            data.get("gotchas", []),
            key=lambda g: g.get("hit_count", 0),
            reverse=True,
        )[:10]

        return {
            "total_gotchas": len(data.get("gotchas", [])),
            "top_gotchas": [
                {
                    "pattern": g["pattern"],
                    "domain": g.get("domain", "unknown"),
                    "severity": g.get("severity", "info"),
                    "hit_count": g.get("hit_count", 0),
                    "logged_at": g.get("logged_at"),
                }
                for g in gotchas
            ],
        }

    def _build_slowest_queries(self, records: List[Dict], top_n: int = 10) -> List[Dict]:
        """Return top-N slowest queries."""
        sorted_records = sorted(
            records,
            key=lambda r: r.get("execution_time_ms", 0),
            reverse=True,
        )[:top_n]

        return [
            {
                "query": r.get("query", "")[:80],
                "domain": r.get("domain", ""),
                "role": r.get("role", ""),
                "execution_time_ms": r.get("execution_time_ms", 0),
                "result": r.get("result", ""),
            }
            for r in sorted_records
        ]

    def _build_weekly_trend(self, records: List[Dict]) -> Dict[str, Any]:
        """Build a 7-day rolling trend."""
        if not records:
            return {}

        # Group by day
        by_day = defaultdict(lambda: {"total": 0, "success": 0, "errors": 0})
        for r in records:
            ts = r.get("timestamp", "")
            if not ts:
                continue
            try:
                day = ts[:10]  # YYYY-MM-DD
            except Exception:
                continue
            by_day[day]["total"] += 1
            if r.get("result") == "success":
                by_day[day]["success"] += 1
            elif r.get("result") == "error":
                by_day[day]["errors"] += 1

        trend = []
        for day in sorted(by_day.keys()):
            stats = by_day[day]
            trend.append({
                "date": day,
                "total": stats["total"],
                "success": stats["success"],
                "errors": stats["errors"],
                "rate": round(stats["success"] / max(stats["total"], 1), 3),
            })

        return {"daily": trend}

    # -------------------------------------------------------------------------
    # Recommendations
    # -------------------------------------------------------------------------
    def _generate_recommendations(self, report: Dict[str, Any]) -> List[Dict[str, str]]:
        recs = []
        summary = report.get("summary", {})

        if summary.get("error_rate", 0) > 0.1:
            recs.append({
                "priority": "HIGH",
                "area": "Error Rate",
                "recommendation": f"Error rate is {summary['error_rate']*100:.0f}% — "
                                   "review failed queries in query_history.jsonl. "
                                   "Consider expanding SQL patterns or fixing self-heal rules.",
            })

        if summary.get("avg_critique_score", 1.0) < 0.7:
            recs.append({
                "priority": "MEDIUM",
                "area": "SQL Quality",
                "recommendation": f"Avg critique score {summary['avg_critique_score']:.2f} is low. "
                                   "Review patterns that consistently score below 0.7 and replace them.",
            })

        by_domain = report.get("by_domain", {})
        worst_domain = max(by_domain.items(), key=lambda x: 1 - x[1].get("rate", 0)) if by_domain else None
        if worst_domain and worst_domain[1].get("rate", 1.0) < 0.6:
            recs.append({
                "priority": "MEDIUM",
                "area": f"Domain: {worst_domain[0]}",
                "recommendation": f"Success rate in '{worst_domain[0]}' domain is only "
                                   f"{worst_domain[1].get('rate', 0)*100:.0f}%. "
                                   "Check for missing patterns or table access issues.",
            })

        gotchas = report.get("gotchas", {}).get("top_gotchas", [])
        if gotchas:
            top_gotcha = gotchas[0]
            if top_gotcha.get("hit_count", 0) >= 5:
                recs.append({
                    "priority": "HIGH",
                    "area": f"Gotcha: {top_gotcha['pattern'][:50]}",
                    "recommendation": f"Gotcha '{top_gotcha['pattern'][:40]}' has been "
                                       f"hit {top_gotcha['hit_count']} times. "
                                       "This suggests a systemic issue — add a specific self-heal rule.",
                })

        if not recs:
            recs.append({
                "priority": "INFO",
                "area": "Overall",
                "recommendation": "System is healthy. Continue monitoring and encourage user feedback.",
            })

        return recs

    # -------------------------------------------------------------------------
    # Formatting
    # -------------------------------------------------------------------------
    def format_text(self, report: Dict[str, Any]) -> str:
        """Format a report as a readable ASCII text block."""
        lines = []
        lines.append("=" * 70)
        lines.append("  SAP MASTERS — EVAL REPORT")
        lines.append(f"  Generated: {report.get('generated_at', '')[:19]}")
        lines.append(f"  Period: {report.get('period', 'all')}")
        lines.append("=" * 70)

        if "error" in report:
            lines.append(f"\n  No data available: {report['error']}")
            return "\n".join(lines)

        s = report.get("summary", {})
        lines.append(f"\n📊 SUMMARY")
        lines.append(f"  Total queries : {s.get('total_queries', 0)}")
        lines.append(f"  Success rate  : {s.get('success_rate', 0)*100:.1f}%")
        lines.append(f"  Error rate    : {s.get('error_rate', 0)*100:.1f}%")
        lines.append(f"  Avg exec time : {s.get('avg_execution_ms', 0):.0f}ms")
        lines.append(f"  P95 exec time : {s.get('p95_execution_ms', 0):.0f}ms")
        lines.append(f"  Avg critique  : {s.get('avg_critique_score', 0):.2f}/1.0")

        # By domain
        lines.append(f"\n📁 BY DOMAIN")
        for d, stats in report.get("by_domain", {}).items():
            bar = "█" * int(stats.get("rate", 0) * 10) + "░" * (10 - int(stats.get("rate", 0) * 10))
            lines.append(f"  {d:<22} {bar} {stats.get('rate', 0)*100:.0f}% ({stats.get('total', 0)} q)")

        # By role
        lines.append(f"\n👤 BY ROLE")
        for role, stats in report.get("by_role", {}).items():
            lines.append(f"  {role:<30} {stats.get('total', 0):>4}q  rate={stats.get('rate', 0)*100:.0f}%")

        # Top patterns
        lines.append(f"\n🧠 TOP PATTERNS (by success ratio)")
        for p in report.get("by_pattern", {}).get("top_patterns", [])[:8]:
            lines.append(f"  {p['pattern']:<35} {p['domain']:<20} ratio={p['success_ratio']:.2f} "
                         f"uses={p['total_uses']}")

        # Gotchas
        lines.append(f"\n⚠️  TOP GOTCHAS")
        for g in report.get("gotchas", {}).get("top_gotchas", [])[:5]:
            lines.append(f"  [{g.get('severity', 'info').upper():>8}] {g.get('pattern', '')[:45]} "
                         f"hits={g.get('hit_count', 0)}")

        # Slowest
        lines.append(f"\n🐌 SLOWEST QUERIES")
        for q in report.get("slowest_queries", [])[:5]:
            lines.append(f"  {q.get('execution_time_ms', 0):>6}ms  {q.get('query', '')[:40]}")

        # Weekly trend
        trend = report.get("weekly_trend", {}).get("daily", [])
        if trend:
            lines.append(f"\n📈 7-DAY TREND")
            for d in trend[-7:]:
                bar = "█" * min(d.get("total", 0), 20)
                lines.append(f"  {d.get('date', '')}  {bar:<20} {d.get('total', 0)}q  "
                             f"rate={d.get('rate', 0)*100:.0f}%")

        # Recommendations
        recs = report.get("recommendations", [])
        if not recs and "this_week" in report:
            recs = report.get("recommendations", [])
        lines.append(f"\n💡 RECOMMENDATIONS")
        if not recs:
            lines.append("  No critical recommendations — system healthy.")
        else:
            for r in recs:
                lines.append(f"  [{r.get('priority', 'INFO'):>8}] {r.get('area', '')}")
                lines.append(f"             {r.get('recommendation', '')}")

        lines.append("\n" + "=" * 70)
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _load_records(self, period: str) -> List[Dict]:
        records = _load_jsonl(QUERY_HISTORY)
        if not records:
            return []

        cutoff = None
        if period == "last_24h":
            cutoff = self.now - timedelta(hours=24)
        elif period == "last_7d":
            cutoff = self.now - timedelta(days=7)
        elif period == "last_30d":
            cutoff = self.now - timedelta(days=30)

        if cutoff:
            filtered = []
            for r in records:
                try:
                    ts = datetime.fromisoformat(r.get("timestamp", ""))
                    if ts >= cutoff:
                        filtered.append(r)
                except Exception:
                    pass
            return filtered

        return records
