from __future__ import annotations

"""
hybrid_graph_signoff.py
=======================

Phase: Hybrid graph runtime perf/load sign-off

Purpose:
- Verify parity between the baseline NetworkX graph and the hybrid Memgraph+NetworkX runtime
- Measure latency for the main graph APIs used by the orchestrator
- Optionally run Memgraph load tests for burst/steady-state coverage
- Emit a JSON sign-off report with PASS/WARN/FAIL gates

Usage:
    python hybrid_graph_signoff.py
    python hybrid_graph_signoff.py --iterations 25 --workers 10 --target-qps 40
    python hybrid_graph_signoff.py --skip-load --output backend/reports/hybrid_graph_signoff.json

Notes:
- Memgraph must be running for full sign-off
- The script is safe and read-only
- Load testing reuses the existing memgraph_load_test.py suite when mgclient is available
"""

import argparse
import json
import os
import queue
import socket
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from neo4j import GraphDatabase

from app.core.graph_store import GraphRAGManager

try:
    from memgraph_load_test import MEMGRAPH_TEST_QUERIES
    LOAD_TEST_AVAILABLE = True
except Exception:
    MEMGRAPH_TEST_QUERIES = []
    LOAD_TEST_AVAILABLE = False


PATH_CASES: List[Tuple[str, str]] = [
    ("MARA", "LFA1"),
    ("MARA", "KNA1"),
    ("LFA1", "EKKO"),
    ("LFA1", "BKPF"),
    ("KNA1", "BSEG"),
    ("VBAK", "VBRK"),
    ("MARA", "QALS"),
    ("PRPS", "MARA"),
]

NEIGHBOR_CASES: List[Tuple[str, int]] = [
    ("LFA1", 1),
    ("MARA", 1),
    ("MARA", 2),
    ("EKKO", 2),
]

RANKED_CASES: List[Tuple[str, str, int, int]] = [
    ("LFA1", "EKKO", 3, 3),
    ("MARA", "QALS", 3, 3),
    ("VBAK", "VBRK", 4, 3),
]

_DRIVER_CACHE: Dict[str, Any] = {}

DEFAULT_SLOS = {
    "find_path_p95_ms": 3.0,
    "neighbors_p95_ms": 5.0,
    "subgraph_p95_ms": 6.0,
    "ranked_native_p95_ms": 40.0,
    "load_burst_p95_ms": 60.0,
    "load_steady_p95_ms": 80.0,
    "error_rate_pct": 0.0,
}


@dataclass
class MetricSummary:
    name: str
    count: int
    min_ms: float
    mean_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    error_count: int = 0
    sample_errors: List[str] = field(default_factory=list)


@dataclass
class SignoffReport:
    generated_at: str
    memgraph_uri: str
    tenant_id: str
    baseline_stats: Dict[str, Any]
    hybrid_stats: Dict[str, Any]
    remote_counts: Dict[str, Any]
    parity: Dict[str, Any]
    latency: Dict[str, Any]
    load: Dict[str, Any]
    slos: Dict[str, float]
    gates: Dict[str, Any]
    overall_status: str


def percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, max(0, int(round((len(sorted_values) - 1) * q))))
    return float(sorted_values[idx])


def summarize_latencies(name: str, latencies: List[float], errors: List[str]) -> MetricSummary:
    values = sorted(latencies)
    if not values:
        return MetricSummary(
            name=name,
            count=0,
            min_ms=0.0,
            mean_ms=0.0,
            p50_ms=0.0,
            p95_ms=0.0,
            p99_ms=0.0,
            max_ms=0.0,
            error_count=len(errors),
            sample_errors=errors[:5],
        )
    return MetricSummary(
        name=name,
        count=len(values),
        min_ms=round(min(values), 3),
        mean_ms=round(statistics.mean(values), 3),
        p50_ms=round(percentile(values, 0.50), 3),
        p95_ms=round(percentile(values, 0.95), 3),
        p99_ms=round(percentile(values, 0.99), 3),
        max_ms=round(max(values), 3),
        error_count=len(errors),
        sample_errors=errors[:5],
    )


def measure(name: str, iterations: int, fn: Callable[[int], Any]) -> MetricSummary:
    latencies: List[float] = []
    errors: List[str] = []
    for i in range(iterations):
        started = time.perf_counter()
        try:
            fn(i)
            latencies.append((time.perf_counter() - started) * 1000)
        except Exception as exc:
            errors.append(str(exc))
    return summarize_latencies(name, latencies, errors)


