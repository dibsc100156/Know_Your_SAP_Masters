# validate_memgraph.py - Memgraph Migration Validation Script
import sys, re, os
sys.path.insert(0, os.path.dirname(__file__))

NX_OK = False
try:
    import networkx as nx
    NX_OK = True
except ImportError:
    print('WARNING: NetworkX not available - skipping graph logic tests')

# 1. AST validation
print('')
print('[1/5] Python AST Validation: memgraph_adapter.py')
import ast

adapter_path = os.path.join(os.path.dirname(__file__), 'app', 'core', 'memgraph_adapter.py')
with open(adapter_path, 'r', encoding='utf-8') as f:
    src = f.read()

try:
    tree = ast.parse(src)
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    public_methods = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and not n.name.startswith('_')]
    print('  AST valid')
    print('  Classes: ' + ', '.join(classes))
    print('  Public methods: ' + ', '.join(public_methods))
except SyntaxError as e:
    print('  SYNTAX ERROR: ' + str(e))
    sys.exit(1)

# 2. CQL init script validation
print('')
print('[2/5] CQL Init Script Validation: init_schema.cql')
cql_path = os.path.join(os.path.dirname(__file__), '..', 'docker', 'memgraph', 'init_schema.cql')
with open(cql_path, 'r', encoding='utf-8') as f:
    cql_text = f.read()
cql_lines = cql_text.splitlines()

node_merges = [l.strip() for l in cql_lines if 'MERGE (m:SAPTable' in l]
edge_lines  = [l.strip() for l in cql_lines if 'FOREIGN_KEY' in l and 'MATCH' in l]
index_lines = [l.strip() for l in cql_lines if l.strip().startswith('CREATE INDEX')]

print('  Node MERGEs: ' + str(len(node_merges)))
print('  Edge MATCHes: ' + str(len(edge_lines)))
print('  Index CREATE: ' + str(len(index_lines)))

all_tables_in_cql = set(re.findall(r'"table_name":"([A-Za-z0-9_/]+)"', cql_text))
print('  Unique tables in CQL: ' + str(len(all_tables_in_cql)))

unbalanced = [(i+1, l) for i, l in enumerate(cql_lines) if l.count('{') != l.count('}')]
if unbalanced:
    print('  WARNING: Unbalanced braces on lines: ' + str([x for x,_ in unbalanced[:3]]))
else:
    print('  All CQL braces balanced')

if any('RETURN' in l and 'status' in l for l in cql_lines):
    print('  Verification RETURN query present')

# 3. API compatibility
print('')
print('[3/5] GraphRAGManager API Compatibility')

if NX_OK:
    from app.core.graph_store import GraphRAGManager
    from app.core.memgraph_adapter import MemgraphGraphRAGManager

    orig = GraphRAGManager()
    orig_stats = orig.stats()
    print('  Original: ' + str(orig_stats['total_tables']) + ' tables, ' + str(orig_stats['total_relationships']) + ' edges, ' + str(len(orig_stats['modules'])) + ' modules')

    orig_methods = set(n for n in dir(GraphRAGManager) if not n.startswith('_') and callable(getattr(GraphRAGManager, n)))
    mig_methods  = set(n for n in dir(MemgraphGraphRAGManager) if not n.startswith('_') and callable(getattr(MemgraphGraphRAGManager, n)))
    shared = orig_methods & mig_methods
    missing = orig_methods - mig_methods
    extra   = mig_methods - orig_methods

    print('  Shared methods (drop-in compatible): ' + str(len(shared)))
    if missing:
        print('  WARNING - In original but NOT in adapter: ' + str(sorted(missing)))
    if extra:
        print('  Extra in adapter (extensions): ' + str(sorted(extra)))
    print('  API compatibility: PASS' if not missing else '  API compatibility: PARTIAL')
else:
    print('  SKIPPED (NetworkX not available)')

