"""Step-by-step debug of edge regex — with hyphen fix."""
import re

stmt = 'MATCH (a:SAPTable {table_name:"MARA"}), (b:SAPTable {table_name:"MARC"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARA.MATNR = MARC.MATNR", cardinality:"1:N", bridge_type:"internal", notes:"Material -> Plant-specific data"}]->(b);'

print(f"Stmt: {stmt}\n")

# Test 1: basic MERGE -> structure with hyphen
p1 = re.compile(r'MERGE\s*\(\s*a\)\s*-\s*\[:FOREIGN_KEY\s*\{[^}]*\}\]\s*->\s*\(b\)', re.I)
m1 = p1.search(stmt)
print(f"Test1 MERGE with hyphen: {'OK' if m1 else 'FAIL'}")
if m1:
    print(f"  Matched: {m1.group()!r}")

# Test 2: full edge pat with hyphen
p2 = re.compile(
    r'MATCH\s*\(\s*a:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*,\s*'
    r'\(\s*b:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*'
    r'MERGE\s*\(\s*a\)\s*-\s*\[:FOREIGN_KEY\s*\{[^}]*\}\]\s*->\s*\(b\)',
    re.I
)
m2 = p2.search(stmt)
print(f"Test2 full edge with hyphen: {'OK' if m2 else 'FAIL'}")
if m2:
    print(f"  src={m2.group(1)}, tgt={m2.group(2)}")

# Test 3: EDGE_PAT with full capture
EDGE_PAT_FINAL = re.compile(
    r'MATCH\s*\(\s*a:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*,\s*'
    r'\(\s*b:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*'
    r'MERGE\s*\(\s*a\)\s*-\s*\[:FOREIGN_KEY\s*\{[^}]*\}\]\s*->\s*\(b\)',
    re.I
)
m3 = EDGE_PAT_FINAL.search(stmt)
print(f"Test3 final pattern: {'OK' if m3 else 'FAIL'}")
if m3:
    print(f"  src={m3.group(1)}, tgt={m3.group(2)}")

    # Now extract properties
    EDGE_PROPS = re.compile(
        r'condition:"([^"]*)"\s*,\s*'
        r'cardinality:"([^"]*)"\s*,\s*'
        r'bridge_type:"([^"]*)"'
        r'(?:,?\s*notes:"([^"]*)")?',
        re.I
    )
    pm = EDGE_PROPS.search(m3.group(0))
    if pm:
        print(f"  condition={pm.group(1)!r}, cardinality={pm.group(2)!r}, bridge_type={pm.group(3)!r}, notes={pm.group(4)!r}")

# Test against all 47 edges in file
schema = r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\docker\memgraph\init_schema.cql"
all_lines = open(schema, encoding="utf-8").read().splitlines()
buf = []
all_stmts = []
for line in all_lines:
    s = line.strip()
    if not s or s.startswith("--"):
        continue
    buf.append(s)
    if s.endswith(";"):
        all_stmts.append(" ".join(buf))
        buf = []

edge_stmts = [s for s in all_stmts if 'FOREIGN_KEY' in s and 'MATCH' in s]
ok = sum(1 for s in edge_stmts if EDGE_PAT_FINAL.search(s))
print(f"\nFile test: {ok}/{len(edge_stmts)} edges matched")