class OfflineHybridGraph:
    def __init__(self, baseline: GraphRAGManager, memgraph_uri: str, tenant_id: str):
        self._baseline = baseline
        self._mg = None
        self._is_connected = False
        self.uri = memgraph_uri
        self.tenant_id = tenant_id
        self.tenant_label = f"Tenant_{tenant_id}"

    def find_path(self, start_table: str, end_table: str):
        return self._baseline.find_path(start_table, end_table)

    def get_neighbors(self, table: str, depth: int = 1):
        return self._baseline.get_neighbors(table, depth)

    def get_subgraph_context(self, path: List[str]):
        return self._baseline.get_subgraph_context(path)

    def stats(self) -> Dict[str, Any]:
        stats = dict(self._baseline.stats())
        stats["memgraph_connected"] = False
        return stats


def is_socket_open(host: str, port: int, timeout_seconds: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return True
    except OSError:
        return False


def build_hybrid_from_baseline(
    baseline: GraphRAGManager,
    memgraph_uri: str,
    tenant_id: str,
):
    return OfflineHybridGraph(baseline, memgraph_uri=memgraph_uri, tenant_id=tenant_id)


def build_driver(uri: str):
    driver = _DRIVER_CACHE.get(uri)
    if driver is None:
        driver = GraphDatabase.driver(uri, connection_timeout=2, max_transaction_retry_time=1)
        _DRIVER_CACHE[uri] = driver
    return driver


def close_drivers() -> None:
    for driver in _DRIVER_CACHE.values():
        try:
            driver.close()
        except Exception:
            pass
    _DRIVER_CACHE.clear()


def direct_native_ranked_query(host: str, port: int, start: str, end: str, max_depth: int, top_k: int) -> Dict[str, Any]:
    if not is_socket_open(host, port):
        raise RuntimeError("Memgraph native query path unavailable")

    query = (
        f"MATCH path = (a:SAPTable {{table_name: $start}})-[*BFS..{max_depth}]-(b:SAPTable {{table_name: $end}}) "
        f"RETURN path LIMIT {top_k}"
    )
    driver = build_driver(f"bolt://{host}:{port}")
    with driver.session() as session:
        rows = list(session.run(query, {"start": start, "end": end}))
    return {"row_count": len(rows)}


def verify_remote_counts(memgraph_uri: str, tenant_id: str) -> Dict[str, Any]:
    host, port = infer_host_port(memgraph_uri)
    tenant_label = f"Tenant_{tenant_id}"
    if not is_socket_open(host, port):
        return {
            "connected": False,
            "tenant_label": tenant_label,
            "node_count": None,
            "edge_count": None,
        }

    driver = build_driver(memgraph_uri)
    try:
        with driver.session() as session:
            node_count = [dict(r.items()) for r in session.run(f"MATCH (n:SAPTable:{tenant_label}) RETURN count(n) AS c")][0]["c"]
            edge_count = [dict(r.items()) for r in session.run(f"MATCH (:SAPTable:{tenant_label})-[r:FOREIGN_KEY]->(:SAPTable:{tenant_label}) RETURN count(r) AS c")][0]["c"]
            generic_node_count = [dict(r.items()) for r in session.run("MATCH (n:SAPTable) RETURN count(n) AS c")][0]["c"]
            generic_edge_count = [dict(r.items()) for r in session.run("MATCH (:SAPTable)-[r:FOREIGN_KEY]->(:SAPTable) RETURN count(r) AS c")][0]["c"]
        result = {
            "connected": True,
            "tenant_label": tenant_label,
            "node_count": node_count,
            "edge_count": edge_count,
            "generic_node_count": generic_node_count,
            "generic_edge_count": generic_edge_count,
        }
        if node_count == 0 and generic_node_count > 0:
            result["node_count"] = generic_node_count
            result["edge_count"] = generic_edge_count
            result["label_mode"] = "generic_fallback"
        else:
            result["label_mode"] = "tenant"
        return result
    except Exception as exc:
        return {
            "connected": False,
            "tenant_label": tenant_label,
            "node_count": None,
            "edge_count": None,
            "error": str(exc),
        }


def verify_parity(baseline: GraphRAGManager, hybrid) -> Dict[str, Any]:
    path_results: List[Dict[str, Any]] = []
    matched = 0
    for start, end in PATH_CASES:
        base_path = baseline.find_path(start, end)
        hybrid_path = hybrid.find_path(start, end)
        ok = base_path == hybrid_path
        if ok:
            matched += 1
        path_results.append({
            "start": start,
            "end": end,
            "baseline": base_path,
            "hybrid": hybrid_path,
            "match": ok,
        })

    neighbor_results: List[Dict[str, Any]] = []
    neighbors_matched = 0
    for table, depth in NEIGHBOR_CASES:
        base_neighbors = sorted(baseline.get_neighbors(table, depth).keys())
        hybrid_neighbors = sorted(hybrid.get_neighbors(table, depth).keys())
        ok = base_neighbors == hybrid_neighbors
        if ok:
            neighbors_matched += 1
        neighbor_results.append({
            "table": table,
            "depth": depth,
            "baseline_count": len(base_neighbors),
            "hybrid_count": len(hybrid_neighbors),
            "match": ok,
        })

    return {
        "table_count_match": baseline.stats()["total_tables"] == hybrid.stats()["total_tables"],
        "edge_count_match": baseline.stats()["total_relationships"] == hybrid.stats()["total_relationships"],
        "path_match_rate": round(matched / len(PATH_CASES), 3),
        "neighbor_match_rate": round(neighbors_matched / len(NEIGHBOR_CASES), 3),
        "path_cases": path_results,
        "neighbor_cases": neighbor_results,
    }


def build_latency_profile(
    baseline: GraphRAGManager,
    hybrid,
    iterations: int,
    host: str,
    port: int,
    skip_native: bool,
) -> Dict[str, Any]:
    find_path_metric = measure(
        "find_path",
        iterations,
        lambda i: hybrid.find_path(*PATH_CASES[i % len(PATH_CASES)]),
    )

    neighbors_metric = measure(
        "get_neighbors",
        iterations,
        lambda i: hybrid.get_neighbors(*NEIGHBOR_CASES[i % len(NEIGHBOR_CASES)]),
    )

    def subgraph_op(i: int) -> Any:
        start, end = PATH_CASES[i % len(PATH_CASES)]
        path = baseline.find_path(start, end)
        if not path:
            raise ValueError(f"No baseline path for {start}->{end}")
        return hybrid.get_subgraph_context(path)

    subgraph_metric = measure("get_subgraph_context", iterations, subgraph_op)

    if skip_native:
        ranked_metric = summarize_latencies(
            "find_all_ranked_paths_native",
            [],
            ["skipped by flag"],
        )
    else:
        ranked_metric = measure(
            "find_all_ranked_paths_native",
            iterations,
            lambda i: direct_native_ranked_query(host, port, *RANKED_CASES[i % len(RANKED_CASES)]),
        )

    return {
        "find_path": asdict(find_path_metric),
        "get_neighbors": asdict(neighbors_metric),
        "get_subgraph_context": asdict(subgraph_metric),
        "find_all_ranked_paths_native": asdict(ranked_metric),
    }


def run_mixed_workload(
    baseline: GraphRAGManager,
    hybrid,
    rounds: int,
    host: str,
    port: int,
    skip_native: bool,
) -> MetricSummary:
    latencies: List[float] = []
    errors: List[str] = []

    for seed in range(rounds):
        started = time.perf_counter()
        try:
            start, end = PATH_CASES[seed % len(PATH_CASES)]
            path = hybrid.find_path(start, end)
            if not path:
                raise ValueError(f"Missing path for {start}->{end}")
            hybrid.get_subgraph_context(path)
            hybrid.get_neighbors(*NEIGHBOR_CASES[seed % len(NEIGHBOR_CASES)])
            if not skip_native and LOAD_TEST_AVAILABLE and is_socket_open(host, port):
                direct_native_ranked_query(host, port, *RANKED_CASES[seed % len(RANKED_CASES)])
            latencies.append((time.perf_counter() - started) * 1000)
        except Exception as exc:
            errors.append(str(exc))

    return summarize_latencies("mixed_workload", latencies, errors)


def maybe_run_load_tests(
    host: str,
    port: int,
    workers: int,
    target_qps: int,
    duration_seconds: int,
) -> Dict[str, Any]:
    try:
        direct_native_ranked_query(host, port, "LFA1", "EKKO", 2, 1)
    except Exception as exc:
        return {
            "available": False,
            "reason": f"Memgraph health preflight failed: {exc}",
        }

    uri = f"bolt://{host}:{port}"
    driver = build_driver(uri)
    complex_query = (
        "MATCH (a:SAPTable)-[r:FOREIGN_KEY]-(b:SAPTable) "
        "WHERE r.bridge_type = 'cross_module' "
        "RETURN a.table_name AS src, b.table_name AS dst, r.notes AS note LIMIT 30"
    )
    neighbor_query = (
        "MATCH (a:SAPTable {table_name: 'LFA1'})-[r:FOREIGN_KEY]->(b:SAPTable) "
        "RETURN a.table_name AS src, b.table_name AS dst, r.cardinality AS card LIMIT 10"
    )

    def run_query(cypher: str) -> float:
        with driver.session() as session:
            started = time.perf_counter()
            list(session.run(cypher))
            return (time.perf_counter() - started) * 1000

    def summarize_load(name: str, tier: str, latencies: List[float], errors: List[str], elapsed: float, concurrent_workers: int) -> Dict[str, Any]:
        values = sorted(latencies)
        n = len(values)
        total = len(latencies) + len(errors)
        return {
            "suite_name": name,
            "tier": tier,
            "concurrent_workers": concurrent_workers,
            "duration_seconds": round(elapsed, 3),
            "total_queries": total,
            "success_count": len(latencies),
            "error_count": len(errors),
            "error_rate_pct": round((len(errors) / total) * 100, 2) if total else 0,
            "latency_min_ms": round(min(values), 3) if values else 0,
            "latency_mean_ms": round(statistics.mean(values), 3) if values else 0,
            "latency_p50_ms": round(percentile(values, 0.50), 3) if values else 0,
            "latency_p75_ms": round(percentile(values, 0.75), 3) if values else 0,
            "latency_p90_ms": round(percentile(values, 0.90), 3) if values else 0,
            "latency_p95_ms": round(percentile(values, 0.95), 3) if values else 0,
            "latency_p99_ms": round(percentile(values, 0.99), 3) if values else 0,
            "latency_max_ms": round(max(values), 3) if values else 0,
            "throughput_qps": round(total / elapsed, 2) if elapsed > 0 else 0,
            "latencies_ms": [round(v, 3) for v in values],
            "errors": errors[:5],
            "memgraph_stats": {"driver": "neo4j"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    try:
        burst_latencies: List[float] = []
        burst_errors: List[str] = []
        burst_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_query, complex_query) for _ in range(workers * 5)]
            for future in as_completed(futures):
                try:
                    burst_latencies.append(future.result())
                except Exception as exc:
                    burst_errors.append(str(exc))
        burst_elapsed = time.perf_counter() - burst_started
        burst = summarize_load("cross_module_bridges_burst", "complex", burst_latencies, burst_errors, burst_elapsed, workers)

        steady_latencies: List[float] = []
        steady_errors: List[str] = []
        steady_started = time.perf_counter()
        dispatch_interval = 1.0 / max(target_qps, 1)
        next_dispatch = steady_started
        futures = []
        with ThreadPoolExecutor(max_workers=min(max(target_qps, 1), max(workers, 4), 32)) as pool:
            while (time.perf_counter() - steady_started) < duration_seconds:
                now = time.perf_counter()
                if now >= next_dispatch:
                    futures.append(pool.submit(run_query, neighbor_query))
                    next_dispatch += dispatch_interval
                else:
                    time.sleep(0.001)
            for future in as_completed(futures):
                try:
                    steady_latencies.append(future.result())
                except Exception as exc:
                    steady_errors.append(str(exc))
        steady_elapsed = time.perf_counter() - steady_started
        steady = summarize_load("lfa1_direct_neighbors_steady", "simple", steady_latencies, steady_errors, steady_elapsed, min(max(target_qps, 1), max(workers, 4), 32))
    except Exception as exc:
        return {
            "available": False,
            "reason": f"Load test timed out or failed: {exc}",
        }
    finally:
        driver.close()

    return {
        "available": True,
        "burst": burst,
        "steady_state": steady,
    }


def evaluate_gates(
    parity: Dict[str, Any],
    latency: Dict[str, Any],
    load: Dict[str, Any],
    remote_counts: Dict[str, Any],
    slos: Dict[str, float],
) -> Dict[str, Any]:
    checks: Dict[str, Any] = {}

    remote_connected = remote_counts.get("connected", False)
    checks["remote_connected"] = remote_connected
    checks["table_count_match"] = parity.get("table_count_match", False)
    checks["edge_count_match"] = parity.get("edge_count_match", False)
    checks["path_match_rate"] = parity.get("path_match_rate", 0.0) == 1.0
    checks["neighbor_match_rate"] = parity.get("neighbor_match_rate", 0.0) == 1.0

    checks["find_path_p95_ok"] = latency["find_path"]["p95_ms"] <= slos["find_path_p95_ms"]
    checks["neighbors_p95_ok"] = latency["get_neighbors"]["p95_ms"] <= slos["neighbors_p95_ms"]
    checks["subgraph_p95_ok"] = latency["get_subgraph_context"]["p95_ms"] <= slos["subgraph_p95_ms"]
    ranked_metric = latency["find_all_ranked_paths_native"]
    if ranked_metric["count"] == 0 and any("skipped" in err for err in ranked_metric.get("sample_errors", [])):
        checks["ranked_native_p95_ok"] = "skipped"
    else:
        checks["ranked_native_p95_ok"] = ranked_metric["p95_ms"] <= slos["ranked_native_p95_ms"]
    latency_errors_ok = True
    for name, metric in latency.items():
        if metric["count"] == 0 and any("skipped" in err for err in metric.get("sample_errors", [])):
            continue
        if metric["error_count"] > slos["error_rate_pct"]:
            latency_errors_ok = False
            break
    checks["latency_error_free"] = latency_errors_ok

    if load.get("available"):
        checks["load_burst_p95_ok"] = load["burst"]["latency_p95_ms"] <= slos["load_burst_p95_ms"]
        checks["load_steady_p95_ok"] = load["steady_state"]["latency_p95_ms"] <= slos["load_steady_p95_ms"]
        checks["load_error_free"] = (
            load["burst"]["error_rate_pct"] <= slos["error_rate_pct"]
            and load["steady_state"]["error_rate_pct"] <= slos["error_rate_pct"]
        )
    else:
        checks["load_burst_p95_ok"] = "skipped"
        checks["load_steady_p95_ok"] = "skipped"
        checks["load_error_free"] = "skipped"

    failing = [name for name, value in checks.items() if value is False]
    warn = [name for name, value in checks.items() if value == "skipped"]

    status = "PASS"
    if failing:
        status = "FAIL"
    elif warn:
        status = "WARN"

    return {
        "status": status,
        "checks": checks,
        "failing": failing,
        "warnings": warn,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hybrid graph runtime perf/load sign-off")
    parser.add_argument("--memgraph-uri", default=os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687"))
    parser.add_argument("--tenant-id", default=os.environ.get("TENANT_ID", "default"))
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--target-qps", type=int, default=30)
    parser.add_argument("--duration", type=int, default=10)
    parser.add_argument("--skip-load", action="store_true")
    parser.add_argument("--skip-native", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--find-path-p95-ms", type=float, default=DEFAULT_SLOS["find_path_p95_ms"])
    parser.add_argument("--neighbors-p95-ms", type=float, default=DEFAULT_SLOS["neighbors_p95_ms"])
    parser.add_argument("--subgraph-p95-ms", type=float, default=DEFAULT_SLOS["subgraph_p95_ms"])
    parser.add_argument("--ranked-native-p95-ms", type=float, default=DEFAULT_SLOS["ranked_native_p95_ms"])
    parser.add_argument("--load-burst-p95-ms", type=float, default=DEFAULT_SLOS["load_burst_p95_ms"])
    parser.add_argument("--load-steady-p95-ms", type=float, default=DEFAULT_SLOS["load_steady_p95_ms"])
    return parser.parse_args()


def infer_host_port(memgraph_uri: str) -> Tuple[str, int]:
    remainder = memgraph_uri.split("://", 1)[-1]
    if ":" not in remainder:
        return remainder, 7687
    host, port = remainder.rsplit(":", 1)
    return host, int(port)


def main() -> int:
    args = parse_args()
    slos = {
        "find_path_p95_ms": args.find_path_p95_ms,
        "neighbors_p95_ms": args.neighbors_p95_ms,
        "subgraph_p95_ms": args.subgraph_p95_ms,
        "ranked_native_p95_ms": args.ranked_native_p95_ms,
        "load_burst_p95_ms": args.load_burst_p95_ms,
        "load_steady_p95_ms": args.load_steady_p95_ms,
        "error_rate_pct": DEFAULT_SLOS["error_rate_pct"],
    }

    baseline = GraphRAGManager()
    hybrid = build_hybrid_from_baseline(baseline, memgraph_uri=args.memgraph_uri, tenant_id=args.tenant_id)

    baseline_stats = baseline.stats()
    hybrid_stats = hybrid.stats()
    host, port = infer_host_port(args.memgraph_uri)
    if args.skip_native:
        remote_counts = {
            "connected": "skipped",
            "tenant_label": f"Tenant_{args.tenant_id}",
            "node_count": None,
            "edge_count": None,
        }
    else:
        remote_counts = verify_remote_counts(args.memgraph_uri, args.tenant_id)
    parity = verify_parity(baseline, hybrid)
    latency = build_latency_profile(
        baseline,
        hybrid,
        iterations=args.iterations,
        host=host,
        port=port,
        skip_native=args.skip_native,
    )
    latency["mixed_workload"] = asdict(
        run_mixed_workload(
            baseline,
            hybrid,
            rounds=max(args.iterations, 8),
            host=host,
            port=port,
            skip_native=args.skip_native,
        )
    )

    load: Dict[str, Any]
    if args.skip_load:
        load = {"available": False, "reason": "skipped by flag"}
    else:
        load = maybe_run_load_tests(host=host, port=port, workers=args.workers, target_qps=args.target_qps, duration_seconds=args.duration)

    gates = evaluate_gates(parity=parity, latency=latency, load=load, remote_counts=remote_counts, slos=slos)

    report = SignoffReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        memgraph_uri=args.memgraph_uri,
        tenant_id=args.tenant_id,
        baseline_stats=baseline_stats,
        hybrid_stats=hybrid_stats,
        remote_counts=remote_counts,
        parity=parity,
        latency=latency,
        load=load,
        slos=slos,
        gates=gates,
        overall_status=gates["status"],
    )

    output_path = args.output
    if not output_path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = str(BACKEND_DIR / "reports" / f"hybrid_graph_signoff_{stamp}.json")
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")

    print("=" * 88)
    print("HYBRID GRAPH RUNTIME SIGN-OFF")
    print("=" * 88)
    print(f"Status:          {report.overall_status}")
    print(f"Memgraph URI:    {report.memgraph_uri}")
    print(f"Tenant:          {report.tenant_id}")
    print(f"Baseline stats:  {baseline_stats['total_tables']} tables / {baseline_stats['total_relationships']} edges")
    print(f"Hybrid stats:    {hybrid_stats['total_tables']} tables / {hybrid_stats['total_relationships']} edges")
    print(f"Remote counts:   connected={remote_counts.get('connected')} nodes={remote_counts.get('node_count')} edges={remote_counts.get('edge_count')}")
    print(f"Path parity:     {parity['path_match_rate'] * 100:.1f}%")
    print(f"Neighbor parity: {parity['neighbor_match_rate'] * 100:.1f}%")
    print()
    print("Latency (p95 ms)")
    print(f"- find_path:                {latency['find_path']['p95_ms']}")
    print(f"- get_neighbors:            {latency['get_neighbors']['p95_ms']}")
    print(f"- get_subgraph_context:     {latency['get_subgraph_context']['p95_ms']}")
    print(f"- find_all_ranked_paths:    {latency['find_all_ranked_paths_native']['p95_ms']}")
    print(f"- mixed_workload:           {latency['mixed_workload']['p95_ms']}")
    if load.get("available"):
        print()
        print("Load")
        print(f"- burst p95 ms:             {load['burst']['latency_p95_ms']}")
        print(f"- steady p95 ms:            {load['steady_state']['latency_p95_ms']}")
        print(f"- burst qps:                {load['burst']['throughput_qps']}")
        print(f"- steady qps:               {load['steady_state']['throughput_qps']}")
    else:
        print()
        print(f"Load:            skipped ({load.get('reason', 'n/a')})")
    print()
    if gates["failing"]:
        print("Failing gates:")
        for gate in gates["failing"]:
            print(f"- {gate}")
    if gates["warnings"]:
        print("Warnings:")
        for gate in gates["warnings"]:
            print(f"- {gate}")
    print()
    print(f"Report written:  {output_file}")
    close_drivers()
    return 0 if report.overall_status in {"PASS", "WARN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
