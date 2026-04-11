"""
self_healer.py — Phase 4 Self-Healing SQL Engine
=================================================
When SQL validation fails or execution produces an error, this module
attempts to automatically correct the SQL based on the error type.

Error → Fix mappings (SAP HANA + generic SQL):
  ORA-00942  → Table not found        → strip JOIN to missing table, retry single-table
  ORA-01799  → Column not in subquery  → remove subquery, use direct JOIN
  ORA-01476  → Division by zero        → wrap denominator with NVL(..., 1)
  42S22      → Invalid column          → remove offending column from SELECT
  37000      → Syntax error            → strip ORDER BY / complex WHERE, simplify
  SAP_AUTH   → Auth block              → add MANDT filter, retry
  MANDT_MISS → No client filter        → inject MANDT = '<client>'
  CARTESIAN  → Cartesian product       → add strict JOIN condition
  NO_ROWS    → Empty result            → relax WHERE, expand date range
  HANA_020   → Invalid identifier      → quote identifier or remove

Usage:
  from app.core.self_healer import SelfHealer, HEALING_RULES
  healer = SelfHealer()
  fixed, explanation = healer.heal(sql=sql, error=error, schema_context=ctx)
  if fixed:
      print(f"Auto-healed: {explanation}")
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Error → Healing Rule registry
# ---------------------------------------------------------------------------
@dataclass
class HealingRule:
    code: str                  # unique identifier
    triggers: List[str]        # substrings that appear in error messages
    description: str           # human-readable explanation
    apply: str                 # 'strip_join' | 'remove_column' | 'add_nvl' | 'add_mandt' | 'simplify' | 'relax_where'

    # For strip_join: which table to drop from JOIN clause
    drop_table_hint: Optional[str] = None
    # For remove_column: which column pattern to remove
    column_hint: Optional[str] = None


HEALING_RULES: List[HealingRule] = [
    HealingRule(
        code="MANDT_MISSING",
        triggers=["MANDT", "client", "missing client"],
        description="MANDT filter missing from SQL",
        apply="add_mandt",
    ),
    HealingRule(
        code="CARTESIAN_PRODUCT",
        triggers=["cartesian", "cross join", "combin*"],
        description="Potential Cartesian product detected",
        apply="simplify",
    ),
    HealingRule(
        code="DIVISION_BY_ZERO",
        triggers=["division", "divi", "divide by zero", "ORA-01476"],
        description="Division by zero in expression",
        apply="add_nvl",
    ),
    HealingRule(
        code="TABLE_NOT_FOUND",
        triggers=["table not found", "ORA-00942", "SAPABC", "invalid object",
                  "does not exist", "base table", "not found in ddic"],
        description="Referenced table does not exist in schema",
        apply="strip_join",
    ),
    HealingRule(
        code="INVALID_COLUMN",
        triggers=["invalid column", "column not found", "42S22", "unknown column",
                  "not a valid identifier", "HANA 020"],
        description="Column reference not valid",
        apply="remove_column",
    ),
    HealingRule(
        code="SYNTAX_ERROR",
        triggers=["syntax error", "37000", "SQL compilation failed",
                  "incorrect syntax", "parse error", "near"],
        description="SQL syntax error",
        apply="simplify",
    ),
    HealingRule(
        code="SUBQUERY_JOIN_ERROR",
        triggers=["subquery", "ORA-01799", "not allowed in join criterion"],
        description="Subquery used incorrectly in JOIN",
        apply="simplify",
    ),
    HealingRule(
        code="SAP_AUTH_BLOCK",
        triggers=["not authorized", "authorization", "auth object",
                  "SAPSQLX", "AUTH_BLOCK", "access denied"],
        description="Table/field not authorized for current role",
        apply="add_mandt",
    ),
    HealingRule(
        code="EMPTY_RESULT",
        triggers=["no rows", "empty result", "0 rows", "no data found"],
        description="Query returns no data — may need relaxed filters",
        apply="relax_where",
    ),
]


# ---------------------------------------------------------------------------
# SelfHealer class
# ---------------------------------------------------------------------------
class SelfHealer:
    """
    Autonomous SQL self-healing engine.
    Applies rule-based corrections to SQL that has failed validation or execution.
    """

    def __init__(self, rules: Optional[List[HealingRule]] = None):
        self.rules = rules or HEALING_RULES
        self._heal_count: Dict[str, int] = {}

    def heal(
        self,
        sql: str,
        error: str,
        schema_context: Optional[List[Dict]] = None,
        max_attempts: int = 2,
    ) -> Tuple[str, str, Optional[str]]:
        """
        Attempt to heal broken SQL.

        Args:
            sql: The SQL that failed
            error: The error message string
            schema_context: Optional list of {table, fields} dicts for context
            max_attempts: How many heal attempts to make (default 2)

        Returns:
            Tuple of (healed_sql, explanation, rule_code)
            If no rule matched: (original_sql, "no healing rule applied", None)
        """
        original_sql = sql
        error_lower = error.lower()

        for attempt in range(max_attempts):
            matched_rule = self._find_matching_rule(error_lower)
            if not matched_rule:
                return original_sql, "no healing rule applied", None

            self._heal_count[matched_rule.code] = self._heal_count.get(matched_rule.code, 0) + 1

            if matched_rule.apply == "add_mandt":
                sql, explanation = self._heal_add_mandt(sql, matched_rule.code)
            elif matched_rule.apply == "simplify":
                sql, explanation = self._heal_simplify(sql, matched_rule.code)
            elif matched_rule.apply == "strip_join":
                sql, explanation = self._heal_strip_join(sql, matched_rule, error_lower)
            elif matched_rule.apply == "remove_column":
                sql, explanation = self._heal_remove_column(sql, matched_rule, error_lower)
            elif matched_rule.apply == "add_nvl":
                sql, explanation = self._heal_add_nvl(sql, matched_rule.code)
            elif matched_rule.apply == "relax_where":
                sql, explanation = self._heal_relax_where(sql, matched_rule.code)
            else:
                return sql, f"unknown heal type: {matched_rule.apply}", matched_rule.code

            if sql != original_sql:
                return sql, f"[{matched_rule.code}] {explanation}", matched_rule.code

        return sql, "max heal attempts reached", None

    def _find_matching_rule(self, error_lower: str) -> Optional[HealingRule]:
        for rule in self.rules:
            for trigger in rule.triggers:
                if trigger.lower() in error_lower:
                    return rule
        return None

    # -------------------------------------------------------------------------
    # Individual healing strategies
    # -------------------------------------------------------------------------
    def _heal_add_mandt(self, sql: str, code: str) -> Tuple[str, str]:
        """Add MANDT = '100' WHERE clause if missing."""
        sql_upper = sql.upper()
        if "MANDT" in sql_upper:
            return sql, "MANDT already present"

        if "WHERE" in sql_upper:
            # Append to existing WHERE
            healed = re.sub(
                r'(\bWHERE\b.+)',
                r"\1\n  AND MANDT = '100'",
                sql,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
        else:
            # Add new WHERE
            where_pos = sql_upper.rfind("FROM")
            if where_pos == -1:
                where_pos = len(sql)
            healed = sql[:where_pos] + "\n WHERE MANDT = '100'" + sql[where_pos:]

        return healed, "injected MANDT = '100' filter"

    def _heal_simplify(self, sql: str, code: str) -> Tuple[str, str]:
        """
        Simplify SQL by removing complex clauses.
        Removes: ORDER BY (if complex), excessive JOINs, complex subqueries.
        """
        original = sql
        sql_upper = sql.upper()

        # Strip ORDER BY clause (preserve if simple)
        if "ORDER BY" in sql_upper:
            # Check if ORDER BY references a column that might be invalid
            simplified = re.sub(
                r'\bORDER\s+BY\s+[^;]+?(?=\bLIMIT\b|\bWHERE\b|;|$)',
                '',
                sql,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            if simplified != original:
                return simplified.rstrip().rstrip(';') + ';', "removed ORDER BY clause"

        # Remove trailing commas before FROM (syntax fix)
        fixed = re.sub(r',\s*\n\s*FROM\b', '\nFROM', sql, count=1, flags=re.IGNORECASE)
        if fixed != sql:
            return fixed, "fixed trailing comma before FROM"

        # Remove duplicate WHERE keywords
        fixed = re.sub(r'\bWHERE\b.*\bWHERE\b', 'WHERE', sql, count=1, flags=re.IGNORECASE)
        if fixed != sql:
            return fixed, "removed duplicate WHERE"

        # As last resort, strip complex JOINs and keep first table only
        if " JOIN " in sql_upper:
            first_from = sql_upper.find(" FROM ")
            if first_from != -1:
                select_part = sql[:first_from]
                from_clause = sql[first_from:].split(" WHERE ")[0].split(" ORDER ")[0]
                return (select_part + from_clause + " WHERE MANDT = '100';"), \
                    "reduced to single-table query (JOINs removed)"

        return original, "no simplification applicable"

    def _heal_strip_join(
        self,
        sql: str,
        rule: HealingRule,
        error_lower: str,
    ) -> Tuple[str, str]:
        """
        Remove a problematic table from JOIN clause.
        If we know which table is bad, drop it.
        Otherwise, remove the last JOIN in the chain.
        """
        sql_upper = sql.upper()

        # Try to identify the bad table from the error message
        bad_table = self._extract_table_from_error(error_lower)

        if bad_table and bad_table.upper() in sql_upper:
            # Remove all references to the bad table (JOIN + ON conditions)
            # Drop the entire JOIN block for this table
            pattern = rf'\bLEFT\s+JOIN\b[^\n]*\b{bad_table}\b[^\n]*\n?'
            fixed = re.sub(pattern, '', sql, count=1, flags=re.IGNORECASE)
            pattern = rf'\bRIGHT\s+JOIN\b[^\n]*\b{bad_table}\b[^\n]*\n?'
            fixed = re.sub(pattern, '', fixed, count=1, flags=re.IGNORECASE)
            pattern = rf'\bJOIN\b[^\n]*\b{bad_table}\b[^\n]*\n?'
            fixed = re.sub(pattern, '', fixed, count=1, flags=re.IGNORECASE)
            if fixed != sql:
                return fixed, f"removed JOIN to unavailable table: {bad_table}"

        # Fallback: remove the last JOIN clause
        join_positions = [m.start() for m in re.finditer(r'\bJOIN\b', sql_upper)]
        if join_positions:
            last_join = join_positions[-1]
            # Find the next FROM or WHERE after the JOIN
            after_join = sql_upper[last_join:]
            next_from = re.search(r'\bFROM\b', after_join[5:], re.IGNORECASE)
            next_where = re.search(r'\bWHERE\b', after_join[5:], re.IGNORECASE)
            end_pos = len(sql)
            if next_from:
                end_pos = min(end_pos, last_join + 5 + next_from.start())
            if next_where:
                end_pos = min(end_pos, last_join + 5 + next_where.start())
            fixed = sql[:last_join] + sql[end_pos:]
            return fixed, "removed last JOIN clause (suspected invalid table)"

        return sql, "cannot strip JOIN: no JOIN found"

    def _heal_remove_column(
        self,
        sql: str,
        rule: HealingRule,
        error_lower: str,
    ) -> Tuple[str, str]:
        """Remove an invalid column from SELECT clause."""
        # Try to extract the column name from error
        col_name = self._extract_column_from_error(error_lower)

        if col_name:
            # Remove alias patterns like 'AS COL' or bare 'COL'
            pattern = rf',?\s*(\w+\.)?{re.escape(col_name)}\s*(AS\s+\w+)?'
            fixed = re.sub(pattern, '', sql, count=1, flags=re.IGNORECASE)
            if fixed != sql:
                return fixed, f"removed invalid column: {col_name}"

        # Fallback: if error is about a specific pattern, strip SELECT to *
        if "SELECT DISTINCT" in sql.upper():
            fixed = re.sub(r'SELECT DISTINCT', 'SELECT', sql, count=1, flags=re.IGNORECASE)
            return fixed, "changed SELECT DISTINCT to SELECT (column may be duplicate)"
        elif re.search(r'SELECT\s+.+\s+FROM', sql, re.IGNORECASE):
            # Replace SELECT ... FROM with SELECT * FROM
            fixed = re.sub(
                r'SELECT\s+[^;]+?\s+FROM',
                'SELECT * FROM',
                sql,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if fixed != sql:
                return fixed, "replaced SELECT clause with SELECT * (column resolution failed)"

        return sql, "cannot identify invalid column to remove"

    def _heal_add_nvl(self, sql: str, code: str) -> Tuple[str, str]:
        """Wrap potential division operations with NVL/IFNULL."""
        original = sql

        # Pattern: column / column — wrap denominator
        fixed = re.sub(
            r'(\w+\.\w+)\s*/\s*(\w+\.\w+)',
            r'CASE WHEN \2 = 0 THEN NULL ELSE \1 / \2 END',
            sql,
            count=2,
            flags=re.IGNORECASE,
        )
        if fixed != original:
            return fixed, "wrapped division with CASE WHEN denominator=0 guard"

        # Also handle simple arithmetic: col / 0
        fixed = re.sub(
            r'(\w+)\s*/\s*0(?!\d)',
            r'CASE WHEN \1 IS NULL THEN NULL ELSE \1 / NULL END',
            sql,
            count=2,
            flags=re.IGNORECASE,
        )
        if fixed != original:
            return fixed, "guarded division-by-zero expression"

        return original, "no division expression found"

    def _heal_relax_where(self, sql: str, code: str) -> Tuple[str, str]:
        """
        Relax WHERE clause to return more data.
        Strategies: remove date range limits, expand company codes, remove specific filters.
        """
        original = sql
        sql_upper = sql.upper()

        # Remove date range restrictions
        date_patterns = [
            r"AND\s+\w+\.(BUDAT|GBSTK|ERDAT|UDATE|PRREG)\s*>=?\s*'[^']+'",  # SAP date fields
            r"AND\s+\w+\.(BUDAT|GBSTK|ERDAT|UDATE|PRREG)\s*<=?\s*'[^']+'",
            r"WHERE\s+\w+\.(BUDAT|GBSTK|ERDAT|UDATE|PRREG)\s*>=?\s*'[^']+'",
        ]
        for pattern in date_patterns:
            fixed = re.sub(pattern, '', sql, count=1, flags=re.IGNORECASE)
            if fixed != original:
                return fixed, "relaxed date filter (removed lower bound)"

        # Remove specific vendor/material filters that might be too narrow
        narrow_filters = [
            r"AND\s+\w+\.(LIFNR|MATNR|KUNNR)\s*=\s*'[^']+'",
            r"WHERE\s+\w+\.(LIFNR|MATNR|KUNNR)\s*=\s*'[^']+'",
        ]
        for pattern in narrow_filters:
            fixed = re.sub(pattern, '', sql, count=1, flags=re.IGNORECASE)
            if fixed != original:
                return fixed, "relaxed entity filter (removed specific ID)"

        # As last resort: remove LIMIT or reduce it
        limit_match = re.search(r'LIMIT\s+(\d+)', sql_upper)
        if limit_match:
            current = int(limit_match.group(1))
            if current < 1000:
                fixed = re.sub(r'LIMIT\s+\d+', f'LIMIT {current * 5}', sql, count=1, flags=re.IGNORECASE)
                return fixed, f"increased LIMIT from {current} to {current * 5}"

        return original, "no relaxable filter found"

    # -------------------------------------------------------------------------
    # Error text extraction utilities
    # -------------------------------------------------------------------------
    def _extract_table_from_error(self, error_lower: str) -> Optional[str]:
        """Try to pull a table name out of an error message."""
        # SAP-style: "Table BSEC not found in DDIC"
        m = re.search(r'table\s+(\w{3,6})\s+not', error_lower)
        if m:
            return m.group(1)
        # Oracle-style: "ORA-00942: table 'LFA1' does not exist"
        m = re.search(r"table\s+'?(\w{3,6})'?\s+(does not exist|not found)", error_lower)
        if m:
            return m.group(1)
        # Generic: "invalid object NAME"
        m = re.search(r'invalid object\s+(\w+)', error_lower)
        if m:
            return m.group(1)
        return None

    def _extract_column_from_error(self, error_lower: str) -> Optional[str]:
        """Try to pull a column name out of an error message."""
        # "invalid column NAME"
        m = re.search(r'invalid column\s+(\w+)', error_lower)
        if m:
            return m.group(1)
        # "column not found: KNA1.STCD3"
        m = re.search(r'column not found:?\s*(\w+\.)?(\w+)', error_lower)
        if m:
            return m.group(2)
        # "Unknown column 'BUKRS'" (HANA-style)
        m = re.search(r"unknown column\s+'?(\w+)'?", error_lower)
        if m:
            return m.group(1)
        return None

    # -------------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------------
    @property
    def heal_stats(self) -> Dict[str, int]:
        """Return count of heals applied per rule code."""
        return dict(self._heal_count)

    def reset_stats(self):
        self._heal_count.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
self_healer = SelfHealer()
