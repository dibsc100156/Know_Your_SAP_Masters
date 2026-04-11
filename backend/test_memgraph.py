from gqlalchemy import Memgraph

mg = Memgraph(host='127.0.0.1', port=7687)

# Count nodes and edges
node_count = list(mg.execute_and_fetch("MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN count(t) AS cnt"))
edge_count = list(mg.execute_and_fetch("MATCH (a)-[r]->(b) WHERE type(r) = 'FOREIGN_KEY' RETURN count(r) AS cnt"))
modules = list(mg.execute_and_fetch("MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN collect(DISTINCT t.module) AS modules"))

print("Nodes:", node_count[0]["cnt"])
print("Edges:", edge_count[0]["cnt"])
print("Modules:", modules[0]["modules"])

# Sample tables
samples = list(mg.execute_and_fetch("MATCH (t) WHERE 'SAPTable' IN labels(t) RETURN t.table_name, t.module LIMIT 10"))
print("Sample nodes:")
for r in samples:
    print(f"  {r['t.table_name']} [{r['t.module']}]")

# Sample cross-module edges
cross = list(mg.execute_and_fetch("MATCH (a)-[r]->(b) WHERE type(r) = 'FOREIGN_KEY' AND r.bridge_type = 'cross_module' RETURN a.table_name AS src, r.condition AS cond, b.table_name AS tgt LIMIT 5"))
print("Sample cross-module edges:")
for e in cross:
    print(f"  {e['src']} --[{e['cond']}]--> {e['tgt']}")

# Verify a path traversal works
path = list(mg.execute_and_fetch("MATCH path = (a)-[:FOREIGN_KEY*1..3]->(b) WHERE a.table_name = 'MARA' AND b.table_name = 'LFA1' RETURN path LIMIT 1"))
print(f"MARA -> LFA1 paths found: {len(path)}")
