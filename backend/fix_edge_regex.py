"""Fix _parse_edge_statement in memgraph_adapter.py."""
import re

f = r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\core\memgraph_adapter.py"
content = open(f, "r", encoding="utf-8").read()

old_method = """    def _parse_edge_statement(self, line: str) -> Optional[dict]:
        \"\"\"
        Parse a single MATCH/MERGE edge line from init_schema.cql.
        Returns a dict with src, tgt, condition, cardinality, bridge_type, notes
        or None if the line is not an edge statement.
        \"\"\"
        # Match: MATCH (a:SAPTable {table_name:\"SRC\"}), (b:SAPTable {table_name:\"TGT\"})
        #        MERGE (a)-[:FOREIGN_KEY {...}]->(b)
        edge_match = re.search(
            r'MATCH\\s*\\(\\s*a:SAPTable\\s*\\{table_name:\"([^\"]+)\"\\}\\)\\s*,\\s*'
            r'\\(\\s*b:SAPTable\\s*\\{table_name:\"([^\"]+)\"\\}\\)\\s*'
            r'MERGE\\s*\\(\\s*a\\)\\s*-\\s*\\[:FOREIGN_KEY\\s*\\{[^}]*\\}\\]\\s*->\\s*\\(b\\)'
            r'condition:\"([^\"]*)\"\\s*,\\s*'
            r'cardinality:\"([^\"]*)\"\\s*,\\s*'
            r'bridge_type:\"([^\"]*)\"'
            r'(?:\\s*,\\s*notes:\"([^\"]*)\")?',
            line, re.IGNORECASE
        )
        if not edge_match:
            return None

        return {
            \"src\": edge_match.group(1).upper(),
            \"tgt\": edge_match.group(2).upper(),
            \"condition\": edge_match.group(3),
            \"cardinality\": edge_match.group(4),
            \"bridge_type\": edge_match.group(5),
            \"notes\": edge_match.group(6) or \"\",
        }"""

new_method = """    def _parse_edge_statement(self, line: str) -> Optional[dict]:
        \"\"\"
        Parse a single MATCH/MERGE edge line from init_schema.cql.
        Returns a dict with src, tgt, condition, cardinality, bridge_type, notes
        or None if the line is not an edge statement.

        The Cypher edge syntax is:
          MATCH (a:SAPTable {table_name:\"SRC\"}), (b:SAPTable {table_name:\"TGT\"})
          MERGE (a)-[:FOREIGN_KEY {condition:\"...\", cardinality:\"...\", ...}]->(b)

        Note: the hyphen in \")-[:\" is required in the regex.
        Uses two-step matching: (1) main structure, (2) property extraction.
        \"\"\"
        # Step 1: match the overall edge structure
        edge_match = re.search(
            r'MATCH\\s*\\(\\s*a:SAPTable\\s*\\{table_name:\"([^\"]+)\"\\}\\)\\s*,\\s*'
            r'\\(\\s*b:SAPTable\\s*\\{table_name:\"([^\"]+)\"\\}\\)\\s*'
            r'MERGE\\s*\\(\\s*a\\)\\s*-\\s*\\[:FOREIGN_KEY\\s*\\{[^}]*\\}\\s*\\]\\s*->\\s*\\(b\\)',
            line, re.IGNORECASE
        )
        if not edge_match:
            return None

        # Step 2: extract properties from inside the {...} block
        props_match = re.search(
            r'condition:\"([^\"]*)\"\\s*,\\s*'
            r'cardinality:\"([^\"]*)\"\\s*,\\s*'
            r'bridge_type:\"([^\"]*)\"'
            r'(?:\\s*,\\s*notes:\"([^\"]*)\")?',
            edge_match.group(0), re.IGNORECASE
        )
        if not props_match:
            return None

        return {
            \"src\": edge_match.group(1).upper(),
            \"tgt\": edge_match.group(2).upper(),
            \"condition\": props_match.group(1),
            \"cardinality\": props_match.group(2),
            \"bridge_type\": props_match.group(3),
            \"notes\": props_match.group(4) or \"\",
        }"""

if old_method in content:
    content = content.replace(old_method, new_method)
    print("Method replaced successfully")
else:
    print("Could not find exact old method - checking partial...")
    if "_parse_edge_statement" in content:
        print("Method exists but content differs")
    else:
        print("Method NOT found in file")

open(f, "w", encoding="utf-8").write(content)
