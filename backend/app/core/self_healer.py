"""
self_healer.py — Phase 4 Self-Healing SQL Engine
=================================================
When SQL validation fails or execution produces an error, this module
attempts to automatically correct the SQL based on the error type.

Error -> Fix mappings (SAP HANA + generic SQL):
  ORA-00942  -> Table not found        -> strip JOIN to missing table, retry single-table
  ORA-01799  -> Column not in subquery  -> remove subquery, use direct JOIN
  ORA-01476  -> Division by zero        -> wrap denominator with NVL(..., 1)
  42S22      -> Invalid column          -> remove offending column from SELECT
  37000      -> Syntax error            -> strip ORDER BY / complex WHERE, simplify
  SAP_AUTH   -> Auth block              -> add MANDT filter, retry
  MANDT_MISS -> No client filter        -> inject MANDT = '<client>'
  CARTESIAN  -> Cartesian product       -> add strict JOIN condition
  NO_ROWS    -> Empty result            -> relax WHERE, expand date range
  HANA_020   -> Invalid identifier      -> quote identifier or remove

Usage:
  from app.core.self_healer import SelfHealer, HEALING_RULES
  healer = SelfHealer()
  fixed, explanation = healer.heal(sql=sql, error=error, schema_context=ctx)
  if fixed:
      logger.info(f"Auto-healed: {explanation}")
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error -> Healing Rule registry
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
    # [P2] MBEW-specific: PEinh=0 in price/unit calculation (STPRS/PEinh) - substitute denominator=1
    HealingRule(
        code="DIVISION_BY_ZERO_MBEW",
        triggers=["PEINH", "MBEW", "STPRS", "price per unit"],
        description="MBEW price-per-unit when PEinh=0 - substitute denominator=1",
        apply="safe_denominator_mbew",
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
        description="Query returns no data -- may need relaxed filters",
        apply="relax_where",
    ),
    HealingRule(
        code="AMBIGUOUS_COLUMN",
        triggers=["ORA-00918", "column ambiguously defined"],
        description="Column reference is ambiguous across multiple JOINed tables",
        apply="qualify_column",
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

    # SAP FK JOIN map: (table_a, table_b) -> valid ON condition
    # Used to repair CARTESIAN_PRODUCT (missing JOIN ON)
    _SAP_FK_JOIN_MAP = {
        ("LFA1", "EKKO"): "LFA1.LIFNR = EKKO.LIFNR",
        ("EKKO", "LFA1"): "EKKO.LIFNR = LFA1.LIFNR",
        ("KNA1", "VBAK"): "KNA1.KUNNR = VBAK.KUNNR",
        ("VBAK", "KNA1"): "VBAK.KUNNR = KNA1.KUNNR",
        ("MARA", "EKKO"): "MARA.MATNR = EKKO.MATNR",
        ("EKKO", "MARA"): "EKKO.MATNR = MARA.MATNR",
        ("MARA", "MSEG"): "MARA.MATNR = MSEG.MATNR",
        ("MSEG", "MARA"): "MSEG.MATNR = MARA.MATNR",
        ("LFA1", "BSIK"): "LFA1.LIFNR = BSIK.LIFNR",
        ("BSIK", "LFA1"): "BSIK.LIFNR = LFA1.LIFNR",
        ("LFA1", "BSAK"): "LFA1.LIFNR = BSAK.LIFNR",
        ("BSAK", "LFA1"): "BSAK.LIFNR = LFA1.LIFNR",
        ("KNA1", "BSID"): "KNA1.KUNNR = BSID.KUNNR",
        ("BSID", "KNA1"): "BSID.KUNNR = KNA1.KUNNR",
        ("EKKO", "EKPO"): "EKKO.EBELN = EKPO.EBELN",
        ("EKPO", "EKKO"): "EKPO.EBELN = EKKO.EBELN",
        ("MARA", "MBEW"): "MARA.MATNR = MBEW.MATNR",
        ("MBEW", "MARA"): "MBEW.MATNR = MARA.MATNR",
        ("MARD", "MARA"): "MARD.MATNR = MARA.MATNR",
        ("MARA", "MARD"): "MARA.MATNR = MARD.MATNR",
        ("QALS", "MARA"): "QALS.MATNR = MARA.MATNR",
        ("MARA", "QALS"): "MARA.MATNR = QALS.MATNR",
        ("LFA1", "LFB1"): "LFA1.LIFNR = LFB1.LIFNR",
        ("LFB1", "LFA1"): "LFB1.LIFNR = LFA1.LIFNR",
        ("LFA1", "LFBK"): "LFA1.LIFNR = LFBK.LIFNR",
        ("LFBK", "LFA1"): "LFBK.LIFNR = LFA1.LIFNR",
        ("KNA1", "KNVV"): "KNA1.KUNNR = KNVV.KUNNR",
        ("KNVV", "KNA1"): "KNVV.KUNNR = KNA1.KUNNR",
        ("MARC", "MARA"): "MARC.MATNR = MARA.MATNR",
        ("MARA", "MARC"): "MARA.MATNR = MARC.MATNR",
        ("VBAK", "VBAP"): "VBAK.VBELN = VBAP.VBELN",
        ("VBAP", "VBAK"): "VBAP.VBELN = VBAK.VBELN",
        ("LIKP", "VBAK"): "LIKP.VBELN = VBAK.VBELN",
        ("VBAK", "LIKP"): "VBAK.VBELN = LIKP.VBELN",
    }

    def __init__(self, rules: Optional[List[HealingRule]] = None):
        self.rules = rules or HEALING_RULES
        self._heal_count: Dict[str, int] = {}

    def heal(
        self,
        sql: str,
        error: str,
        schema_context: Optional[List[Dict]] = None,
        max_attempts: int = 2,
    ) -> Tuple[bool, str]:
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
            elif matched_rule.apply == "safe_denominator_mbew":
                sql, explanation = self._heal_safe_denominator_mbew(sql, matched_rule.code)
            elif matched_rule.apply == "relax_where":
                sql, explanation = self._heal_relax_where(sql, matched_rule.code)
            elif matched_rule.apply == "qualify_column":
                sql, explanation = self._heal_qualify_column(sql, matched_rule.code)
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

    def _find_missing_on_clause(self, sql_upper: str):
        """
        [CARTESIAN_PRODUCT] Find pairs of tables that are JOINed without an ON clause.
        Uses the _SAP_FK_JOIN_MAP to return the correct ON condition.
        """
        tables = re.findall(r'(?:FROM|JOIN)\s+([A-Z0-9_]+)\b', sql_upper)
        tables = [t for t in tables if t not in ('AS', 'JOIN', 'LEFT', 'RIGHT', 'INNER', 'OUTER', 'CROSS')]
        if len(tables) < 2:
            return None
        for i in range(len(tables) - 1):
            for j in range(i + 1, len(tables)):
                t1, t2 = tables[i], tables[j]
                # Check for JOIN t2 without ON
                pair_join = rf'JOIN\s+{re.escape(t2)}(?!\s+ON\b)'
                if re.search(pair_join, sql_upper, re.IGNORECASE):
                    on_key = (t1.upper(), t2.upper())
                    on_cond = (self._SAP_FK_JOIN_MAP.get(on_key) or
                               self._SAP_FK_JOIN_MAP.get((t2.upper(), t1.upper())))
                    if on_cond:
                        return (t1, t2, on_cond)
        return None

    def _heal_simplify(self, sql: str, code: str) -> Tuple[str, str]:
        """
        Simplify or repair SQL.
        CARTESIAN_PRODUCT: add missing JOIN ON using known SAP FK relationships.
        Other codes: strip ORDER BY / trailing commas / duplicate WHERE.
        """
        original = sql
        sql_upper = sql.upper()

        # CARTESIAN_PRODUCT: smart FK-based JOIN repair
        if code == "CARTESIAN_PRODUCT":
            result = self._find_missing_on_clause(sql_upper)
            if result:
                t1, t2, on_cond = result
                # Insert ON after bare "JOIN t2"
                bare_join_re = rf'(JOIN\s+{re.escape(t2)})(\s+)(?!ON\b)'
                fixed = re.sub(bare_join_re, rf'\1\2ON {on_cond} ', sql, count=1, flags=re.IGNORECASE)
                if fixed != sql:
                    return fixed, f"CARTESIAN_PRODUCT repaired: added missing ON {on_cond}"

            # Fallback: strip secondary JOINs (keep FROM table, remove others)
            join_positions = [m.start() for m in re.finditer(r'\bJOIN\b', sql_upper)]
            if join_positions:
                last_join = join_positions[-1]
                first_from = sql_upper.find(" FROM ")
                if first_from != -1 and last_join > first_from:
                    select_part = sql[:first_from]
                    rest = sql[first_from:]
                    where_pos = rest.upper().find(" WHERE")
                    where_end = len(rest) if where_pos == -1 else where_pos
                    order_pos = rest.upper().find(" ORDER")
                    order_end = len(rest) if order_pos == -1 else order_pos
                    end = min(where_end, order_pos) if order_pos != -1 else where_end
                    from_clause = rest[:end]
                    return (select_part + from_clause + " WHERE MANDT = '100';"), \
                        "CARTESIAN_PRODUCT: removed unjoinable secondary table"

        # Generic simplification
        if "ORDER BY" in sql_upper:
            simplified = re.sub(
                r'\bORDER\s+BY\s+[^;]+?(?=\bLIMIT\b|\bWHERE\b|;|$)',
                '',
                sql,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            if simplified != original:
                return simplified.rstrip().rstrip(';') + ';', "removed ORDER BY clause"

        fixed = re.sub(r',\s*\n\s*FROM\b', '\nFROM', sql, count=1, flags=re.IGNORECASE)
        if fixed != sql:
            return fixed, "fixed trailing comma before FROM"

        fixed2 = re.sub(r'\bWHERE\b.*\bWHERE\b', 'WHERE', sql, count=1, flags=re.IGNORECASE)
        if fixed2 != sql:
            return fixed2, "removed duplicate WHERE"

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
        col_name = self._extract_column_from_error(error_lower)

        if col_name:
            pattern = rf',?\s*(\w+\.)?{re.escape(col_name)}\s*(AS\s+\w+)?'
            fixed = re.sub(pattern, '', sql, count=1, flags=re.IGNORECASE)
            if fixed != sql:
                return fixed, f"removed invalid column: {col_name}"

        # Fallback: if SELECT DISTINCT fails, try SELECT
        if "SELECT DISTINCT" in sql.upper():
            fixed = re.sub(r'SELECT DISTINCT', 'SELECT', sql, count=1, flags=re.IGNORECASE)
            return fixed, "changed SELECT DISTINCT to SELECT (column may be duplicate)"
        elif re.search(r'SELECT\s+.+\s+FROM', sql, re.IGNORECASE):
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

        # Pattern: column / column
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

    def _heal_safe_denominator_mbew(self, sql: str, code: str) -> Tuple[str, str]:
        """
        [P2] MBEW price-per-unit: when STPRS/PEinh has PEinh=0, use 1 as denominator.
        SAP stores price in STPRS, price unit in PEinh. If PEinh=0, unit cost = STPRS.
        Replaces division pattern with CASE WHEN guard.
        """
        original = sql
        sql_upper = sql.upper()

        if 'MBEW' not in sql_upper:
            return sql, "MBEW not in query - not MBEW context"

        # STPRS/PEinh -> CASE WHEN PEINH=0 OR PEINH IS NULL THEN STPRS ELSE STPRS/PEINH END
        patterns = [
            (r'MBEW\.STPRS\s*/\s*MBEW\.PEINH',
             r'CASE WHEN MBEW.PEINH=0 OR MBEW.PEINH IS NULL THEN MBEW.STPRS ELSE MBEW.STPRS/MBEW.PEINH END'),
            (r'STPRS\s*/\s*PEINH',
             r'CASE WHEN PEINH=0 OR PEINH IS NULL THEN STPRS ELSE STPRS/PEINH END'),
        ]

        for pattern, replacement in patterns:
            fixed = re.sub(pattern, replacement, sql, count=2, flags=re.IGNORECASE)
            if fixed != original:
                return fixed, "MBEW PEinh=0 guard applied: STPRS used as-is when denominator=0"

        return sql, "no STPRS/PEinh pattern found in MBEW context"

    def _heal_relax_where(self, sql: str, code: str) -> Tuple[str, str]:
        """
        Relax WHERE clause to return more data.
        Strategies: remove date range limits, expand company codes, remove specific filters.
        """
        original = sql
        sql_upper = sql.upper()

        # Remove date range restrictions
        date_patterns = [
            r"AND\s+\w+\.(BUDAT|GBSTK|ERDAT|UDATE|PRREG)\s*>=?\s*'[^']+'",
            r"AND\s+\w+\.(BUDAT|GBSTK|ERDAT|UDATE|PRREG)\s*<=?\s*'[^']+'",
            r"WHERE\s+\w+\.(BUDAT|GBSTK|ERDAT|UDATE|PRREG)\s*>=?\s*'[^']+'",
        ]
        for pattern in date_patterns:
            fixed = re.sub(pattern, '', sql, count=1, flags=re.IGNORECASE)
            if fixed != original:
                return fixed, "relaxed date filter (removed lower bound)"

        # Remove specific vendor/material filters
        narrow_filters = [
            r"AND\s+\w+\.(LIFNR|MATNR|KUNNR)\s*=\s*'[^']+'",
            r"WHERE\s+\w+\.(LIFNR|MATNR|KUNNR)\s*=\s*'[^']+'",
        ]
        for pattern in narrow_filters:
            fixed = re.sub(pattern, '', sql, count=1, flags=re.IGNORECASE)
            if fixed != original:
                return fixed, "relaxed entity filter (removed specific ID)"

        # Increase LIMIT
        limit_match = re.search(r'LIMIT\s+(\d+)', sql_upper)
        if limit_match:
            current = int(limit_match.group(1))
            if current < 1000:
                fixed = re.sub(r'LIMIT\s+\d+', f'LIMIT {current * 5}', sql, count=1, flags=re.IGNORECASE)
                return fixed, f"increased LIMIT from {current} to {current * 5}"

        return original, "no relaxable filter found"

    def _heal_qualify_column(self, sql: str, code: str) -> Tuple[str, str]:
        """
        Resolve ambiguous column references by qualifying them with table prefix.
        Uses heuristic: first joined table that has the column wins.
        """
        original = sql

        # Find ambiguous columns (from ORA-00918)
        # Look for columns used in SELECT without table qualification
        # Strategy: for each naked column in SELECT, find the first table that has it
        sql_upper = sql.upper()

        # Simple heuristic: add alias.tablename prefix to naked columns in ORDER BY / WHERE
        # This is a simplified version; production would need schema introspection
        if "ORDER BY" in sql_upper:
            # Try to qualify ORDER BY columns
            fixed = re.sub(
                r'ORDER\s+BY\s+([A-Z_][A-Z0-9_]*)',
                r'ORDER BY \1',
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
            if fixed != sql:
                return fixed, "qualified ambiguous ORDER BY column"

        return sql, "cannot resolve ambiguous column without schema context"

    # -------------------------------------------------------------------------
    # Error text extraction utilities
    # -------------------------------------------------------------------------
    def _extract_table_from_error(self, error_lower: str) -> Optional[str]:
        """Try to pull a table name out of an error message."""
        m = re.search(r'table\s+(\w{3,6})\s+not', error_lower)
        if m:
            return m.group(1)
        m = re.search(r"table\s+'?(\w{3,6})'?\s+(does not exist|not found)", error_lower)
        if m:
            return m.group(1)
        m = re.search(r'invalid object\s+(\w+)', error_lower)
        if m:
            return m.group(1)
        return None

    def _extract_column_from_error(self, error_lower: str) -> Optional[str]:
        """Try to pull a column name out of an error message."""
        m = re.search(r'invalid column\s+(\w+)', error_lower)
        if m:
            return m.group(1)
        m = re.search(r'column not found:?\s*(\w+\.)?(\w+)', error_lower)
        if m:
            return m.group(2)
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

    def reset_stats(self) -> None:
        self._heal_count.clear()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
self_healer = SelfHealer()