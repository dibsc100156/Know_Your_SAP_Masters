"""
smoke_test_memgraph.py — Phase M1 Smoke Test
============================================
Full end-to-end test for Memgraph Phase M1.
Verifies: Memgraph is up, schema loaded, adapter works, traversals pass.

Usage:
    python smoke_test_memgraph.py

    (Run from the scripts/ directory or project root.
     Uses __file__ to resolve paths correctly.)
"""
import sys
import os

# ── Resolve paths relative to this script ──────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "backend"))
APP_CORE = os.path.join(BACKEND_DIR, "app", "core")

sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, APP_CORE)


def run_smoke_test():
    print("=" * 60)
    print("  Memgraph Phase M1 Smoke Test")
    print("=" * 60)

    # ── 1. Check Memgraph connectivity ──────────────────────────────────────
    print("\n[1] Connecting to Memgraph...")
    try:
        from gqlalchemy import Memgraph
    except ImportError:
        print("❌ gqlalchemy not installed.")
        print("   → cd backend && pip install -r requirements-memgraph.txt")
        return False

    try:
        mg = Memgraph("127.0.0.1", 7687)
        list(mg.execute_and_fetch("RETURN 1"))
        print("   ✅ Connected to Memgraph on bolt://127.0.0.1:7687")
    except Exception as e:
        print(f"❌ Cannot connect: {e}")
        print("   → docker compose -f docker/docker-compose.memgraph.yml up memgraph lab -d")
        return False

    # ── 2. Load schema if needed ─────────────────────────────────────────────
    n_nodes = list(mg.execute_and_fetch(
        "MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS n"
    ))[0]["n"]
    n_edges = list(mg.execute_and_fetch(
        "MATCH ()-[r]->() RETURN count(r) AS e"
    ))[0]["e"]
    print(f"\n[2] Graph state: {n_nodes} nodes, {n_edges} edges")

    if n_nodes < 80:
        print(f"   ⚠ Only {n_nodes} nodes — loading schema via Bolt...")
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "load_init_schema",
                os.path.join(SCRIPT_DIR, "load_init_schema.py"),
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            print(f"   ❌ load_init_schema.py failed: {e}")
            return False
        n_nodes = list(mg.execute_and_fetch(
            "MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS n"
        ))[0]["n"]
        n_edges = list(mg.execute_and_fetch(
            "MATCH ()-[r]->() RETURN count(r) AS e"
        ))[0]["e"]
        print(f"   After load: {n_nodes} nodes, {n_edges} edges")
    else:
        print(f"   ✅ Schema already loaded ({n_nodes} nodes)")

    # ── 3. Test MemgraphGraphRAGManager adapter ───────────────────────────────
    print("\n[3] Testing MemgraphGraphRAGManager drop-in...")
    try:
        from memgraph_adapter import MemgraphGraphRAGManager
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        print("   → cd backend && pip install -r requirements-memgraph.txt")
        return False

    try:
        graph = MemgraphGraphRAGManager(
            uri="bolt://127.0.0.1:7687",
            load_on_init=True,
        )
        print(f"   ✅ Adapter created. Memgraph connected: {graph._is_connected}")
    except Exception as e:
        print(f"   ❌ Adapter creation failed: {e}")
        return False

    stats = graph.stats()
    print(f"   Stats: {stats['total_tables']} tables, "
          f"{stats['total_relationships']} relationships, "
          f"{stats.get('cross_module_bridges', '?')} cross-module bridges")

    # ── 4. Traversal tests ───────────────────────────────────────────────────
    print("\n[4] Testing graph traversals...")
    test_cases = [
        ("MARA",  "LFA1",  "Material → Vendor"),
        ("MARA",  "KNA1",  "Material → Customer"),
        ("LFA1",  "BKPF",  "Vendor → FI Document"),
        ("MARA",  "QALS",  "Material → Inspection Lot"),
        ("LFA1",  "EKKO",  "Vendor → PO"),
        ("VBAK",  "VBRK",  "Sales Order → Billing"),
        ("MARA",  "MARD",  "Material → Storage Location"),
    ]

    all_pass = True
    for start, end, desc in test_cases:
        path = graph.find_path(start, end)
        if path:
            print(f"   ✅ {start} → {end}  ({desc})")
            print(f"      Path: {' → '.join(path)}")
        else:
            print(f"   ❌ {start} → {end}: NO PATH FOUND")
            all_pass = False

    # ── 5. .G property backward compat ───────────────────────────────────────
    print("\n[5] Testing .G backward compatibility...")
    try:
        nodes_list = list(graph.G.nodes)
        edges_list = list(graph.G.edges)
        print(f"   ✅ graph.G.nodes: {len(nodes_list)} nodes")
        print(f"   ✅ graph.G.edges: {len(edges_list)} edges")
        assert "MARA" in nodes_list, "MARA missing"
        assert "LFA1" in nodes_list, "LFA1 missing"
    except Exception as e:
        print(f"   ❌ .G compat failed: {e}")
        all_pass = False

    # ── 6. use_memgraph() factory ────────────────────────────────────────────
    print("\n[6] Testing use_memgraph() factory...")
    try:
        from app.core import use_memgraph, MEMGRAPH_GRAPH_STORE
        print(f"   ✅ use_memgraph() imported")
        if MEMGRAPH_GRAPH_STORE is not None:
            print(f"   ✅ MEMGRAPH_GRAPH_STORE global already set")
        else:
            print(f"   ⚠ MEMGRAPH_GRAPH_STORE is None (call use_memgraph() in main.py)")
    except Exception as e:
        print(f"   ⚠ use_memgraph() check skipped: {e}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if all_pass:
        print("  ✅ ALL CHECKS PASSED — Phase M1 COMPLETE")
        print("=" * 60)
        print(f"\n  Graph: {n_nodes} nodes, {n_edges} edges in Memgraph")
        print("  Memgraph Lab: http://localhost:3000")
        print("\nNext steps:")
        print("  Phase M2: Wire use_memgraph() into main.py startup")
        print("  Phase M3: Run benchmark against Memgraph-backed graph")
        return True
    else:
        print("  ❌ SOME CHECKS FAILED — see above")
        print("=" * 60)
        return False


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
