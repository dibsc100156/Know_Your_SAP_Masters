#!/usr/bin/env python3
"""
sap_tools.mask — Column Masking CLI (Pillar 1)

Usage:
    python -m sap_tools.mask --role AP_CLERK --data '{"LIFNR": "1000", "BANKN": "123456789"}'
    python -m sap_tools.mask --role CFO_GLOBAL --data '{"LIFNR": "1000", "BANKN": "123456789"}'
    cat results.json | python -m sap_tools.mask --role AP_CLERK

Applies role-based column masking to result sets.
Shows the difference between masked and unmasked output for a given role.
"""

import sys
import os
import argparse
import json
from typing import List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.security import SAP_ROLES, security_mesh, SAPAuthContext


def apply_masking(data: List[Dict], auth_context: SAPAuthContext) -> tuple:
    """Apply masking to a result set. Returns (masked_data, masked_fields)."""
    masked_fields = []
    
    if not auth_context.masked_fields or not data:
        return data, []
    
    result = []
    for row in data:
        masked_row = row.copy()
        for col, value in row.items():
            # Check if this column should be masked
            mask_key = f"{col}".upper()
            is_masked = any(
                mask.upper() == mask_key or 
                mask.upper().endswith(f"-{mask_key}")
                for mask in auth_context.masked_fields.keys()
            )
            if is_masked:
                masked_row[col] = "*****"
                masked_fields.append(f"{col}")
        result.append(masked_row)
    
    return result, list(set(masked_fields))


def format_comparison(original: List[Dict], masked: List[Dict], role: str) -> str:
    """Format a before/after comparison for CLI output."""
    output = []
    
    role_ctx = SAP_ROLES[role]
    
    output.append(f"\n{'=' * 60}")
    output.append(f"  🔐 MASKING REPORT — Role: {role}")
    output.append(f"{'=' * 60}")
    output.append(f"  Description: {role_ctx.description}")
    
    masked_keys = list(role_ctx.masked_fields.keys())
    output.append(f"\n  [SEC] Masked Fields ({len(masked_keys)}):")
    for k in masked_keys:
        output.append(f"     • {k}")
    
    output.append(f"\n  [TABLE] Before -> After:")
    
    for orig_row, mask_row in zip(original, masked):
        for key in orig_row:
            if orig_row[key] != mask_row[key]:
                output.append(f"     {key}:")
                output.append(f"       Before: {orig_row[key]}")
                output.append(f"       After:  {'*****' if mask_row[key] == '*****' else mask_row[key]}")
    
    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="[Pillar 1] Apply role-based column masking to result sets"
    )
    parser.add_argument("--role", type=str, required=True,
                        choices=list(SAP_ROLES.keys()),
                        help="Role to apply masking for")
    parser.add_argument("--data", type=str, default=None,
                        help="JSON data to mask (single row object)")
    parser.add_argument("--json", type=str, default=None,
                        help="JSON array of rows to mask")
    parser.add_argument("--file", type=str, default=None,
                        help="Read JSON from file instead of stdin/arg")
    parser.add_argument("--show-unmasked", action="store_true",
                        help="Also show the unmasked (original) data")
    
    args = parser.parse_args()
    
    # Read data
    raw_data = None
    
    if args.data:
        try:
            raw_data = [json.loads(args.data)]
        except json.JSONDecodeError:
            print("❌ Invalid JSON in --data. Use: '{\"col\": \"value\"}'")
            return 1
    elif args.json:
        try:
            raw_data = json.loads(args.json)
            if isinstance(raw_data, dict):
                raw_data = [raw_data]
        except json.JSONDecodeError:
            print("❌ Invalid JSON in --json")
            return 1
    elif args.file:
        try:
            with open(args.file) as f:
                raw_data = json.load(f)
                if isinstance(raw_data, dict):
                    raw_data = [raw_data]
        except Exception as e:
            print(f"❌ Could not read file: {e}")
            return 1
    elif not sys.stdin.isatty():
        try:
            raw_data = json.load(sys.stdin)
            if isinstance(raw_data, dict):
                raw_data = [raw_data]
        except json.JSONDecodeError:
            print("❌ Invalid JSON from stdin")
            return 1
    else:
        print("❌ No data provided.")
        print("   Usage: python -m sap_tools.mask --role AP_CLERK --data '{\"BANKN\": \"123\"}'")
        print("   Or:    cat results.json | python -m sap_tools.mask --role AP_CLERK")
        return 1
    
    # Get auth context
    auth_context = security_mesh.get_context(args.role)
    
    print(f"\n🔐 [MASK] Applying masking for role: {args.role}")
    print(f"   Rows: {len(raw_data)}")
    
    # Apply masking
    masked_data, masked_fields = apply_masking(raw_data, auth_context)
    
    # Output
    if args.show_unmasked:
        print(format_comparison(raw_data, masked_data, args.role))
    else:
        print(f"\n✅ Masking applied:")
        print(json.dumps(masked_data, indent=2, default=str))
        if masked_fields:
            print(f"\n   [SEC] Masked fields: {', '.join(set(masked_fields))}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
