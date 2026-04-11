#!/usr/bin/env python3
"""
sap_tools.graph — Graph Traversal CLI (Pillar 5)

Usage:
    python -m sap_tools.graph LFA1 MARA
    python -m sap_tools.graph KNA1 QALS
    python -m sap_tools.graph LFA1 VBAP --format join

Finds the shortest JOIN path between two SAP tables using NetworkX Graph RAG.
This is the core of cross-module query resolution.
"""

import sys
import os
import argparse
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.graph_store import graph_store


def format_join_output(join_string: str, start: str, end: str) -> str:
    """Format the JOIN path output for readability."""
    output = []
    output.append(f"\n  [LINK] Start: {start}")
    output.append(f"  [PATTERN] End: {end}")
    output.append(f"\n  📜 JOIN Path:")
    
    for line in join_string.split('\n'):
        if line.strip():
            output.append(f"    {line.strip()}")
    
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="[Pillar 5] Graph RAG — Find JOIN path between two SAP tables"
    )
    parser.add_argument("start_table", type=str, help="Starting table (e.g., LFA1)")
    parser.add_argument("end_table", type=str, help="Target table (e.g., MARA)")
    parser.add_argument("--format", choices=["join", "path", "json"], default="join",
                        help="Output format: join (SQL), path (table list), json")
    parser.add_argument("--json", action="store_true", help="Output raw JSON (shorthand for --format json)")
    
    args = parser.parse_args()
    
    # Normalize table names
    start = args.start_table.upper().strip()
    end = args.end_table.upper().strip()
    
    print(f"\n[GRAPH]️  [GRAPH] Finding path: {start} -> {end}")
    
    # Validate tables exist in graph
    all_nodes = list(graph_store.G.nodes)
    missing = []
    if start not in all_nodes:
        missing.append(start)
    if end not in all_nodes:
        missing.append(end)
    
    if missing:
        print(f"\n[WARN]️  Tables not found in Graph RAG schema: {', '.join(missing)}")
        print(f"   Available tables ({len(all_nodes)}): {', '.join(sorted(all_nodes)[:20])}...")
        print(f"\n   To add missing tables, update graph_store.py build_enterprise_schema_graph()")
        return 1
    
    # Traverse
    result = graph_store.traverse_graph(start, end)
    
    # Format output
    format_type = "json" if args.json else args.format
    
    if format_type == "json":
        import json
        output_data = {
            "start": start,
            "end": end,
            "path": result,
            "tables_in_path": []
        }
        # Extract table names from path
        if "Start at" in result:
            for line in result.split('\n'):
                if "Start at" in line:
                    output_data["tables_in_path"].append(line.split("Start at")[1].strip())
                elif "INNER JOIN" in line or "LEFT JOIN" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        output_data["tables_in_path"].append(parts[2])
        print(json.dumps(output_data, indent=2))
        return 0
    
    if "No direct join" in result or "No JOIN needed" in result:
        print(f"\n[WARN]️  {result}")
        print(f"   These tables cannot be joined through known FK relationships.")
        return 1
    
    # Human-readable output
    print(format_join_output(result, start, end))
    
    # If format is "path", also show simple table list
    if format_type == "path":
        print(f"\n  [TABLE] Table List:")
        tables = [start]
        for line in result.split('\n'):
            if "JOIN" in line:
                parts = line.upper().split()
                if 'ON' in parts:
                    idx = parts.index('ON')
                    if len(parts) > idx + 1:
                        tables.append(parts[idx + 1] if parts[idx + 1].isalpha() else parts[idx - 1] if parts[idx - 1].isalpha() else "???")
        print(f"     {' -> '.join(tables)}")
    
    # SQL-ready JOIN clause
    if format_type == "join":
        print(f"\n  💻 Ready-to-use SQL fragment:")
        join_lines = []
        for line in result.split('\n'):
            stripped = line.strip()
            if stripped.startswith("INNER JOIN") or stripped.startswith("LEFT JOIN"):
                join_lines.append(stripped)
        if join_lines:
            print("    " + "\n    ".join(join_lines))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
