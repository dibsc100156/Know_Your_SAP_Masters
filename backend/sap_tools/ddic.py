#!/usr/bin/env python3
"""
sap_tools.ddic — Schema Lookup CLI (Pillar 3)

Usage:
    python -m sap_tools.ddic "find vendor tables"
    python -m sap_tools.ddic "material stock levels" --domain material_master
    python -m sap_tools.ddic "purchase orders" --n 3

Outputs table definitions from Qdrant (Schema RAG).
"""

import sys
import os
import argparse
from typing import Optional

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.schema_store import search_tables
from app.core.security import SAP_ROLES, security_mesh


def format_schema_result(schema: dict, auth_role: Optional[str] = None) -> str:
    """Format a single schema result for CLI output."""
    output = []
    output.append(f"\n  [TABLE] Table: {schema['table']}")
    output.append(f"     Module: {schema.get('module', 'N/A')}")
    output.append(f"     Auth Object: {schema.get('auth_object', 'N/A')}")
    output.append(f"     Description: {schema['description']}")
    
    # Show columns
    cols = schema.get('key_columns', [])
    output.append(f"     Columns ({len(cols)}): {', '.join(cols[:10])}")
    if len(cols) > 10:
        output.append(f"                   ...and {len(cols) - 10} more")
    
    # Show sensitive columns if not masked
    sensitive = schema.get('sensitive_columns', [])
    if sensitive:
        output.append(f"     [SEC] Sensitive: {', '.join(sensitive)}")
    
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="[Pillar 3] Schema RAG — Find SAP tables matching a query"
    )
    parser.add_argument("query", type=str, help="Natural language query (e.g., 'find vendor tables')")
    parser.add_argument("--domain", type=str, default=None, 
                        help="Domain filter: business_partner, material_master, purchasing, etc.")
    parser.add_argument("--n", type=int, default=4, help="Max results (default: 4)")
    parser.add_argument("--role", type=str, default=None,
                        help="Apply role-based filtering (AP_CLERK, CFO_GLOBAL, etc.)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    
    args = parser.parse_args()
    
    print(f"\n[SEARCH] [DDIC] Searching schemas for: '{args.query}'")
    if args.domain:
        print(f"   Domain filter: {args.domain}")
    if args.role:
        print(f"   Role context: {args.role}")
    
    # Perform schema search
    raw_results = search_tables(args.query)
    
    # Apply role-based filtering if specified
    if args.role and args.role in SAP_ROLES:
        auth_context = security_mesh.get_context(args.role)
        results = security_mesh.filter_schema_context(auth_context, 
            [{"metadata": {"table": r["table"]}, "document": r["description"]} for r in raw_results]
        )
        # Re-attach raw schema data
        table_map = {r["table"]: r for r in raw_results}
        filtered_results = []
        for r in results:
            t = r["metadata"]["table"]
            if t in table_map:
                filtered_results.append(table_map[t])
        raw_results = filtered_results
        print(f"   Role filter applied. {len(raw_results)}/{len(raw_results)} tables authorized.")
    else:
        # Filter denied tables silently
        results = raw_results
    
    # Apply n limit
    results = raw_results[:args.n]
    
    if not results:
        print("\n❌ No schemas found matching your query.")
        print("   Try: 'python -m sap_tools.ddic vendor' or 'python -m sap_tools.ddic material'")
        return 1
    
    # Output
    print(f"\n✅ Found {len(results)} schema(s):")
    
    if args.json:
        import json
        print(json.dumps(results, indent=2))
    else:
        for i, schema in enumerate(results, 1):
            print(f"\n{'─' * 60}")
            print(format_schema_result(schema, args.role))
    
    print(f"\n{'─' * 60}")
    print(f"[STATS] Total: {len(results)} schema(s) returned")
    
    # Return exit code for agent integration
    return 0


if __name__ == "__main__":
    sys.exit(main())
