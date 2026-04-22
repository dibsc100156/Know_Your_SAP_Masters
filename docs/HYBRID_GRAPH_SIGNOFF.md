# Hybrid Graph Runtime Perf/Load Sign-Off
**Created:** 2026-04-22
**Purpose:** Operational sign-off procedure for the Memgraph + NetworkX hybrid graph runtime.

---

## What this signs off
This sign-off covers the remaining roadmap item:
- **Hybrid graph runtime perf/load sign-off**

It validates four things:
1. **Connectivity** — Memgraph is reachable
2. **Parity** — hybrid runtime matches baseline NetworkX behavior for key graph APIs
3. **Latency** — main graph operations stay inside agreed p95 budgets
4. **Load** — Memgraph holds up under burst and steady-state query pressure

---

## Script
Use:
- `backend/hybrid_graph_signoff.py`

The script emits a JSON report and returns a non-zero exit code on sign-off failure.

---

## Prerequisites
- Memgraph is running and loaded
- Hybrid runtime can connect via `MEMGRAPH_URI`
- Existing graph metadata is available in code
- Optional but recommended: `mgclient` installed so raw Memgraph load tests can run

---

## Quick run
### Windows PowerShell
```powershell
cd backend
.\.venv\Scripts\python.exe .\hybrid_graph_signoff.py
```

### With explicit settings
```powershell
cd backend
$env:MEMGRAPH_URI = "bolt://localhost:7687"
$env:TENANT_ID = "default"
.\.venv\Scripts\python.exe .\hybrid_graph_signoff.py --iterations 25 --workers 10 --target-qps 40 --duration 15
```

### If you want parity/latency only
```powershell
cd backend
.\.venv\Scripts\python.exe .\hybrid_graph_signoff.py --skip-load
```

---

## What gets measured

### Parity checks
- table count match
- edge count match
- shortest-path parity across representative SAP table pairs
- neighbor traversal parity across representative cases

### Latency checks
- `find_path()`
- `get_neighbors()`
- `get_subgraph_context()`
- `find_all_ranked_paths_native()`
- mixed parallel workload over the hybrid API surface

### Load checks
Reuses `backend/memgraph_load_test.py` when available:
- burst load p95
- steady-state load p95
- throughput (QPS)
- error rate

---

## Default SLOs
- `find_path` p95 <= **3 ms**
- `get_neighbors` p95 <= **5 ms**
- `get_subgraph_context` p95 <= **6 ms**
- `find_all_ranked_paths_native` p95 <= **40 ms**
- burst load p95 <= **60 ms**
- steady-state load p95 <= **80 ms**
- error rate = **0%**

Tune these with CLI flags if production targets change.

---

## PASS / WARN / FAIL meaning
- **PASS** — parity holds, latency SLOs pass, and load checks pass
- **WARN** — core checks passed but one or more optional load checks were skipped
- **FAIL** — parity broke, Memgraph was unreachable, or SLOs were exceeded

---

## Output
By default, reports are written to:
- `backend/reports/hybrid_graph_signoff_<timestamp>.json`

Keep the latest sign-off report as evidence before marking the punch-list item complete.

---

## Suggested sign-off workflow
1. Run `smoke_test_memgraph.py`
2. Run `hybrid_graph_signoff.py --skip-load`
3. Run full `hybrid_graph_signoff.py`
4. Archive the JSON report
5. Update:
   - `docs/LEVEL5_ROADMAP.md`
   - `docs/LEVEL5_PUNCHLIST.md`
   - any ops/perf notes if thresholds changed

---

## Completion rule for punch list
You can close **Hybrid graph runtime perf/load sign-off** when:
- Memgraph connectivity is stable
- parity checks are 100%
- p95 latency targets are met
- load tests complete without errors
- the JSON sign-off report is archived and referenced in docs
