"""
bolt_load.py — Load init_schema.cql into Memgraph via neo4j Bolt driver
======================================================================
Uses the neo4j Python driver (Bolt protocol compatible with Memgraph).
Bypasses gqlalchemy which has a broken torch dependency on Windows.

Usage:
    python bolt_load.py
"""
import os
import time
from neo4j import GraphDatabase

HOST = "127.0.0.1"
PORT = 7687
URI = f"bolt://{HOST}:{PORT}"
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "docker", "memgraph", "init_schema.cql")
SCHEMA_PATH = os.path.abspath(SCHEMA_PATH)


def wait_for_memgraph(driver, timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with driver.session() as s:
                list(s.run("RETURN 1"))
            return True
        except Exception:
            time.sleep(1)
    raise RuntimeError("Memgraph not available")


def load_schema(driver):
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        raw = f.read()

    # Parse into executable statements (skip full-line comments and blanks)
    statements = []
    buf = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(stripped)
        if stripped.endswith(";"):
            statements.append(" ".join(buf))
            buf = []

    print(f"Loaded {len(statements)} statements from init_schema.cql")

    errors = []
    with driver.session() as s:
        # Check existing
        result = list(s.run("MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS n"))
        existing = result[0]["n"]
        print(f"Existing nodes: {existing}")

        for i, stmt in enumerate(statements):
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                s.run(stmt)
                if (i + 1) % 20 == 0:
                    print(f"  ... {i + 1}/{len(statements)} statements executed")
            except Exception as e:
                err_str = str(e)[:100]
                errors.append((i, stmt[:70], err_str))

        # Verify
        result_nodes = list(s.run("MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS n"))
        result_edges = list(s.run("MATCH ()-[r]->() RETURN count(r) AS e"))

        n_nodes = result_nodes[0]["n"]
        n_edges = result_edges[0]["e"]

        print(f"\nVerification:")
        print(f"    Nodes: {n_nodes} (expected: 80+)")
        print(f"    Edges: {n_edges} (expected: 100+)")
        print(f"    Errors: {len(errors)}")

        if errors:
            print(f"\n    Errors ({len(errors)}):")
            for i, stmt, err in errors[:5]:
                print(f"      [{i}] {stmt}")
                print(f"               → {err}")

        return n_nodes, n_edges, errors


def main():
    print("=" * 60)
    print("  Memgraph Schema Loader (neo4j Bolt)")
    print("=" * 60)

    driver = GraphDatabase.driver(URI)

    print(f"\n[1] Waiting for Memgraph at {URI}...")
    wait_for_memgraph(driver)
    print("    ✅ Memgraph is ready")

    print(f"\n[2] Loading schema from init_schema.cql...")
    n_nodes, n_edges, errors = load_schema(driver)

    if not errors and n_nodes >= 80 and n_edges >= 100:
        print("\n" + "=" * 60)
        print("  ✅ Schema loaded successfully")
        print("=" * 60)
    elif n_nodes >= 80:
        print("\n⚠️  Nodes loaded but edges low")
    else:
        print("\n❌ Schema load failed")

    driver.close()


if __name__ == "__main__":
    main()
