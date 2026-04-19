"""
benchmark_50.py — Full 50-query benchmark across 16 domains, 4 roles
Tests all previously failing seeds + general coverage
"""
import requests, json, time, sys
from collections import defaultdict

API_BASE = "http://localhost:8000/api/v1"

HEADERS = {
    "Content-Type": "application/json",
    "X-Session-ID": "bench-50-full",
}

# 50 queries across 16 domains
QUERIES = [
    # VENDOR (8)
    ("vendor payment terms for company code 1010", "AP_CLERK"),
    ("vendor open POs above 50000", "AP_CLERK"),
    ("vendor master with bank details", "AP_CLERK"),
    ("vendor quality rating for top suppliers", "AP_CLERK"),
    ("supplier inspection results last quarter", "AP_CLERK"),
    ("vendor financial exposure current year", "AP_CLERK"),
    ("blocked vendors in purchasing org", "AP_CLERK"),
    ("vendor lifnr and name for company code 1010", "AP_CLERK"),
    # CUSTOMER (5)
    ("customer credit limit for company code 1010", "SD_CLERK"),
    ("customer open items and reconciliation", "SD_CLERK"),
    ("customer sales history last 3 years", "SD_CLERK"),
    ("customer payment terms and dunning", "SD_CLERK"),
    ("customer tax numbers for india", "SD_CLERK"),
    # PURCHASING (5)
    ("purchase order history for vendor v1000", "MM_CLERK"),
    ("info records for material mat001", "MM_CLERK"),
    ("contract details for purchasing org 1010", "MM_CLERK"),
    ("source list for plant 1010 material", "MM_CLERK"),
    ("rfq pending for vendor list", "MM_CLERK"),
    # MATERIAL (6)
    ("material stock quantities at plant 1010", "MM_CLERK"),
    ("material valuation and price control", "MM_CLERK"),
    ("material type classification for all raw materials", "MM_CLERK"),
    ("material availability check for sales order", "MM_CLERK"),
    ("material cost rollup for finished goods", "MM_CLERK"),
    ("material stock in transit between plants", "MM_CLERK"),
    # FINANCE (4)
    ("gl account balances for company code 1010 current period", "FI_ACCOUNTANT"),
    ("cost center actual vs budget", "FI_ACCOUNTANT"),
    ("profit center revenue analysis", "FI_ACCOUNTANT"),
    ("journals posted in last 7 days", "FI_ACCOUNTANT"),
    # SALES (4)
    ("sales order backlog for region east", "SD_CLERK"),
    ("delivery status for pending orders", "SD_CLERK"),
    ("billing documents pending payment", "SD_CLERK"),
    ("sales volume by customer last quarter", "SD_CLERK"),
    # QUALITY (3)
    ("quality inspection lots for plant 1010 last month", "MM_CLERK"),
    ("quality notifications open for material mat001", "MM_CLERK"),
    ("vendor quality scorecard for top 10 suppliers", "AP_CLERK"),
    # PROJECT (2)
    ("wbs element cost overrun for project ps001", "MM_CLERK"),
    ("project milestones and budget consumption", "MM_CLERK"),
    # BUDGET (2)
    ("budget vs actual for cost center cc001", "FI_ACCOUNTANT"),
    ("annual budget distribution by department", "FI_ACCOUNTANT"),
    # HR (2)
    ("employee headcount by organizational unit", "AP_CLERK"),
    ("personnel area and employee group data", "AP_CLERK"),
    # TAX (2)
    ("india tax codes and rates for gst", "FI_ACCOUNTANT"),
    ("tax jurisdiction determination for state maharashtra", "FI_ACCOUNTANT"),
    # TRANSPORTATION (2)
    ("transportation lane from vendor to plant 1010", "MM_CLERK"),
    ("freight cost analysis for inbound deliveries", "MM_CLERK"),
    # WAREHOUSE (2)
    ("storage bin capacity and utilization at plant 1010", "MM_CLERK"),
    ("inventory movement in warehouse 001 last week", "MM_CLERK"),
    # MASTER DATA (1)
    ("general data for business partner master", "AP_CLERK"),
    # GTS - EIGER (1) - the seed_fail_010 query
    ("goods in transit status for vendor v1000 purchase orders", "MM_CLERK"),
    # QM (1)
    ("inspection results and usage decision for material mat001", "MM_CLERK"),
]

