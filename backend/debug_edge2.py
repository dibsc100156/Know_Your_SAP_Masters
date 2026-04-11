"""Print raw bytes of first edge statement."""
schema = r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\docker\memgraph\init_schema.cql"
lines = open(schema, encoding="utf-8").read().splitlines()

buf = []
in_edge = False
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("--"):
        continue
    buf.append(stripped)
    if stripped.endswith(";"):
        stmt = " ".join(buf)
        buf = []
        if 'FOREIGN_KEY' in stmt and 'MATCH' in stmt:
            print("=== FULL STATEMENT ===")
            print(repr(stmt))
            print()
            print("=== MATCH section ===")
            idx = stmt.index('MATCH')
            print(repr(stmt[idx:idx+120]))
            print()
            # Try simple parse
            import re
            # Just extract table names
            tables = re.findall(r'table_name:"([^"]+)"', stmt)
            print(f"Table names found: {tables}")
            break