# 4. Docker Compose validation
print('')
print('[4/5] Docker Compose Validation')
compose_path = os.path.join(os.path.dirname(__file__), '..', 'docker-compose.memgraph.yml')
with open(compose_path, 'r', encoding='utf-8') as f:
    compose = f.read()

required_services = ['memgraph', 'qdrant', 'redis', 'rabbitmq', 'minio']
required_ports    = {'memgraph': '7687', 'qdrant': '6333', 'redis': '6379', 'rabbitmq': '5672'}

for svc in required_services:
    status = 'OK' if svc in compose else 'MISSING'
    print('  ' + status + ' Service: ' + svc)

for svc, port in required_ports.items():
    found = port in compose
    print('  ' + ('OK' if found else 'MISSING') + ' Port ' + port + ' for ' + svc)

hc_count = compose.count('healthcheck:')
print('  ' + ('OK' if hc_count >= 4 else 'WARNING') + ' Healthchecks: ' + str(hc_count) + ' (expected >=4)')

# 5. NetworkX fallback traversal test
print('')
print('[5/5] NetworkX Fallback Traversal Test')

if NX_OK:
    from app.core.graph_store import GraphRAGManager
    from app.core.memgraph_adapter import MemgraphGraphRAGManager, MemgraphNodeMeta

    orig_gm = GraphRAGManager()

    adapter = MemgraphGraphRAGManager(uri='bolt://localhost:99999', load_on_init=False)
    adapter._node_meta = {}
    adapter._edge_meta = {}

    for table, meta in orig_gm._node_meta.items():
        adapter._node_meta[table] = MemgraphNodeMeta(
            module=meta.get('module', '?'),
            domain=meta.get('domain', '?'),
            desc=meta.get('desc', ''),
            key_columns=meta.get('key_columns', []),
        )

    adapter._nx_cache = nx.Graph()
    for table in orig_gm.G.nodes:
        adapter._nx_cache.add_node(table)
    for u, v, data in orig_gm.G.edges(data=True):
        adapter._nx_cache.add_edge(u, v, **data)

    adapter_stats = adapter.stats()
    print('  Adapter loaded: ' + str(adapter_stats['total_tables']) + ' tables, ' + str(adapter_stats['total_relationships']) + ' edges')
    print('  NetworkX fallback works (no Memgraph required)')

    test_cases = [
        ('MARA',   'LFA1'),
        ('KNA1',   'BSEG'),
        ('EKKO',   'MBEW'),
        ('PRPS',   'MARA'),
        ('BUT000', 'LFA1'),
    ]

    print('  Shortest-path comparisons (adapter vs original):')
    all_pass = True
    for start, end in test_cases:
        orig_path = orig_gm.find_path(start, end)
        adap_path = adapter.find_path(start, end)
        match = orig_path == adap_path
        if not match:
            all_pass = False
        print('    ' + ('OK' if match else 'FAIL') + ' ' + start + ' -> ' + end + ': ' + str(adap_path))

    print('  All paths match: ' + str(all_pass))

    ctx = adapter.get_subgraph_context(['MARA', 'MARC', 'MBEW'])
    print('  get_subgraph_context: ' + str(len(ctx['tables'])) + ' tables, cross_module=' + str(ctx['is_cross_module']))

    stats = adapter.stats()
    print('  stats: tables=' + str(stats['total_tables']) + ', edges=' + str(stats['total_relationships']) + ', cross_module=' + str(stats['cross_module_bridges']))
else:
    print('  SKIPPED (NetworkX not available)')

print('')
print('=' * 60)
print('VALIDATION COMPLETE')
print('')
print('Next steps when Docker+Memgraph are available:')
print('  1. pip install gqlalchemy>=3.0.0 celery>=5.4.0 redis>=5.2.0')
print('  2. docker compose -f docker-compose.memgraph.yml up -d')
print('  3. python -c "from app.core.memgraph_adapter import MemgraphGraphRAGManager;')
print('       g = MemgraphGraphRAGManager(); g.build_enterprise_schema_graph(); print(g.stats())"')
print('=' * 60)