def run_query(query, role_id):
    payload = {
        "query": query,
        "role_id": role_id,
        "tenant_id": "DEFAULT",
    }
    t0 = time.time()
    try:
        r = requests.post(f"{API_BASE}/chat/master-data", json=payload, headers=HEADERS, timeout=30)
        elapsed_ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return {"status": "HTTP_ERROR", "code": r.status_code, "elapsed_ms": elapsed_ms, "error": str(r.text[:100])}
        data = r.json()
        tables = data.get("tables_used", [])
        sql = data.get("sql_generated", "")
        confidence = data.get("confidence_score", {})
        composite = confidence.get("composite") if isinstance(confidence, dict) else confidence
        exec_ms = data.get("execution_time_ms", 0)
        self_heal = data.get("self_heal", {})
        critique = data.get("critique", {})
        sentinel = data.get("sentinel", {}) or {}
        return {
            "status": "PASS" if r.status_code == 200 else "FAIL",
            "code": r.status_code,
            "elapsed_ms": elapsed_ms,
            "exec_ms": exec_ms,
            "tables": tables[:6],
            "sql": sql[:80],
            "confidence": composite,
            "heal_applied": self_heal.get("applied", False),
            "heal_code": self_heal.get("code"),
            "critique_passed": critique.get("passed", False),
            "sentinel_verdict": sentinel.get("verdict") if sentinel else None,
        }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return {"status": "ERROR", "elapsed_ms": elapsed_ms, "error": str(e)[:100]}

def run_benchmark():
    print("=" * 70)
    print("  SAP MASTERS 50-QUERY BENCHMARK")
    print("=" * 70)
    results = []
    for i, (query, role) in enumerate(QUERIES, 1):
        print(f"[{i:02d}/50] {query[:60]}... ({role})", end=" ", flush=True)
        r = run_query(query, role)
        results.append((query, role, r))
        status = r.get("status", "?")
        elapsed = r.get("elapsed_ms", 0)
        confidence = r.get("confidence", "N/A")
        heal = r.get("heal_code", "")
        sentinel = r.get("sentinel_verdict", "")
        print(f"→ {status} | {elapsed}ms | conf={confidence} | heal={heal or '-'} | sent={sentinel or '-'}")

    # Summary
    total = len(results)
    passed = sum(1 for _, _, r in results if r.get("status") == "PASS")
    errors = sum(1 for _, _, r in results if r.get("status") == "ERROR")
    http_err = sum(1 for _, _, r in results if r.get("status") == "HTTP_ERROR")
    crit_fails = sum(1 for _, _, r in results if r.get("critique_passed") == False and r.get("status") == "PASS")
    heals_applied = sum(1 for _, _, r in results if r.get("heal_applied", False) == True)
    avg_confidence = sum(r.get("confidence", 0) or 0 for _, _, r in results if r.get("confidence")) / max(1, passed)

    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Total queries : {total}")
    print(f"  PASS          : {passed}/{total} ({100*passed//total}%)")
    print(f"  FAIL          : {total - passed}")
    print(f"  HTTP errors   : {http_err}")
    print(f"  Crit fails    : {crit_fails}")
    print(f"  Heals applied : {heals_applied}")
    print(f"  Avg confidence: {avg_confidence:.3f}")
    print()

    # Failed queries
    failed = [(q, r) for q, _, r in results if r.get("status") not in ("PASS",)]
    if failed:
        print("  FAILED QUERIES:")
        for q, r in failed:
            print(f"  - [{r.get('status')}] {q[:60]}")
            if r.get("error"):
                print(f"    Error: {r['error']}")

    print("=" * 70)

    # Save results
    with open(r"C:\Users\vishnu\.openclaw\workspace\benchmark_results_50.json", "w") as f:
        json.dump([{"query": q, "role": role, "result": r} for q, role, r in results], f, indent=2, default=str)
    print(f"\n  Results saved to benchmark_results_50.json")

if __name__ == "__main__":
    run_benchmark()