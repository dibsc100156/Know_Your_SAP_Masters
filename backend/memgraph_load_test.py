"""
memgraph_load_test.py — Phase M6: Memgraph Load Testing Suite
==============================================================
Concurrent stress test for Memgraph using pymgclient.
Measures latency percentiles, throughput, and query profiling.

Usage:
    python memgraph_load_test.py                      # all 4 test suites
    python memgraph_load_test.py --suite latency      # latency profiling only
    python memgraph_load_test.py --concurrent 20     # 20 concurrent workers
    python memgraph_load_test.py --duration 60       # 60-second steady-state test
    python memgraph_load_test.py --compare            # Memgraph vs NetworkX comparison
    python memgraph_load_test.py --profile            # query-level profiling
    python memgraph_load_test.py --report             # full report + JSON export

Metrics:
  - Latency: min, mean, p50, p75, p90, p95, p99, max (ms)
  - Throughput: queries/second (sustained)
  - Error rate: % queries that errored
  - Connection pool: active/idle/waiting connections
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mgclient

# =============================================================================
# Test Queries — 3 tiers of complexity
# =============================================================================

@dataclass
class TestQuery:
    name: str
    cypher: str
    params: Dict[str, Any]
    tier: str          # simple | moderate | complex
    description: str


MEMGRAPH_TEST_QUERIES: List[TestQuery] = [
    # ── Tier 1: Simple lookup ───────────────────────────────────────────────
    TestQuery(
        name="LFA1_metadata",
        cypher="MATCH (a:SAPTable {table_name: 'LFA1'}) RETURN a.table_name, a.module",
        params={},
        tier="simple",
        description="Single-table metadata lookup",
    ),
    TestQuery(
        name="LFA1_direct_neighbors",
        cypher=(
            "MATCH (a:SAPTable {table_name: 'LFA1'})-[r:FOREIGN_KEY]->(b:SAPTable) "
            "RETURN a.table_name AS src, b.table_name AS dst, r.cardinality AS card "
            "LIMIT 10"
        ),
        params={},
        tier="simple",
        description="Direct 1-hop neighbors of LFA1",
    ),
    # ── Tier 2: Moderate — multi-hop ──────────────────────────────────────
    TestQuery(
        name="LFA1_EKKO_2hop",
        cypher=(
            "MATCH (a:SAPTable {table_name: 'LFA1'})-[r1:FOREIGN_KEY*1..2]-(b:SAPTable {table_name: 'EKKO'}) "
            "RETURN a.table_name, b.table_name, SIZE(r1) AS hops LIMIT 5"
        ),
        params={},
        tier="moderate",
        description="Variable-length path LFA1→EKKO (up to 2 hops)",
    ),
    TestQuery(
        name="LFA1_2hop_filtered",
        cypher=(
            "MATCH (a:SAPTable)-[r1:FOREIGN_KEY*1..2]-(b:SAPTable) "
            "WHERE a.table_name = 'LFA1' AND b.module = 'Purchasing' "
            "RETURN a.table_name AS src, b.table_name AS dst, b.module, SIZE(r1) AS hops LIMIT 10"
        ),
        params={},
        tier="moderate",
        description="2-hop path with module filter",
    ),
    TestQuery(
        name="MARA_3hop_trace",
        cypher=(
            "MATCH (a:SAPTable {table_name: 'MARA'})-[*1..3]-(b:SAPTable) "
            "RETURN a.table_name AS src, b.table_name AS dst, b.module "
            "LIMIT 15"
        ),
        params={},
        tier="moderate",
        description="Material traceability — 3-hop neighborhood",
    ),
    # ── Tier 3: Complex — full graph traversal ──────────────────────────────
    TestQuery(
        name="cross_module_bridges",
        cypher=(
            "MATCH (a:SAPTable)-[r:FOREIGN_KEY]-(b:SAPTable) "
            "WHERE r.bridge_type = 'cross_module' "
            "RETURN a.table_name AS src, b.table_name AS dst, r.notes AS note "
            "LIMIT 30"
        ),
        params={},
        tier="complex",
        description="All cross-module bridge edges",
    ),
    TestQuery(
        name="all_tables_3hop",
        cypher=(
            "MATCH (a:SAPTable)-[r:FOREIGN_KEY*1..3]-(b:SAPTable) "
            "RETURN DISTINCT b.table_name AS table_name, b.module, SIZE(r) AS hops "
            "ORDER BY hops LIMIT 25"
        ),
        params={},
        tier="complex",
        description="All reachable tables within 3 hops",
    ),
]


# =============================================================================
# Result Types
# =============================================================================

@dataclass
class QueryResult:
    query_name: str
    latency_ms: float
    success: bool
    error: Optional[str] = None
    worker_id: int = 0
    timestamp: str = ""


@dataclass
class LoadTestResult:
    suite_name: str
    tier: str
    concurrent_workers: int
    duration_seconds: float
    total_queries: int
    success_count: int
    error_count: int
    error_rate_pct: float
    latency_min_ms: float
    latency_mean_ms: float
    latency_p50_ms: float
    latency_p75_ms: float
    latency_p90_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_max_ms: float
    throughput_qps: float
    latencies_ms: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    memgraph_stats: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


# =============================================================================
# Connection Pool
# =============================================================================

class MemgraphPool:
    """Thread-safe connection pool using pymgclient."""

    def __init__(self, host: str = "localhost", port: int = 7687,
                 username: str = "", password: str = "", pool_size: int = 10):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.pool_size = pool_size
        self._lock = threading.Lock()
        self._connections: List[Any] = []
        self._active = 0
        self._created = 0

    def _create_connection(self) -> Any:
        conn = mgclient.connect(
            host=self.host, port=self.port,
            username=self.username, password=self.password,
        )
        # Verify connectivity
        cursor = conn.cursor()
        cursor.execute("RETURN 1")
        cursor.fetchall()
        return conn

    def get_connection(self) -> Any:
        with self._lock:
            self._active += 1
            if self._connections:
                return self._connections.pop()
            self._created += 1
        return self._create_connection()

    def return_connection(self, conn: Any):
        with self._lock:
            self._active -= 1
            if len(self._connections) < self.pool_size:
                self._connections.append(conn)
            else:
                try:
                    conn.close()
                except Exception:
                    pass

    def get_pool_stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "pool_size": self.pool_size,
                "idle": len(self._connections),
                "active": self._active,
                "created": self._created,
            }


# =============================================================================
# Load Tester
# =============================================================================

class MemgraphLoadTester:
    def __init__(self, host: str = "localhost", port: int = 7687,
                 username: str = "", password: str = "", pool_size: int = 10):
        self.pool = MemgraphPool(host, port, username, password, pool_size)

    def run_query(self, query: TestQuery, worker_id: int = 0) -> QueryResult:
        ts = datetime.now(timezone.utc).isoformat()
        conn = None
        try:
            conn = self.pool.get_connection()
            cursor = conn.cursor()
            start = time.perf_counter()
            cursor.execute(query.cypher, query.params)
            list(cursor.fetchall())  # Consume results
            latency_ms = (time.perf_counter() - start) * 1000
            return QueryResult(query_name=query.name, latency_ms=latency_ms,
                               success=True, worker_id=worker_id, timestamp=ts)
        except Exception as e:
            return QueryResult(query_name=query.name, latency_ms=0,
                               success=False, error=str(e), worker_id=worker_id, timestamp=ts)
        finally:
            if conn:
                self.pool.return_connection(conn)

    def run_burst_test(
        self, query: TestQuery,
        concurrent_workers: int = 10,
        queries_per_worker: int = 20,
    ) -> LoadTestResult:
        total = concurrent_workers * queries_per_worker
        results: List[QueryResult] = []

        def worker(wid: int) -> List[QueryResult]:
            return [self.run_query(query, wid) for _ in range(queries_per_worker)]

        start_time = time.perf_counter()
        with ThreadPoolExecutor(max_workers=concurrent_workers) as ex:
            futures = [ex.submit(worker, i) for i in range(concurrent_workers)]
            for f in as_completed(futures):
                try:
                    results.extend(f.result())
                except Exception as e:
                    print(f"[WARN] Worker exception: {e}")

        elapsed = time.perf_counter() - start_time
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        latencies = sorted([r.latency_ms for r in successes])
        n = len(latencies)

        return LoadTestResult(
            suite_name=query.name,
            tier=query.tier,
            concurrent_workers=concurrent_workers,
            duration_seconds=round(elapsed, 3),
            total_queries=total,
            success_count=len(successes),
            error_count=len(failures),
            error_rate_pct=round(len(failures) / total * 100, 2) if total else 0,
            latency_min_ms=round(min(latencies), 3) if latencies else 0,
            latency_mean_ms=round(statistics.mean(latencies), 3) if latencies else 0,
            latency_p50_ms=round(latencies[int(n * 0.50)], 3) if n > 0 else 0,
            latency_p75_ms=round(latencies[int(n * 0.75)], 3) if n > 0 else 0,
            latency_p90_ms=round(latencies[int(n * 0.90)], 3) if n > 0 else 0,
            latency_p95_ms=round(latencies[int(n * 0.95)], 3) if n > 0 else 0,
            latency_p99_ms=round(latencies[int(n * 0.99)], 3) if n > 0 else 0,
            latency_max_ms=round(max(latencies), 3) if latencies else 0,
            throughput_qps=round(total / elapsed, 2),
            latencies_ms=latencies,
            errors=[r.error for r in failures if r.error][:5],
            memgraph_stats=self.pool.get_pool_stats(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def run_steady_state_test(
        self, query: TestQuery,
        target_qps: float = 50,
        duration_seconds: float = 30,
    ) -> LoadTestResult:
        interval = 1.0 / target_qps
        results: List[QueryResult] = []
        start_time = time.perf_counter()
        next_dispatch = start_time
        wid = 0

        with ThreadPoolExecutor(max_workers=min(int(target_qps), 20)) as ex:
            futures = []

            while (time.perf_counter() - start_time) < duration_seconds:
                now = time.perf_counter()
                if now >= next_dispatch:
                    futures.append(ex.submit(self.run_query, query, wid))
                    wid += 1
                    next_dispatch += interval
                else:
                    time.sleep(0.001)

            for f in as_completed(futures):
                try:
                    results.append(f.result())
                except Exception:
                    pass

        total_time = time.perf_counter() - start_time
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        latencies = sorted([r.latency_ms for r in successes])
        n = len(latencies)
        total = len(results)

        return LoadTestResult(
            suite_name=f"{query.name}_steady_{int(target_qps)}qps",
            tier=query.tier,
            concurrent_workers=int(target_qps),
            duration_seconds=round(total_time, 3),
            total_queries=total,
            success_count=len(successes),
            error_count=len(failures),
            error_rate_pct=round(len(failures) / total * 100, 2) if total else 0,
            latency_min_ms=round(min(latencies), 3) if latencies else 0,
            latency_mean_ms=round(statistics.mean(latencies), 3) if latencies else 0,
            latency_p50_ms=round(latencies[int(n * 0.50)], 3) if n > 0 else 0,
            latency_p75_ms=round(latencies[int(n * 0.75)], 3) if n > 0 else 0,
            latency_p90_ms=round(latencies[int(n * 0.90)], 3) if n > 0 else 0,
            latency_p95_ms=round(latencies[int(n * 0.95)], 3) if n > 0 else 0,
            latency_p99_ms=round(latencies[int(n * 0.99)], 3) if n > 0 else 0,
            latency_max_ms=round(max(latencies), 3) if latencies else 0,
            throughput_qps=round(total / total_time, 2),
            latencies_ms=latencies,
            errors=[r.error for r in failures if r.error][:5],
            memgraph_stats=self.pool.get_pool_stats(),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


# =============================================================================
# NetworkX comparison baseline
# =============================================================================

def run_networkx_baseline(query: TestQuery) -> Dict[str, Any]:
    """Run equivalent NetworkX traversal for latency comparison."""
    try:
        from app.core.graph_store import graph_store
        start = time.perf_counter()

        if query.name == "LFA1_metadata":
            node = graph_store.get_node("LFA1")
            return {"success": True, "latency_ms": round((time.perf_counter() - start) * 1000, 3)}

        elif query.name == "LFA1_direct_neighbors":
            list(graph_store.get_neighbors("LFA1"))
            return {"success": True, "latency_ms": round((time.perf_counter() - start) * 1000, 3)}

        elif query.name == "LFA1_EKKO_2hop":
            paths = list(graph_store.find_all_ranked_paths("LFA1", "EKKO", max_depth=2))
            return {"success": True, "latency_ms": round((time.perf_counter() - start) * 1000, 3), "count": len(paths)}

        elif query.name == "LFA1_2hop_filtered":
            paths = list(graph_store.find_all_ranked_paths("LFA1", None, max_depth=2))
            filtered = [p for p in paths if graph_store.get_node(p[-1]).get("module") == "Purchasing"]
            return {"success": True, "latency_ms": round((time.perf_counter() - start) * 1000, 3), "count": len(filtered)}

        elif query.name == "cross_module_bridges":
            edges = [(s, t) for (s, t), m in getattr(graph_store, "_edge_meta", {}).items()
                     if m.get("bridge_type") == "cross_module"]
            return {"success": True, "latency_ms": round((time.perf_counter() - start) * 1000, 3), "count": len(edges)}

        else:
            return {"success": True, "latency_ms": round((time.perf_counter() - start) * 1000, 3), "note": "no equiv"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# =============================================================================
# Report
# =============================================================================

def print_report(results: List[LoadTestResult], compare: Optional[Dict] = None):
    print()
    print("=" * 90)
    print("  MEMGRAPH LOAD TEST REPORT — Phase M6")
    print("=" * 90)
    print(f"  Timestamp:    {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"  Suites run:  {len(results)}")
    print()

    for res in results:
        ok = res.error_rate_pct == 0
        warn = 0 < res.error_rate_pct < 5
        icon = "\033[92mOK\033[0m" if ok else "\033[93mWARN\033[0m" if warn else f"\033[91mERR {res.error_rate_pct}%\033[0m"
        print(f"  {res.suite_name}  [tier={res.tier}, workers={res.concurrent_workers}]")
        print(f"    {icon}  {res.total_queries} queries / {res.duration_seconds:.2f}s  |  "
              f"p50={res.latency_p50_ms:.2f}ms  p95={res.latency_p95_ms:.2f}ms  "
              f"max={res.latency_max_ms:.2f}ms  qps={res.throughput_qps:.1f}")
        if res.errors:
            print(f"    Errors: {res.errors[:2]}")
        print()

    if compare:
        print("=" * 90)
        print("  MEMGRAPH vs NetworkX")
        print("=" * 90)
        print(f"  {'Query':<35} {'Memgraph':>12} {'NetworkX':>12} {'Winner':>12}")
        print(f"  {'─' * 73}")
        for qname, d in compare.items():
            mg = d.get("memgraph_ms")
            nx = d.get("networkx_ms")
            mg_str = f"{mg:.2f}ms" if mg else "FAIL"
            nx_str = f"{nx:.2f}ms" if nx else "FAIL"
            winner = ""
            if mg and nx:
                winner = "Memgraph" if mg < nx else "NetworkX"
                ratio = min(mg, nx) / max(mg, nx)
                winner += f" ({ratio:.2f}x)"
            print(f"  {qname:<35} {mg_str:>12} {nx_str:>12} {winner:>12}")
        print()


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Memgraph Load Testing — Phase M6")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7687)
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    parser.add_argument("--pool-size", type=int, default=10)
    parser.add_argument("--suite", choices=["all", "latency", "throughput", "compare"],
                        default="all")
    parser.add_argument("--concurrent", type=int, nargs="+", default=[1, 5, 10, 20])
    parser.add_argument("--duration", type=int, default=20)
    parser.add_argument("--target-qps", type=int, default=50)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--output", default="backend/load_test_memgraph.json")
    args = parser.parse_args()

    tester = MemgraphLoadTester(
        host=args.host, port=args.port,
        username=args.username, password=args.password,
        pool_size=args.pool_size,
    )

    # ── Connectivity check ─────────────────────────────────────────────────
    try:
        conn = tester.pool.get_connection()
        tester.pool.return_connection(conn)
        print(f"[OK] Memgraph connected at {args.host}:{args.port}")
    except Exception as e:
        print(f"[FAIL] Cannot connect to Memgraph: {e}")
        print("       Is Memgraph running?")
        sys.exit(1)

    all_results: List[LoadTestResult] = []
    compare_results: Dict[str, Dict] = {}

    # ── Latency burst tests ────────────────────────────────────────────────
    if args.suite in ("all", "latency"):
        print(f"\n[Latency] Burst tests at concurrency: {args.concurrent}")
        for query in MEMGRAPH_TEST_QUERIES:
            for conc in args.concurrent:
                res = tester.run_burst_test(query, concurrent_workers=conc,
                                            queries_per_worker=max(5, 30 // conc))
                all_results.append(res)
                icon = "OK" if res.error_rate_pct == 0 else f"ERR {res.error_rate_pct}%"
                print(f"  {query.name}[tier={query.tier}] workers={conc}: "
                      f"p50={res.latency_p50_ms:.1f}ms p95={res.latency_p95_ms:.1f}ms "
                      f"qps={res.throughput_qps:.1f} [{icon}]")

    # ── Steady-state throughput ────────────────────────────────────────────
    if args.suite in ("all", "throughput"):
        print(f"\n[Throughput] Steady-state at {args.target_qps} QPS for {args.duration}s")
        for query in [q for q in MEMGRAPH_TEST_QUERIES if q.tier == "moderate"]:
            res = tester.run_steady_state_test(query, target_qps=args.target_qps,
                                                duration_seconds=args.duration)
            all_results.append(res)
            print(f"  {res.suite_name}: actual={res.throughput_qps:.1f} qps "
                  f"p95={res.latency_p95_ms:.1f}ms err={res.error_rate_pct}%")

    # ── Memgraph vs NetworkX ──────────────────────────────────────────────
    if args.suite in ("all", "compare"):
        print(f"\n[Compare] Memgraph vs NetworkX")
        try:
            from app.core.graph_store import graph_store
            print("  [OK] NetworkX graph_store loaded")
        except Exception as e:
            print(f"  [SKIP] NetworkX unavailable: {e}")
            args.suite = args.suite.replace("compare", "")

        for query in MEMGRAPH_TEST_QUERIES[:5]:
            r = tester.run_query(query)
            mg_ms = r.latency_ms if r.success else None
            nx = run_networkx_baseline(query)
            nx_ms = nx.get("latency_ms") if nx.get("success") else None

            compare_results[query.name] = {
                "memgraph_ms": round(mg_ms, 3) if mg_ms else None,
                "networkx_ms": round(nx_ms, 3) if nx_ms else None,
                "tier": query.tier,
            }
            mg_s = f"{mg_ms:.2f}ms" if mg_ms else "FAIL"
            nx_s = f"{nx_ms:.2f}ms" if nx_ms else "FAIL"
            win = ""
            if mg_ms and nx_ms:
                win = "Memgraph" if mg_ms < nx_ms else "NetworkX"
                win += f" {min(mg_ms,nx_ms)/max(mg_ms,nx_ms):.2f}x"
            print(f"  {query.name}: Memgraph={mg_s}  NetworkX={nx_s}  → {win or 'N/A'}")

    print_report(all_results, compare_results if compare_results else None)

    if args.report:
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "host": args.host,
            "port": args.port,
            "pool_size": args.pool_size,
            "results": [asdict(r) for r in all_results],
            "compare": compare_results,
        }
        output_path = args.output
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\n[Report] → {output_path}")


if __name__ == "__main__":
    main()
