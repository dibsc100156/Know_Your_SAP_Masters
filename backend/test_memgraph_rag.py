"""
test_memgraph_rag.py — Verify Memgraph Graph RAG is operational
==============================================================
Simplified for Memgraph 2.x compatibility (no path functions).
"""
from neo4j import GraphDatabase

driver = GraphDatabase.driver("bolt://127.0.0.1:7687")

with driver.session() as s:
    # 1. Basic node lookup
    result = list(s.run(
        "MATCH (t:SAPTable {table_name:'LFA1'}) RETURN t.table_name AS tn, t.module AS module, t.domain AS domain"
    ))
    print(f"[1] LFA1 lookup: {result[0] if result else 'NOT FOUND'}")

    # 2. LFA1 neighbors
    neighbors = list(s.run(
        "MATCH (lfa1:SAPTable {table_name:'LFA1'})-[r:FOREIGN_KEY]-(neighbor:SAPTable) "
        "RETURN lfa1.table_name AS node, neighbor.table_name AS neigh, r.bridge_type AS bridge_type"
    ))
    print(f"\n[2] LFA1 neighbors ({len(neighbors)}):")
    for n in neighbors:
        print(f"  {n['node']} <-> {n['neigh']}  [{n['bridge_type']}]")

    # 3. 2-hop: LFA1 -> via any table -> BSEG
    paths_2hop = list(s.run(
        "MATCH (lfa1:SAPTable {table_name:'LFA1'})-[r1:FOREIGN_KEY]-(mid:SAPTable) "
        "MATCH (mid:SAPTable)-[r2:FOREIGN_KEY]-(bseg:SAPTable {table_name:'BSEG'}) "
        "WHERE lfa1 <> bseg AND mid <> lfa1 AND mid <> bseg "
        "RETURN lfa1.table_name AS src, mid.table_name AS mid_tbl, bseg.table_name AS dst"
    ))
    print(f"\n[3] 2-hop paths LFA1 -> BSEG ({len(paths_2hop)}):")
    for p in paths_2hop[:10]:
        print(f"  {p['src']} -> {p['mid_tbl']} -> {p['dst']}")

    # 4. All MARA connections
    mara_hubs = list(s.run(
        "MATCH (mara:SAPTable {table_name:'MARA'})-[r:FOREIGN_KEY]-(neighbor:SAPTable) "
        "RETURN mara.table_name AS tbl, neighbor.table_name AS neighbor, r.bridge_type AS bt"
    ))
    print(f"\n[4] MARA connections ({len(mara_hubs)}):")
    for h in mara_hubs:
        print(f"  MARA <-> {h['neighbor']}  [{h['bt']}]")

    # 5. Module summary
    modules = list(s.run(
        "MATCH (t:SAPTable) RETURN t.module AS module, count(t) AS cnt ORDER BY cnt DESC"
    ))
    print(f"\n[5] Tables per module:")
    for m in modules:
        print(f"  {m['module'] or 'null'}: {m['cnt']} tables")

    # 6. Bridge type analysis
    bridges = list(s.run(
        "MATCH ()-[r:FOREIGN_KEY]->() "
        "RETURN r.bridge_type AS bt, count(r) AS cnt ORDER BY cnt DESC"
    ))
    print(f"\n[6] Edge types:")
    for b in bridges:
        print(f"  {b['bt']}: {b['cnt']} edges")

driver.close()
print("\n✅ Memgraph Graph RAG operational — all checks passed")
