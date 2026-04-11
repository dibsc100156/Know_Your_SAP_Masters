"""Test edge regex with [^}]* fix."""
import re

# Replace .*? with [^}]*? to avoid DOTALL greediness
EDGE_PAT = re.compile(
    r'MATCH\s*\(\s*a:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*,\s*'
    r'\(\s*b:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*'
    r'MERGE\s*\(\s*a\)\[:FOREIGN_KEY\s*\{[^}]*\}\]->\(b\)',
    re.IGNORECASE
)

EDGE_PROPS_PAT = re.compile(
    r'condition:"([^"]*)"\s*,\s*'
    r'cardinality:"([^"]*)"\s*,\s*'
    r'bridge_type:"([^"]*)"'
    r'(?:,?\s*notes:"([^"]*)")?',
    re.IGNORECASE
)

schema = r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\docker\memgraph\init_schema.cql"
lines = open(schema, encoding="utf-8").read().splitlines()

buf = []
edge_stmts = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("--"):
        continue
    buf.append(stripped)
    if stripped.endswith(";"):
        stmt = " ".join(buf)
        buf = []
        if 'FOREIGN_KEY' in stmt and 'MATCH' in stmt:
            edge_stmts.append(stmt)

print(f"Found {len(edge_stmts)} edge statements\n")
nodes_ok, edges_ok = 0, 0
for stmt in edge_stmts:
    m = EDGE_PAT.search(stmt)
    if m:
        pm = EDGE_PROPS_PAT.search(m.group(0))
        edges_ok += 1
    else:
        print(f"FAILED: {stmt[:100]}")

print(f"Nodes (regex): {nodes_ok}, Edges: {edges_ok}/{len(edge_stmts)}")
if edges_ok == len(edge_stmts):
    print("ALL EDGES PARSED!")
