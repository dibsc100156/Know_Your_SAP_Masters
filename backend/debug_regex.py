"""Debug regex parsing of init_schema.cql."""
import re, sys, os
sys.path.insert(0, os.path.dirname(__file__) + "/app/core")
sys.path.insert(0, os.path.dirname(__file__))

# ── Test the node regex ──────────────────────────────────────────────────────
NODE_PAT = re.compile(
    r'MERGE\s*\(\s*m:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*'
    r'SET\s*m\.module="([^"]*)"\s*,\s*m\.domain="([^"]*)"'
    r'(?:\s*,\s*m\.description="([^"]*)")?'
    r'(?:\s*,\s*m\.key_columns=\[([^\]]*)\])?'
    r'(?:\s*,\s*m\.bridge=(true|false))?',
    re.IGNORECASE
)

EDGE_PAT = re.compile(
    r'MATCH\s*\(\s*a:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*,\s*'
    r'\(\s*b:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*'
    r'MERGE\s*\(\s*a\)\[:FOREIGN_KEY\s*\{.*?\}\]->\(b\)',
    re.DOTALL | re.IGNORECASE
)

# Inner parse for edge properties (after the main match)
EDGE_PROPS_PAT = re.compile(
    r'condition:"([^"]*)"\s*,\s*'
    r'cardinality:"([^"]*)"\s*,\s*'
    r'bridge_type:"([^"]*)"'
    r'(?:\s*,\s*notes:"([^"]*)")?',
    re.IGNORECASE
)

def test_regex():
    # Test node line
    test = 'MERGE (m:SAPTable {table_name:"MBEW"}) SET m.module="MM", m.domain="material_master", m.description="Material Valuation", m.key_columns=["MATNR","BWKEY"], m.bridge=false;'
    m = NODE_PAT.search(test)
    if m:
        print(f"Node test OK: {m.groups()}")
    else:
        print(f"Node test FAIL: {test[:60]}")

    # Test edge line
    edge_test = 'MATCH (a:SAPTable {table_name:"MARA"}), (b:SAPTable {table_name:"MARC"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARA.MATNR = MARC.MATNR", cardinality:"1:N", bridge_type:"internal", notes:"Material -> Plant-specific data"}]->(b);'
    e = EDGE_PAT.search(edge_test)
    if e:
        # Extract props from the rel block
        props_m = EDGE_PROPS_PAT.search(e.group(0))
        if props_m:
            print(f"Edge test OK: src={e.group(1)}, tgt={e.group(2)}, "
                  f"condition={props_m.group(1)}, card={props_m.group(2)}, "
                  f"bridge={props_m.group(3)}, notes={props_m.group(4)}")
        else:
            print(f"Edge test OK (match) but props parse fail")
    else:
        print(f"Edge test FAIL: {edge_test[:60]}")

    # Now test against actual file
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    schema_path = os.path.normpath(os.path.join(_script_dir, "..", "docker", "memgraph", "init_schema.cql"))
    print(f"\nParsing: {schema_path}")

    nodes_found, edges_found, errors = [], [], []

    buf = []
    for raw_line in open(schema_path, encoding="utf-8").read().splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(stripped)
        if stripped.endswith(";"):
            stmt = " ".join(buf)
            buf = []
            n = NODE_PAT.search(stmt)
            if n:
                nodes_found.append((n.group(1), n.group(2)))
            else:
                e = EDGE_PAT.search(stmt)
                if e:
                    props_m = EDGE_PROPS_PAT.search(e.group(0))
                    if props_m:
                        edges_found.append((e.group(1), e.group(2)))
                    else:
                        errors.append(stmt[:80])
                elif re.match(r'CREATE\s+INDEX', stmt, re.I):
                    pass  # index - ok
                elif re.match(r'RETURN', stmt, re.I):
                    pass  # verification - ok
                else:
                    errors.append(stmt[:80])

    print(f"\nResults: {len(nodes_found)} nodes, {len(edges_found)} edges, {len(errors)} unknown")
    if errors:
        print(f"\nFirst 5 unknown statements:")
        for s in errors[:5]:
            print(f"  {s}")

    print(f"\nSample nodes: {nodes_found[:5]}")
    print(f"Sample edges: {edges_found[:5]}")

test_regex()
