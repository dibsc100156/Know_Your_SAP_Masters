from gqlalchemy import Memgraph

mg = Memgraph(host='127.0.0.1', port=7687)

# Check what edges actually exist
all_edges = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE 'SAPTable' IN labels(a) AND 'SAPTable' IN labels(b)
    RETURN a.table_name AS src, type(r) AS rel_type, r.bridge_type AS bridge_type, b.table_name AS tgt
    ORDER BY src
    LIMIT 30
"""))
print(f"Total edges found: {len(all_edges)}")
for e in all_edges:
    print(f"  {e['src']} -[{e['rel_type']}/{e['bridge_type']}]-> {e['tgt']}")

# Check MARA's neighbors
mara_neighbors = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE a.table_name = 'MARA' AND 'SAPTable' IN labels(b)
    RETURN b.table_name AS neighbor, r.bridge_type AS bridge_type
"""))
print(f"\nMARA neighbors: {mara_neighbors}")

# Check LFA1's neighbors
lfa1_neighbors = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE b.table_name = 'LFA1' AND 'SAPTable' IN labels(a)
    RETURN a.table_name AS neighbor, r.bridge_type AS bridge_type
"""))
print(f"LFA1 neighbors (inbound): {lfa1_neighbors}")

# Check MSLB neighbors
mslb_neighbors = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE a.table_name = 'MSLB' AND 'SAPTable' IN labels(b)
    RETURN b.table_name AS neighbor, r.bridge_type AS bridge_type
"""))
print(f"MSLB neighbors: {mslb_neighbors}")
