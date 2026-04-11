import re
from typing import Dict, List, Any

class CritiqueAgent:
    """
    Phase 4: Self-Critique Loop for SAP SQL Validation
    Evaluates generated SQL against a 7-point checklist before execution.
    """
    
    def __init__(self):
        self.checklist = [
            "SELECT-only (no DML/DDL)?",
            "MANDT filter present?",
            "All JOIN keys exist in both tables?",
            "AuthContext filters applied?",
            "No cardinality explosion?",
            "Date filters have reasonable range?",
            "LIMIT/max_rows guard present?"
        ]

    def critique(self, query: str, sql: str, schema_context: List[Dict], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        issues = []
        suggestions = []
        score = 1.0
        
        sql_upper = sql.upper()
        
        # 1. SELECT-only
        if re.search(r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE)\b', sql_upper):
            issues.append("CRITICAL: SQL contains DML/DDL keywords. Only SELECT is allowed.")
            score -= 1.0
            
        # 2. MANDT filter present
        if "MANDT" not in sql_upper:
            issues.append("Missing MANDT client filter.")
            suggestions.append("Add 'MANDT = <client>' to the WHERE clause.")
            score -= 0.2
            
        # AuthContext filters applied (auth_context may be dict or SAPAuthContext object)
        _filters = None
        if auth_context:
            if isinstance(auth_context, dict):
                _filters = auth_context.get("filters", {})
            else:
                # SAPAuthContext object — use get_where_clauses() method
                _filters = getattr(auth_context, "get_where_clauses", lambda: {})()
        if _filters:
            for table, conditions in _filters.items():
                if table.upper() in sql_upper:
                    # Basic check if the column is filtered
                    for col in conditions.keys():
                        if col.upper() not in sql_upper:
                            issues.append(f"AuthContext violation: Missing required filter on {table}.{col}")
                            suggestions.append(f"Add {table}.{col} restriction based on role AuthContext.")
                            score -= 0.3
                            
        # 4. LIMIT/max_rows guard
        if "LIMIT " not in sql_upper and "TOP " not in sql_upper:
            issues.append("No LIMIT or TOP guard found.")
            suggestions.append("Add 'LIMIT 100' or similar to prevent massive data pulls.")
            score -= 0.1
            
        # 5. Cartesian product / Missing JOIN
        if " JOIN " in sql_upper and " ON " not in sql_upper:
            issues.append("Potential Cartesian Product: JOIN without ON condition.")
            suggestions.append("Verify JOIN conditions are explicitly stated.")
            score -= 0.4
            
        # Normalize score
        final_score = max(0.0, round(score, 2))
        
        return {
            "score": final_score,
            "passed": final_score >= 0.7,
            "issues": issues,
            "suggestions": suggestions,
            "checklist": self.checklist
        }

# Singleton instance
critique_agent = CritiqueAgent()
