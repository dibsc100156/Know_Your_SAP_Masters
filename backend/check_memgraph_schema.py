"""Test specific init_schema.cql commands against Memgraph."""
import sys
sys.path.insert(0, ".venv\\Scripts\\site-packages")

from gqlalchemy import Memgraph

mg = Memgraph("127.0.0.1", 7687)

tests = [
    # Index creation
    ("CREATE INDEX ON :SAPTable(table_name)", "index on table_name"),
    # Simple MERGE node
    ("MERGE (m:SAPTable {table_name:'TEST001', module:'TEST', domain:'test', description:'Test node', key_columns:['ID'], bridge:false}) RETURN m.table_name", "merge node"),
]

for query, desc in tests:
    try:
        result = list(mg.execute_and_fetch(query))
        print(f"✅ {desc}: {[dict(r) for r in result]}")
    except Exception as e:
        print(f"❌ {desc}: {e}")
    except Exception as e:
        print(f"❌ {desc}: {type(e).__name__}: {e}")

# Now try loading the first few nodes from init_schema.cql
print("\n--- Loading MARA node ---")
try:
    mg.execute("""
    MERGE (m:SAPTable {table_name:'MARA'})
    SET m.module='MM', m.domain='material_master', m.description='General Material Data',
        m.key_columns=['MATNR'], m.bridge=false, m.table='MARA'
    """)
    result = list(mg.execute_and_fetch("MATCH (t) WHERE 'SAPTable' IN labels(t) AND t.table_name='MARA' RETURN t"))
    print(f"✅ MARA: {dict(result[0])}")
except Exception as e:
    print(f"❌ MARA load: {e}")

print("\n--- Loading MARA→MARC edge ---")
try:
    mg.execute("""
    MATCH (a:SAPTable {table_name:'MARA'}), (b:SAPTable {table_name:'MARC'})
    MERGE (a)-[r:FOREIGN_KEY]->(b)
    SET r.condition='MARA.MATNR = MARC.MATNR', r.cardinality='1:N', r.bridge_type='internal', r.notes='Material → Plant'
    """)
    edges = list(mg.execute_and_fetch("MATCH ()-[r:FOREIGN_KEY]->() RETURN count(r) AS e"))
    print(f"✅ Edge created. Total edges: {edges[0]['e']}")
except Exception as e:
    print(f"❌ Edge: {e}")
