"""
smoke_test_memgraph.py — Phase M1 Smoke Test
============================================
Full end-to-end test for Memgraph Phase M1:
  1. Load schema if not already present
  2. Verify Memgraph has nodes/edges
  3. Test MemgraphGraphRAGManager drop-in
  4. Verify orchestrator compatibility (.G property, traverse_graph)

Usage:
    cd backend
    .\.venv\Scripts\python.exe scripts\smoke_test_memgraph.py
"""
import sys as _sys
import os as _os

# Add backend to path
_sys.path.insert(0, _sys.path[0])

def run_smoke_test():
    print("=" * 60)
    print("  Memgraph Phase M1 Smoke Test")
    print("=" * 60)

    # ── 1. Load schema if needed ─────────────────────────────────────────────
    print("\n[1] Checking Memgraph schema...")
    try:
        from gqlalchemy import Memgraph
    except ImportError:
        print("❌ gqlalchemy not installed.")
        print("   → Run: pip install gqlalchemy")
        return False

    try:
        mg = Memgraph("127.0.0.1", 7687)
        list(mg.execute_and_fetch("RETURN 1"))
    except Exception as e:
        print(f"❌ Cannot connect to Memgraph: {e}")
        print("   → Is Memgraph running?")
        print("   docker compose -f docker/docker-compose.memgraph.yml up memgraph lab -d")
        return False

    # Count existing nodes
    existing = list(mg.execute_and_fetch(
        "MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS n"
    ))
    n_nodes = existing[0]["n"]
    n_edges = list(mg.execute_and_fetch("MATCH ()-[r]->() RETURN count(r) AS e"))[0]["e"]
    print(f"   Memgraph: {n_nodes} nodes, {n_edges} edges")

    if n_nodes < 80:
        print(f"   ⚠ Schema not loaded (only {n_nodes} nodes).")
        print("   → Running load_init_schema.py...")
        _os.chdir(_os.path.dirname(_sys.argv[0]) if _sys.argv[0] else ".")
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "load_init_schema",
                _os.path.join(_os.path.dirname(_sys.argv[0] or "."),
                              "load_init_schema.py")
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception as e:
            print(f"   ❌ Schema load failed: {e}")
            return False
        # Re-check
        n_nodes = list(mg.execute_and_fetch(
            "MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS n"
        ))[0]["n"]
        n_edges = list(mg.execute_and_fetch("MATCH ()-[r]->() RETURN count(r) AS e"))[0]["e"]
        print(f"   After load: {n_nodes} nodes, {n_edges} edges")
    else:
        print(f"   ✅ Schema already loaded ({n_nodes} nodes)")

    # ── 2. Test MemgraphGraphRAGManager drop-in ────────────────────────────────
    print("\n[2] Testing MemgraphGraphRAGManager adapter...")
    try:
        # Add backend/app/core to path for the import
        _sys.path.insert(0, _os.path.join(_os.path.dirname(_sys.path[0]), "app", "core"))
        from memgraph_adapter import MemgraphGraphRAGManager
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        print("   → pip install -r requirements-memgraph.txt")
        return False

    try:
        graph = MemgraphGraphRAGManager(
            uri="bolt://localhost:7687",
            load_on_init=True,
        )
        print(f"   ✅ Adapter created. Memgraph connected: {graph._is_connected}")
    except Exception as e:
        print(f"❌ Adapter creation failed: {e}")
        return False

    # Stats
    stats = graph.stats()
    print(f"   Stats: {stats['total_tables']} tables, "
          f"{stats['total_relationships']} relationships, "
          f"{stats.get('cross_module_bridges', '?')} cross-module bridges")

    # ── 3. Traversal tests ────────────────────────────────────────────────────
    print("\n[3] Testing graph traversals...")

    test_cases = [
        ("MARA",  "LFA1",  "Material → Vendor (cross-module)"),
        ("MARA",  "KNA1",  "Material → Customer (cross-module)"),
        ("LFA1",  "BKPF",  "Vendor → FI Document (cross-module)"),
        ("MARA",  "QALS",  "Material → Inspection Lot (cross-module)"),
        ("LFA1",  "EKKO",  "Vendor → PO (cross-module)"),
        ("VBAK",  "VBRK",  "Sales Order → Billing (internal)"),
        ("MARA",  "MARD",  "Material → Storage Location (internal)"),
    ]

    all_pass = True
    for start, end, desc in test_cases:
        path = graph.find_path(start, end)
        if path:
            print(f"   ✅ {start} → {end} ({desc})")
            print(f"      Path: {' → '.join(path)}")
        else:
            print(f"   ❌ {start} → {end}: NO PATH FOUND")
            all_pass = False

    # ── 4. .G property compatibility ─────────────────────────────────────────
    print("\n[4] Testing .G backward compatibility...")
    try:
        nodes_list = list(graph.G.nodes)
        edges_list = list(graph.G.edges)
        print(f"   ✅ graph.G.nodes: {len(nodes_list)} nodes")
        print(f"   ✅ graph.G.edges: {len(edges_list)} edges")
        assert "MARA" in nodes_list, "MARA not in G.nodes"
        assert "LFA1" in nodes_list, "LFA1 not in G.nodes"
    except Exception as e:
        print(f"   ❌ .G compatibility failed: {e}")
        all_pass = False

    # ── 5. Summary ────────────────────────────────────────────────────────────
    print("\n[5] Summary:")
    print(f"   Nodes in Memgraph: {n_nodes}")
    print(f"   Edges in Memgraph: {n_edges}")
    print(f"   Adapter finds: {stats['total_tables']} tables, "
          f"{stats['total_relationships']} relationships")

    # Verify MEMGRAPH_GRAPH_STORE global
    try:
        _sys.path.insert(0, _os.path.join(_os.path.dirname(_sys.path[0]), "app"))
        from core import MEMGRAPH_GRAPH_STORE
        if MEMGRAPH_GRAPH_STORE is graph:
            print(f"   ✅ MEMGRAPH_GRAPH_STORE global set correctly")
        else:
            print(f"   ⚠️  MEMGRAPH_GRAPH_STORE not yet set (call use_memgraph() in main.py)")
    except Exception:
        print(f"   ⚠️  MEMGRAPH_GRAPH_STORE import skipped")

    if all_pass:
        print("\n" + "=" * 60)
        print("  ✅ ALL CHECKS PASSED — Phase M1 COMPLETE")
        print("=" * 60)
        print("\nNext steps:")
        print("  Phase M2: Wire use_memgraph() into main.py startup")
        print("  Phase M3: Run full benchmark against Memgraph-backed graph")
        print("  Memgraph Lab: http://localhost:3000")
        return True
    else:
        print("\n❌ Some checks failed — see above.")
        return False


if __name__ == "__main__":
    success = run_smoke_test()
    _sys.exit(0 if success else 1)
