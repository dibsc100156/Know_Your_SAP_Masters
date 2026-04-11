from gqlalchemy import Memgraph
mg = Memgraph(host='127.0.0.1', port=7687)

# Check LFA1 neighbors (inbound = edges pointing TO LFA1 from other SAPTables)
in_edges = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE b.table_name = 'LFA1' AND 'SAPTable' IN labels(a)
    RETURN a.table_name AS src, type(r) AS rel, r.bridge_type AS bridge
"""))
print("LFA1 inbound edges:", in_edges)

# Check EINA neighbors (outbound from EINA)
eina_out = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE a.table_name = 'EINA' AND 'SAPTable' IN labels(b)
    RETURN b.table_name AS tgt, r.bridge_type AS bridge
"""))
print("EINA outbound edges:", eina_out)

# Check MSLB neighbors
mslb = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE a.table_name = 'MSLB' AND 'SAPTable' IN labels(b)
    RETURN b.table_name AS tgt, r.bridge_type AS bridge
"""))
print("MSLB outbound edges:", mslb)

# Check if MARA exists and what edges it has
mara = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE a.table_name = 'MARA' AND 'SAPTable' IN labels(b)
    RETURN b.table_name AS tgt, r.bridge_type AS bridge, r.condition AS cond
"""))
print("MARA outbound edges:", mara)

# Find any path using variable-length path
path1 = list(mg.execute_and_fetch("""
    MATCH path = (a)-[:FOREIGN_KEY*1..4]->(b)
    WHERE a.table_name = 'MARA' AND b.table_name = 'LFA1'
    RETURN length(path) AS hops, [n IN nodes(path) | n.table_name] AS tables
    LIMIT 5
"""))
print("MARA -> LFA1 paths (1..4 hops):", path1)

# Count all edges
all_edge_count = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE 'SAPTable' IN labels(a) AND 'SAPTable' IN labels(b)
    RETURN count(r) AS cnt
"""))
print("Total SAP-to-SAP edges:", all_edge_count[0]["cnt"])

# What edges from LFA1?
from_lfa1 = list(mg.execute_and_fetch("""
    MATCH (a)-[r]->(b)
    WHERE a.table_name = 'LFA1' AND 'SAPTable' IN labels(b)
    RETURN b.table_name AS tgt, r.bridge_type AS bridge
"""))
print("LFA1 outbound edges:", from_lfa1)
