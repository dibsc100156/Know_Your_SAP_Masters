#!/usr/bin/env python3
"""
sap_tools.execute — SQL Execution CLI (Dry-Run + Mock)

Usage:
    python -m sap_tools.execute "SELECT * FROM LFA1 WHERE MANDT = '100'"
    python -m sap_tools.execute --sql "SELECT EBELN, NETPR FROM EKKO WHERE BUKRS = '1000'" --role AP_CLERK --dry-run

Executes validated SQL against mock SAP HANA (--dry-run mode) or
validates without executing (--validate-only).
In production, replace mock with real hdbcli connection.
"""

import sys
import os
import argparse
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tools.sql_executor import SAPSQLExecutor
from app.core.security import SAP_ROLES, security_mesh, SAPAuthContext


def format_results(df: pd.DataFrame, masked_fields: list) -> str:
    """Format DataFrame results for CLI output."""
    if df is None or df.empty:
        return "  (No rows returned)"
    
    output = []
    
    # Column headers
    col_widths = []
    for col in df.columns:
        max_val = max(len(str(col)), df[col].astype(str).str.len().max())
        col_widths.append(min(max_val, 30))
    
    # Header row
    header = "  | " + " | ".join(str(col).ljust(w)[:w] for col, w in zip(df.columns, col_widths)) + " |"
    separator = "  +" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    
    output.append(separator)
    output.append(header)
    output.append(separator.replace("-", "="))
    
    # Data rows
    for _, row in df.iterrows():
        vals = []
        for val, w in zip(row, col_widths):
            v = str(val)[:w]
            vals.append(v.ljust(w))
        output.append("  | " + " | ".join(vals) + " |")
    
    output.append(separator)
    output.append(f"  {len(df)} row(s) returned")
    
    if masked_fields:
        output.append(f"  [SEC] Masked fields: {', '.join(masked_fields)}")
    
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="[Execution] Execute validated SAP SQL against mock HANA or dry-run"
    )
    parser.add_argument("sql", type=str, nargs="?", default=None, help="SQL query to execute")
    parser.add_argument("--sql", dest="sql_arg", type=str, default=None, help="SQL query (--sql variant)")
    parser.add_argument("--role", type=str, default="AP_CLERK",
                        choices=list(SAP_ROLES.keys()),
                        help="Role for execution context (default: AP_CLERK)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate SQL but don't execute (default: True when no mock data)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually execute (requires real HANA connection)")
    parser.add_argument("--max-rows", type=int, default=1000,
                        help="Row limit (default: 1000)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    
    args = parser.parse_args()
    
    # Get SQL
    sql = args.sql or args.sql_arg
    if not sql:
        print("❌ No SQL provided. Use positional argument or --sql.")
        print("   python -m sap_tools.execute \"SELECT * FROM LFA1 WHERE MANDT = '100'\"")
        return 1
    
    print(f"\n[RUN] [EXECUTE] Role: {args.role}")
    print(f"   SQL: {sql[:80]}{'...' if len(sql) > 80 else ''}")
    
    # Get auth context
    auth_context = security_mesh.get_context(args.role)
    
    # Initialize executor
    executor = SAPSQLExecutor(connection=None, max_rows=args.max_rows)
    
    if args.dry_run or not args.execute:
        print("   Mode: DRY RUN (mock data only)")
        
        # Validate first
        print("\n[LOOKUP] Pre-execution validation...")
        try:
            executor._validate_sql_safety(sql)
            executor._validate_table_access(sql, auth_context)
            print("   ✅ Safety checks passed")
        except PermissionError as e:
            print(f"\n   ❌ VALIDATION FAILED: {e}")
            return 1
        
        # Execute mock
        print("\n[STATS] Executing mock query...")
        try:
            df = executor._mock_execution(sql)
            df_masked = executor._mask_results(df, auth_context)
            
            masked = [f for f in auth_context.masked_fields.keys() 
                     if any(c.upper() in f.upper() for c in df.columns)]
            
            if args.json:
                import json
                result = {
                    "status": "success",
                    "rows_returned": len(df_masked),
                    "sql": sql,
                    "masked_fields": masked,
                    "data": df_masked.to_dict(orient="records")
                }
                print(json.dumps(result, indent=2, default=str))
            else:
                print(format_results(df_masked, masked))
                print("\n   [WARN]️  NOTE: This is mock data. Real HANA execution requires --execute")
                
        except Exception as e:
            print(f"\n   ❌ EXECUTION ERROR: {e}")
            return 1
    else:
        print("   Mode: LIVE EXECUTION")
        print("   [WARN]️  Connecting to SAP HANA...")
        
        if not executor.connection:
            print("   ❌ No HANA connection configured. Set up hdbcli in production.")
            print("   Falling back to dry-run mode.")
            args.dry_run = True
            return main()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
