#!/usr/bin/env python3
"""
sap_tools.sql_pattern — SQL Pattern Lookup CLI (Pillar 4)

Usage:
    python -m sap_tools.sql_pattern "show me open purchase orders"
    python -m sap_tools.sql_pattern "vendor invoice status" --domain purchasing
    python -m sap_tools.sql_pattern "customer sales history" --n 2

Outputs proven SAP HANA SQL templates from the SQL RAG library.
"""

import sys
import os
import argparse
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.sql_vector_store import SQLRAGStore
from app.core.security import SAP_ROLES, security_mesh


def format_pattern_result(pattern: dict, idx: int) -> str:
    """Format a single SQL pattern for CLI output."""
    output = []
    output.append(f"\n  [PATTERN] Pattern #{idx}: {pattern['query_id']}")
    output.append(f"     Intent: {pattern['intent']}")
    output.append(f"     Tables: {', '.join(pattern['tables_used'])}")
    output.append(f"     Distance: {pattern.get('distance', 0.0):.3f}")
    output.append(f"\n  SQL Template:")
    
    # Indent SQL for readability
    sql_lines = pattern['sql_template'].strip().split('\n')
    for line in sql_lines[:15]:
        output.append(f"    {line}")
    if len(sql_lines) > 15:
        output.append(f"    ... ({len(sql_lines) - 15} more lines)")
    
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="[Pillar 4] SQL RAG — Find proven SAP SQL patterns matching your query"
    )
    parser.add_argument("query", type=str, 
                        help="Natural language business question (e.g., 'show me open POs')")
    parser.add_argument("--domain", type=str, default=None,
                        help="Domain filter: purchasing, business_partner, sales_distribution, etc.")
    parser.add_argument("--n", type=int, default=2, help="Max results (default: 2)")
    parser.add_argument("--role", type=str, default=None,
                        help="Apply role-based table access filter")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--init", action="store_true", 
                        help="Initialize/reseed the SQL pattern library first")
    
    args = parser.parse_args()
    
    print(f"\n[NOTE] [SQL_PATTERN] Searching for: '{args.query}'")
    if args.domain:
        print(f"   Domain filter: {args.domain}")
    if args.role:
        print(f"   Role context: {args.role}")
    
    # Initialize store
    try:
        store = SQLRAGStore(db_path="./chroma_db", collection_name="sap_sql_patterns")
    except Exception as e:
        print(f"\n[WARN]️  Could not connect to vector store: {e}")
        print("   Run with --init to seed the library first.")
        return 1
    
    if args.init:
        print("\n[INIT] Initializing SQL RAG library...")
        store.initialize_library()
        print("   ✅ Library seeded successfully.")
    
    # Search
    try:
        results = store.search(args.query, top_k=args.n)
    except Exception as e:
        print(f"\n❌ Search failed: {e}")
        return 1
    
    if not results:
        print("\n❌ No SQL patterns found matching your query.")
        print("   Try: 'python -m sap_tools.sql_pattern \"purchase order\"'")
        print("   Or run: python -m sap_tools.sql_pattern --init")
        return 1
    
    # Apply role filter if specified
    if args.role and args.role in SAP_ROLES:
        auth_context = security_mesh.get_context(args.role)
        filtered = []
        for p in results:
            allowed = True
            for table in p.get("tables_used", []):
                if not auth_context.is_table_allowed(table):
                    allowed = False
                    break
            if allowed:
                filtered.append(p)
        print(f"   Role filter applied. {len(filtered)}/{len(results)} patterns authorized.")
        results = filtered
    
    if not results:
        print("\n❌ No authorized patterns found for your role.")
        return 1
    
    # Output
    print(f"\n✅ Found {len(results)} SQL pattern(s):")
    
    if args.json:
        import json
        print(json.dumps(results, indent=2))
    else:
        for i, pattern in enumerate(results, 1):
            print(f"\n{'─' * 60}")
            print(format_pattern_result(pattern, i))
    
    print(f"\n{'─' * 60}")
    print(f"[STATS] Total: {len(results)} pattern(s) returned")
    print("\n[TIP] Use these as templates. Replace {placeholders} with actual values.")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
