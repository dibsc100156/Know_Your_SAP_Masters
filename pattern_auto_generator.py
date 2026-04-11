import os
import sys
import json
from collections import defaultdict

# Add backend to path so we can import the Graph Store
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

from app.core.graph_store import GraphRAGManager

def generate_patterns():
    print("Loading GraphRAGManager...")
    graph_manager = GraphRAGManager()
    G = graph_manager.G
    
    patterns_by_module = defaultdict(list)
    total_patterns = 0
    
    print(f"Found {G.number_of_nodes()} tables and {G.number_of_edges()} relationships.")
    print("Generating Single-Table Base Patterns...")
    
    # 1. Generate Single-Table Read Patterns
    for node, data in G.nodes(data=True):
        module = data.get('module', 'UNKNOWN')
        desc = data.get('desc', node)
        
        sql = f"""
SELECT * 
FROM 
    {node}
WHERE 
    MANDT = '{{MANDT}}'
LIMIT 100;
""".strip()
        
        patterns_by_module[module].append({
            "intent": f"Retrieve {desc} ({node})",
            "business_use_case": f"Basic data retrieval for {desc}",
            "tables": [node],
            "sql": sql
        })
        total_patterns += 1

    print("Generating 1-Hop JOIN Patterns...")
    
    # 2. Generate 1-Hop JOIN Patterns based on Edges
    for u, v, data in G.edges(data=True):
        condition = data.get('condition', '')
        if not condition:
            continue
            
        u_data = G.nodes[u]
        v_data = G.nodes[v]
        
        # Determine the primary module for the pattern (default to u's module)
        module = u_data.get('module', 'UNKNOWN')
        bridge_type = data.get('bridge_type', 'internal')
        
        desc_u = u_data.get('desc', u)
        desc_v = v_data.get('desc', v)
        
        intent_prefix = "Cross-Module: " if bridge_type == "cross_module" else ""
        
        sql = f"""
SELECT 
    a.*, b.*
FROM 
    {u} a
JOIN 
    {v} b ON {condition.replace(f"{u}.", "a.").replace(f"{v}.", "b.")}
WHERE 
    a.MANDT = '{{MANDT}}'
LIMIT 100;
""".strip()

        patterns_by_module[module].append({
            "intent": f"{intent_prefix}Join {u} and {v} ({desc_u} to {desc_v})",
            "business_use_case": f"Combine data from {u} and {v} using standard SAP foreign keys.",
            "tables": [u, v],
            "sql": sql
        })
        total_patterns += 1

    # Write the output to a Python file
    output_file = "generated_sql_patterns.py"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write('"""\nAUTO-GENERATED SAP SQL PATTERNS\n')
        f.write(f'Generated from Graph Store. Total Patterns: {total_patterns}\n"""\n\n')
        
        for module, patterns in patterns_by_module.items():
            var_name = f"{module.replace('-', '_').upper()}_AUTO_PATTERNS"
            f.write(f"# {'='*70}\n")
            f.write(f"# MODULE: {module} ({len(patterns)} patterns)\n")
            f.write(f"# {'='*70}\n\n")
            
            f.write(f"{var_name} = [\n")
            for p in patterns:
                f.write("    {\n")
                f.write(f'        "intent": "{p["intent"]}",\n')
                f.write(f'        "business_use_case": "{p["business_use_case"]}",\n')
                f.write(f'        "tables": {json.dumps(p["tables"])},\n')
                f.write(f'        "sql": """\n{p["sql"]}\n"""\n')
                f.write("    },\n")
            f.write("]\n\n")

    print(f"Successfully generated {total_patterns} patterns.")
    print(f"Saved to {output_file}")

if __name__ == "__main__":
    generate_patterns()