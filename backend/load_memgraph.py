"""
load_memgraph.py — Memgraph Schema Loader
==========================================
Properly loads the SAP enterprise schema graph into Memgraph.
Handles multi-line CQL statements correctly (no semicolon-split breakage).
Handles relationship direction: adds both directions for cross-module FKs.

Usage:
    python load_memgraph.py [--host 127.0.0.1] [--port 7687] [--drop-first]

    # With Docker:
    docker exec -i sap-masters-memgraph python /load_memgraph.py
"""
import re, sys, os, argparse
from gqlalchemy import Memgraph

def load_schema(host="127.0.0.1", port=7687, drop_first=False):
    mg = Memgraph(host=host, port=port)
    cql_path = os.path.join(os.path.dirname(__file__), "..", "docker", "memgraph", "init_schema.cql")
    if not os.path.exists(cql_path):
        # Try relative to this file
        cql_path = os.path.join(os.path.dirname(__file__), "docker", "memgraph", "init_schema.cql")

    with open(cql_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Remove comments
    cleaned = re.sub(r'--[^\n]*', '', raw)
    cleaned = re.sub(r'//[^\n]*', '', cleaned)

    # Split preserving multi-line statements
    lines = cleaned.split("\n")
    statements = []
    current = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        current.append(line)
        if stripped.endswith(";"):
            stmt = "\n".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []

    print(f"Total statements: {len(statements)}")

    if drop_first:
        print("Dropping existing graph...")
        list(mg.execute_and_fetch("MATCH (n) DETACH DELETE n;"))
        list(mg.execute_and_fetch("DROP INDEX ON :SAPTable(table_name);"))
        list(mg.execute_and_fetch("DROP INDEX ON :SAPTable(module);"))
        print("Existing graph dropped.")

    errors = []
    success = 0
    for stmt in statements:
        stmt = stmt.strip()
        if not stmt or not stmt.endswith(";"):
            continue
        try:
            list(mg.execute_and_fetch(stmt))
            success += 1
        except Exception as e:
            err = str(e)
            if "already exists" in err.lower():
                success += 1  # MERGE is idempotent
            else:
                errors.append((stmt[:80], err[:80]))

    print(f"Executed: {success}/{len(statements)}")
    if errors:
        print(f"Errors ({len(errors)}):")
        for s, e in errors[:5]:
            print(f"  STMT: {s}")
            print(f"  ERR:  {e}")
    else:
        print("No errors!")

    # Add bidirectional edges for cross-module FKs
    # (The CQL init creates only one direction; Memgraph needs both for undirected traversal)
    add_bidirectional_edges(mg)

    # Verify
    nodes = list(mg.execute_and_fetch(
        "MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS cnt"
    ))
    edges = list(mg.execute_and_fetch(
        "MATCH (a)-[r]->(b) WHERE 'SAPTable' IN labels(a) AND 'SAPTable' IN labels(b) RETURN count(r) AS cnt"
    ))
    print(f"Graph loaded: {nodes[0]['cnt']} nodes, {edges[0]['cnt']} edges")

    # Test key paths
    path_test = [
        ("MARA", "LFA1", "Material to Vendor"),
        ("KNA1", "BSEG", "Customer to FI"),
        ("BUT000", "LFA1", "BP Central to Vendor"),
    ]
    print("\nPath tests:")
    for src, tgt, desc in path_test:
        path = list(mg.execute_and_fetch(
            f"MATCH path = (a)-[:FOREIGN_KEY*1..5]->(b) "
            f"WHERE a.table_name = '{src}' AND b.table_name = '{tgt}' "
            f"RETURN [n IN nodes(path) | n.table_name] AS tables LIMIT 1"
        ))
        status = "OK" if path else "FAIL"
        print(f"  {status} {desc}: {src} -> {tgt}: {path[0]['tables'] if path else 'no path'}")

def add_bidirectional_edges(mg):
    """Add reverse-direction edges for all cross-module FK relationships."""
    # These are critical bidirectional edges for cross-module traversal
    bidirectional = [
        ("EINA", "LFA1", "EINA.LIFNR = LFA1.LIFNR", "N:1", "cross_module", "Info Record -> Vendor"),
        ("MARA", "MSLB", "MARA.MATNR = MSLB.MATNR", "1:N", "cross_module", "Material -> Vendor-owned stock"),
        ("MARA", "LQUA", "MARA.MATNR = LQUA.MATNR", "1:N", "cross_module", "Material -> WM Quant"),
        ("MARA", "EKKO", "MARA.MATNR = EKKO.MATNR", "N:1", "cross_module", "Material -> PO"),
        ("LQUA", "LAGP", "LQUA.MATNR = LAGP.WERKS AND LQUA.LGORT = LAGP.LGTYP", "N:1", "cross_module", "Quant -> Storage Type"),
        ("QALS", "EKKO", "QALS.MATNR = EKKO.MATNR", "N:1", "cross_module", "QM Lot -> PO"),
        ("MKOL", "PRPS", "MKOL.OBJNR = PRPS.OBJNR", "N:1", "cross_module", "Proj stock -> WBS"),
        ("MSKA", "KNA1", "MSKA.KUNNU = KNA1.KUNNR", "N:1", "cross_module", "SO stock -> Customer"),
        ("LFA1", "KNA1", "LFA1.LIFNR = KNA1.KUNNR", "N:1", "cross_module", "Vendor/Customer cross-type"),
        ("VTTK", "LFA1", "VTTK.LIFNR = LFA1.LIFNR", "N:1", "cross_module", "Shipment -> Carrier vendor"),
        ("QAVE", "LFA1", "QAVE.LIFNR = LFA1.LIFNR", "N:1", "cross_module", "QM UD -> Vendor"),
        ("ANEP", "ANLA", "ANEP.ANLN1 = ANLA.ANLN1 AND ANEP.BUKRS = ANLA.BUKRS", "1:N", "cross_module", "Asset line -> Asset master"),
        ("LFA1", "BUT000", "LFA1.LIFNR = BUT000.PARTNER", "1:1", "cross_module", "Vendor -> BP Central"),
    ]

    added = 0
    for from_tbl, to_tbl, condition, card, bridge, notes in bidirectional:
        cypher = f"""
        MATCH (a), (b)
        WHERE a.table_name = '{from_tbl}' AND b.table_name = '{to_tbl}'
        AND 'SAPTable' IN labels(a) AND 'SAPTable' IN labels(b)
        MERGE (a)-[r:FOREIGN_KEY]->(b)
        SET r.condition = '{condition}',
            r.cardinality = '{card}',
            r.bridge_type = '{bridge}',
            r.notes = '{notes}'
        """
        try:
            list(mg.execute_and_fetch(cypher))
            added += 1
        except Exception:
            pass
    print(f"Bidirectional edges added: {added}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load SAP schema into Memgraph")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7687)
    parser.add_argument("--drop-first", action="store_true")
    args = parser.parse_args()
    load_schema(host=args.host, port=args.port, drop_first=args.drop_first)
