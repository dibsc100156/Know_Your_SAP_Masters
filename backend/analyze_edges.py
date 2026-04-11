from neo4j import GraphDatabase
import re

SCHEMA_PATH = r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\docker\memgraph\init_schema.cql"

# Extract expected edges from the CQL file
with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
    raw = f.read()

pattern = re.compile(
    r'MATCH \(a:SAPTable \{table_name:"([^"]+)"\}\), \(b:SAPTable \{table_name:"([^"]+)"\}\)'
)
expected = [(m.group(1), m.group(2)) for m in pattern.finditer(raw)]
print(f"Expected edges in CQL: {len(expected)}")

driver = GraphDatabase.driver("bolt://127.0.0.1:7687")
with driver.session() as s:
    existing = list(s.run(
        "MATCH (a:SAPTable)-[r:FOREIGN_KEY]->(b:SAPTable) "
        "RETURN a.table_name AS src, b.table_name AS dst ORDER BY src, dst"
    ))
    existing_set = {(r["src"], r["dst"]) for r in existing}
    print(f"Loaded edges in Memgraph: {len(existing_set)}")

    missing = [(s2,d2) for s2,d2 in expected if (s2,d2) not in existing_set]
    print(f"\nMissing {len(missing)} edges:")
    for src, dst in missing:
        print(f"  {src} -> {dst}")

    # Nodes present?
    all_nodes = list(s.run("MATCH (t:SAPTable) RETURN t.table_name AS tn"))
    node_set = {r["tn"] for r in all_nodes}
    print(f"\nTotal nodes: {len(node_set)}")
    needed_nodes = set()
    for s2,d2 in missing:
        needed_nodes.add(s2); needed_nodes.add(d2)
    missing_nodes = needed_nodes - node_set
    if missing_nodes:
        print(f"Missing nodes causing edge failures: {missing_nodes}")

driver.close()
