import re

# Read the init_schema.cql
with open(r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\docker\memgraph\init_schema.cql', encoding='utf-8-sig') as f:
    cql = f.read()

# Find all MATCH/MERGE edge statements
edge_pattern = re.compile(
    r'MATCH\s*\(\s*a:SAPTable\s*\{table_name:"([^"]+)"\}\s*\)\s*,\s*\(\s*b:SAPTable\s*\{table_name:"([^"]+)"\}\s*\)\s*'
    r'MERGE\s+\(a\)\s*-\s*\[:FOREIGN_KEY\s*\{([^}]+)\}\]\s*->\s*\(b\)',
    re.MULTILINE
)

matches = list(re.finditer(edge_pattern, cql))
print(f'Edge regex matches: {len(matches)}')
if matches:
    for m in matches[:3]:
        print(f'  {m.group(1)} → {m.group(2)} | {m.group(3)[:60]}')

# Now test what the _parse_edge_statement actually uses
print()
print('Testing actual regex used in memgraph_adapter._parse_edge_statement:')

line = '        MERGE (a)-[:FOREIGN_KEY {condition:"MARA.MATNR = MARC.MATNR", cardinality:"1:N", bridge_type:"internal", notes:"Material -> Plant"}]->(b)'
edge_match = re.search(
    r'MATCH\s*\(\s*a:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*,\s*'
    r'\(\s*b:SAPTable\s*\{table_name:"([^"]+)"\)\s*\n\s*'
    r'MERGE\s+\(a\)\s*-\s*\[:FOREIGN_KEY\s*\{([^}]+)\}\]\s*->\s*\(b\)',
    line
)
print(f'  with newline: {edge_match}')

edge_match2 = re.search(
    r'MATCH\s*\(\s*a:SAPTable\s*\{table_name:"([^"]+)"\}\)\s*,\s*'
    r'\(\s*b:SAPTable\s*\{table_name:"([^"]+)"\)\s*,?\s*'
    r'MERGE\s+\(a\)\s*-\s*\[:FOREIGN_KEY\s*\{([^}]+)\}\]\s*->\s*\(b\)',
    line
)
print(f'  without newline: {edge_match2}')

# Look at the actual pattern more carefully
print()
print('Looking at actual MATCH edge lines in CQL:')
for m in re.finditer(r'MATCH.*?MERGE.*?FOREIGN_KEY', cql):
    start = max(0, m.start()-20)
    end = min(len(cql), m.end()+80)
    snippet = cql[start:end].replace('\n', ' ')
    if 'a:SAPTable' in snippet:
        print(f'  {snippet[:120]}')
        break