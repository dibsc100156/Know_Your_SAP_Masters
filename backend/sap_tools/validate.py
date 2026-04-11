#!/usr/bin/env python3
"""
sap_tools.validate — SQL Validation CLI (Security + Syntax)

Usage:
    echo "SELECT * FROM EKKO WHERE MANDT = '100'" | python -m sap_tools.validate --role AP_CLERK
    python -m sap_tools.validate --sql "SELECT LIFNR, NAME1 FROM LFA1 WHERE MANDT = '100'"
    python -m sap_tools.validate --sql "UPDATE LFA1 SET NAME1 = 'Hacked'" --role CFO_GLOBAL

Validates SAP HANA SQL for:
1. Read-only (no DML/DDL)
2. Role-based table access
3. MANDT presence
4. AuthContext filter injection
"""

import sys
import os
import argparse
import re
from typing import Optional, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.security import SAP_ROLES, security_mesh, SAPAuthContext


class SQLValidator:
    """Validates SQL queries against SAP security and quality rules."""
    
    FORBIDDEN_KEYWORDS = [
        "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", 
        "TRUNCATE", "GRANT", "REVOKE", "CREATE", "EXECUTE",
        "MERGE", "COMMIT", "ROLLBACK"
    ]
    
    def __init__(self, auth_context: Optional[SAPAuthContext] = None):
        self.auth_context = auth_context
        self.issues: List[Tuple[str, str]] = []  # (severity, message)
    
    def validate(self, sql: str) -> bool:
        """Run all validation checks. Returns True if valid, False otherwise."""
        self.issues = []
        
        sql_upper = sql.strip().upper()
        
        # Check 1: Must be SELECT
        if not sql_upper.startswith("SELECT"):
            self.issues.append(("ERROR", "Query must be a SELECT statement. No DML/DDL permitted."))
            return False
        
        # Check 2: No forbidden keywords
        for keyword in self.FORBIDDEN_KEYWORDS:
            pattern = rf"\b{keyword}\b"
            if re.search(pattern, sql_upper):
                self.issues.append(("ERROR", f"Forbidden keyword detected: {keyword}"))
        
        # Check 3: MANDT presence
        if "MANDT" not in sql_upper and "CLIENT" not in sql_upper:
            self.issues.append(("WARNING", "No MANDT/CLIENT filter detected. Best practice: always filter by client."))
        
        # Check 4: Role-based table access
        if self.auth_context:
            self._check_table_access(sql_upper)
        
        # Check 5: Injection patterns
        if re.search(r";\s*\w+", sql) or "--" in sql or "/*" in sql:
            self.issues.append(("WARNING", "Suspicious SQL patterns detected (comment or multiple statements)."))
        
        # Check 6: No SELECT * for sensitive tables
        if "SELECT *" in sql_upper:
            sensitive_tables = ["LFA1", "KNA1", "PA0008", "PAYR"]
            for table in sensitive_tables:
                if table in sql_upper:
                    self.issues.append(("INFO", f"SELECT * on sensitive table {table}. Consider selecting specific columns."))
                    break
        
        return not any(severity == "ERROR" for severity, _ in self.issues)
    
    def _check_table_access(self, sql_upper: str):
        """Check if user has access to all tables in the query."""
        # Extract table names from FROM and JOIN
        pattern = r"(?:FROM|JOIN)\s+([A-Z0-9_]+)"
        tables = re.findall(pattern, sql_upper)
        
        for table in tables:
            # Clean up aliases
            table = table.split()[0] if ' ' in table else table
            
            # Check denied tables
            if not self.auth_context.is_table_allowed(table):
                self.issues.append(("ERROR", f"Access DENIED to table {table} for role {self.auth_context.role_id}"))
            
            # Check org-level scope
            if table in ["LFB1", "BSIK", "BSAK"] and "BUKRS" not in sql_upper:
                self.issues.append(("WARNING", f"Table {table} queried without BUKRS filter. Role restricts to: {self.auth_context.allowed_bukrs}"))
            
            if table in ["EKKO", "EKPO", "EINA"] and "EKORG" not in sql_upper:
                if self.auth_context.allowed_ekorgs and "*" not in self.auth_context.allowed_ekorgs:
                    self.issues.append(("WARNING", f"Table {table} queried without EKORG filter. Role restricts to: {self.auth_context.allowed_ekorgs}"))
    
    def suggest_where_clauses(self) -> List[str]:
        """Suggest AuthContext WHERE clauses based on the query."""
        suggestions = []
        
        if self.auth_context:
            if self.auth_context.allowed_bukrs and "*" not in self.auth_context.allowed_bukrs:
                bukrs_list = "', '".join(self.auth_context.allowed_bukrs)
                suggestions.append(f"BUKRS IN ('{bukrs_list}')")
            
            if self.auth_context.allowed_ekorgs and "*" not in self.auth_context.allowed_ekorgs:
                ekorg_list = "', '".join(self.auth_context.allowed_ekorgs)
                suggestions.append(f"EKORG IN ('{ekorg_list}')")
            
            if self.auth_context.allowed_werks and "*" not in self.auth_context.allowed_werks:
                werks_list = "', '".join(self.auth_context.allowed_werks)
                suggestions.append(f"WERKS IN ('{werks_list}')")
        
        return suggestions


