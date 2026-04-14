from neo4j import GraphDatabase

def test_memgraph_path():
    driver = GraphDatabase.driver("bolt://localhost:7687", auth=("", ""))
    with driver.session() as session:
        result = session.run("MATCH path = (a:SAPTable {table_name: 'LFA1'})-[*..2]-(b:SAPTable {table_name: 'EKKO'}) RETURN path LIMIT 1")
        record = result.single()
        if record:
            path = record["path"]
            print(type(path))
            print(path)
            print([n.get("table_name", "UNKNOWN") for n in path.nodes])
            print([r.type for r in path.relationships])

if __name__ == "__main__":
    test_memgraph_path()
