"""
load_init_schema.py — Load init_schema.cql into Memgraph via Bolt
==================================================================
Memgraph has NO docker-entrypoint-initdb.d support (PID 1 is the DB itself).
This script loads the full 83-node / 100+ edge schema via gqlalchemy Bolt client.

Usage:
    cd backend
    .\.venv\Scripts\python.exe load_init_schema.py

    # Or from project root:
    docker compose -f docker/docker-compose.memgraph.yml exec memgraph \
      mgclient -u "" -p "" -f /docker-entrypoint-initdb.d/01-schema.cql
    # (mgclient not available in this image — use the Python approach above)
"""
import sys as _sys
_sys.path.insert(0, ".venv\\Lib\\site-packages")

from gqlalchemy import Memgraph
import os
import time

# Resolve relative to this script's location
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(_SCRIPT_DIR, ".."))
SCHEMA_PATH = os.path.join(PROJECT_ROOT, "docker", "memgraph", "init_schema.cql")
MEMGRAPH_URI = "127.0.0.1"
MEMGRAPH_PORT = 7687


def wait_for_memgraph(uri=MEMGRAPH_URI, port=MEMGRAPH_PORT, timeout=30):
    """Poll until Memgraph is reachable."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            mg = Memgraph(uri, port)
            list(mg.execute_and_fetch("RETURN 1"))
            return mg
        except Exception:
            time.sleep(1)
    raise RuntimeError(f"Memgraph not available at {uri}:{port} after {timeout}s")


def load_schema(mg: Memgraph, dry_run=False):
    """Parse and execute init_schema.cql, reporting progress and errors."""
    schema_path = SCHEMA_PATH
    if not os.path.exists(schema_path):
        raise FileNotFoundError(f"init_schema.cql not found at {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Strip full-line comments, build executable statements
    # (inline -- comments inside a statement are preserved; blank/comment-only lines are skipped)
    statements = []
    buf = []
    for line in raw.splitlines():
        stripped = line.strip()
        # Skip blank lines and full-line comment lines
        if not stripped:
            continue
        full_comment = stripped.startswith("--")
        if full_comment:
            continue
        buf.append(stripped)
        if stripped.endswith(";"):
            statements.append(" ".join(buf))
            buf = []

    print(f"Loaded {len(statements)} statements from init_schema.cql")

    errors = []
    for i, stmt in enumerate(statements):
        stmt = stmt.strip()
        if not stmt:
            continue
        try:
            mg.execute(stmt)
            if (i + 1) % 20 == 0:
                print(f"  ... {i + 1}/{len(statements)} statements executed")
        except Exception as e:
            errors.append((i, stmt[:80], str(e)[:100]))

    return errors


def main():
    print("=" * 60)
    print("  Memgraph Schema Loader")
    print("=" * 60)

    print(f"\n[1] Waiting for Memgraph at {MEMGRAPH_URI}:{MEMGRAPH_PORT}...")
    mg = wait_for_memgraph()
    print("    ✅ Memgraph is ready")

    # Check existing data
    existing = list(mg.execute_and_fetch(
        "MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS n"
    ))
    node_count = existing[0]["n"]
    print(f"\n[2] Existing nodes in graph: {node_count}")

    if node_count >= 80:
        print("    ✅ Schema already loaded (80+ nodes). Skipping load.")
        return

    print(f"\n[3] Loading schema from init_schema.cql...")
    errors = load_schema(mg)

    # Final verification
    nodes_after = list(mg.execute_and_fetch(
        "MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS n"
    ))
    edges_after = list(mg.execute_and_fetch(
        "MATCH ()-[r]->() RETURN count(r) AS e"
    ))

    n_nodes = nodes_after[0]["n"]
    n_edges = edges_after[0]["e"]

    print(f"\n[4] Verification:")
    print(f"    Nodes: {n_nodes} (expected: 80+)")
    print(f"    Edges: {n_edges} (expected: 100+)")
    print(f"    Errors: {len(errors)}")

    if errors:
        print(f"\n    Errors ({len(errors)}):")
        for i, stmt, err in errors[:5]:
            print(f"      [{i}] {stmt}")
            print(f"           → {err}")

    if n_nodes >= 80 and n_edges >= 100:
        print("\n" + "=" * 60)
        print("  ✅ Schema loaded successfully")
        print("=" * 60)
    elif n_nodes >= 80:
        print("\n⚠️  Nodes loaded but edges low — run again or check above errors")
    else:
        print("\n❌ Schema load failed — check errors above")
        _sys.exit(1)


if __name__ == "__main__":
    main()