def main():
    parser = argparse.ArgumentParser(
        description="[Security] Validate SAP SQL for safety, syntax, and role-based access"
    )
    parser.add_argument("--sql", type=str, default=None, help="SQL query to validate")
    parser.add_argument("--role", type=str, default=None,
                        choices=list(SAP_ROLES.keys()),
                        help="Role to validate against")
    parser.add_argument("--strict", action="store_true", 
                        help="Treat warnings as errors (exit code non-zero)")
    parser.add_argument("--suggest", action="store_true",
                        help="Output suggested AuthContext WHERE clauses")
    
    args = parser.parse_args()
    
    # Read SQL from stdin or argument
    if args.sql:
        sql = args.sql
    elif not sys.stdin.isatty():
        sql = sys.stdin.read().strip()
    else:
        print("❌ No SQL provided. Use --sql or pipe SQL via stdin.")
        print("\nExamples:")
        print("  python -m sap_tools.validate --sql \"SELECT * FROM LFA1 WHERE MANDT = '100'\"")
        print("  echo \"SELECT * FROM EKKO\" | python -m sap_tools.validate --role AP_CLERK")
        return 1
    
    print(f"\n[LOOKUP] [VALIDATE] Checking SQL for role: {args.role or 'no role'}")
    print(f"   SQL: {sql[:80]}{'...' if len(sql) > 80 else ''}")
    
    # Get auth context
    auth_context = None
    if args.role and args.role in SAP_ROLES:
        auth_context = security_mesh.get_context(args.role)
        print(f"   Role: {auth_context.role_id} — {auth_context.description}")
    
    # Validate
    validator = SQLValidator(auth_context)
    is_valid = validator.validate(sql)
    
    # Report
    if not validator.issues:
        print("\n✅ SQL passed all checks!")
    else:
        for severity, message in validator.issues:
            icon = "❌" if severity == "ERROR" else "[WARN]️" if severity == "WARNING" else "[INFO]️"
            print(f"\n   {icon} [{severity}] {message}")
    
    # Suggestions
    if args.suggest and auth_context:
        suggestions = validator.suggest_where_clauses()
        if suggestions:
            print(f"\n[TIP] Suggested AuthContext WHERE clauses to add:")
            for s in suggestions:
                print(f"      {s}")
        else:
            print(f"\n[TIP] No additional WHERE clauses needed (role has full access or no org restrictions).")
    
    # Exit code
    if not is_valid:
        print(f"\n❌ VALIDATION FAILED — SQL contains errors.")
        return 1
    elif args.strict and any(s == "WARNING" for s, _ in validator.issues):
        print(f"\n[WARN]️  STRICT MODE — Warnings treated as errors.")
        return 1
    else:
        print(f"\n✅ VALIDATION PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
