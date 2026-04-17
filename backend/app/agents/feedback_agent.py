"""
feedback_agent.py — Phase 5 Feedback Loop
=========================================
Handles user corrections and applies them to future behavior.
When a user says "That's wrong — use MARA instead of MARC" or
"No, that should be filtered by company code not plant", the
FeedbackAgent:
  1. Parses the correction intent
  2. Updates the relevant pattern in memory/sap_sessions/
  3. Applies immediate correction to the current session
  4. Optionally triggers a re-run of the query

Feedback types:
  - TABLE_REPLACEMENT  : Use table X instead of Y
  - COLUMN_REPLACEMENT : Select column X instead of Y
  - FILTER_ADDITION    : Add WHERE condition X
  - FILTER_REMOVAL     : Remove WHERE condition X
  - JOIN_CORRECTION    : Fix JOIN between tables X and Y
  - INTENT_CORRECTION  : User intent was different from interpreted intent

Usage:
  from app.agents.feedback_agent import FeedbackAgent
  agent = FeedbackAgent()
  result = agent.process_feedback(
      original_query="show me vendor open invoices",
      original_sql="SELECT ...",
      user_correction="use LFA1-STCD1 as the vendor id, not LIFNR",
      auth_context=ctx,
  )
  if result["applied"]:
      logger.debug(f"Applied: {result['description']}")
      # Re-run query with corrected SQL
      corrected_sql = result["corrected_sql"]
"""

import re
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from app.core.memory_layer import sap_memory


# ---------------------------------------------------------------------------
# Feedback Types
# ---------------------------------------------------------------------------
class FeedbackType(Enum):
    TABLE_REPLACEMENT  = "table_replacement"
    COLUMN_REPLACEMENT = "column_replacement"
    FILTER_ADDITION    = "filter_addition"
    FILTER_REMOVAL     = "filter_removal"
    JOIN_CORRECTION    = "join_correction"
    INTENT_CORRECTION  = "intent_correction"
    UNKNOWN            = "unknown"


@dataclass
class ParsedFeedback:
    feedback_type: FeedbackType
    original_table: Optional[str]
    corrected_table: Optional[str]
    original_column: Optional[str]
    corrected_column: Optional[str]
    original_filter: Optional[str]
    corrected_filter: Optional[str]
    description: str
    confidence: float


# ---------------------------------------------------------------------------
# Feedback Agent
# ---------------------------------------------------------------------------
class FeedbackAgent:
    """
    Parses user corrections, applies them to patterns and SQL,
    logs to feedback memory, and optionally re-executes.
    """

    # Patterns for detecting feedback intent
    TABLE_REPLACE_PATTERNS = [
        (re.compile(r'use (\w{3,6})\s+instead\s+of\s+(\w{3,6})', re.I), 'swap'),
        (re.compile(r'not (\w{3,6}),?\s+use\s+(\w{3,6})', re.I), 'swap'),
        (re.compile(r'should\s+be\s+(\w{3,6})\s+not\s+(\w{3,6})', re.I), 'swap'),
        (re.compile(r'replace\s+(\w{3,6})\s+with\s+(\w{3,6})', re.I), 'swap'),
        (re.compile(r'switch\s+to\s+(\w{3,6})\s+instead\s+of\s+(\w{3,6})', re.I), 'swap'),
    ]

    COLUMN_REPLACE_PATTERNS = [
        (re.compile(r'use\s+(\w+)\s+instead\s+of\s+(\w+)', re.I), 'swap'),
        (re.compile(r'column\s+(\w+)\s+not\s+(\w+)', re.I), 'swap'),
        (re.compile(r'(\w+)\s+instead\s+of\s+(\w+)', re.I), 'swap'),
    ]

    FILTER_PATTERNS = [
        (re.compile(r'add\s+(?:a\s+)?(?:where\s+)?(.+?)\s+filter', re.I), 'add'),
        (re.compile(r'filter\s+by\s+(\w+)\s+not\s+(\w+)', re.I), 'add'),
        (re.compile(r'should\s+(?:also\s+)?(?:be\s+)?(?:filtered|restricted)\s+by\s+(.+)', re.I), 'add'),
        (re.compile(r'remove\s+(?:the\s+)?(.+?)\s+filter', re.I), 'remove'),
        (re.compile(r'don\'?t\s+filter\s+by\s+(\w+)', re.I), 'remove'),
    ]

    def __init__(self):
        self._feedback_history: List[Dict] = []

    def process_feedback(
        self,
        original_query: str,
        original_sql: str,
        user_correction: str,
        auth_context: Optional[Any] = None,
        domain: str = "unknown",
    ) -> Dict[str, Any]:
        """
        Main entry point: parse correction and apply it.

        Returns:
            {
                "applied": bool,
                "feedback_type": str,
                "description": str,
                "corrected_sql": str,
                "pattern_update": dict | None,
                "confidence": float,
            }
        """
        parsed = self._parse_feedback(user_correction, original_sql)

        if parsed.confidence < 0.5:
            return {
                "applied": False,
                "feedback_type": "unknown",
                "description": f"Could not understand correction: '{user_correction}'",
                "corrected_sql": original_sql,
                "pattern_update": None,
                "confidence": parsed.confidence,
            }

        # Build corrected SQL
        corrected_sql = self._apply_correction(original_sql, parsed)

        # Update memory layer: log feedback + update pattern ranking
        pattern_update = self._update_memory(
            domain=domain,
            parsed=parsed,
            original_sql=original_sql,
            corrected_sql=corrected_sql,
        )

        # Log the feedback event
        self._log_feedback(
            query=original_query,
            original_sql=original_sql,
            user_correction=user_correction,
            parsed=parsed,
            corrected_sql=corrected_sql,
            pattern_update=pattern_update,
            auth_context=auth_context,
        )

        return {
            "applied": True,
            "feedback_type": parsed.feedback_type.value,
            "description": parsed.description,
            "corrected_sql": corrected_sql,
            "pattern_update": pattern_update,
            "confidence": parsed.confidence,
        }

    # -------------------------------------------------------------------------
    # Parsing
    # -------------------------------------------------------------------------
    def _parse_feedback(self, user_correction: str, original_sql: str) -> ParsedFeedback:
        """Parse the user's correction string into a structured ParsedFeedback."""
        correction_lower = user_correction.lower()
        sql_upper = original_sql.upper()

        # Try TABLE replacement patterns
        for pattern, _ in self.TABLE_REPLACE_PATTERNS:
            m = pattern.search(user_correction)
            if m:
                # Table names might be in different order (swap)
                t1, t2 = m.group(1).upper(), m.group(2).upper()
                # Figure out which one is in the SQL already
                if t1 in sql_upper:
                    return ParsedFeedback(
                        feedback_type=FeedbackType.TABLE_REPLACEMENT,
                        original_table=t1,
                        corrected_table=t2,
                        original_column=None,
                        corrected_column=None,
                        original_filter=None,
                        corrected_filter=None,
                        description=f"Replace table {t1} with {t2}",
                        confidence=0.9,
                    )
                elif t2 in sql_upper:
                    return ParsedFeedback(
                        feedback_type=FeedbackType.TABLE_REPLACEMENT,
                        original_table=t2,
                        corrected_table=t1,
                        original_column=None,
                        corrected_column=None,
                        original_filter=None,
                        corrected_filter=None,
                        description=f"Replace table {t2} with {t1}",
                        confidence=0.9,
                    )

        # Try COLUMN replacement patterns
        # First, check if the correction mentions a table.column or just column
        for pattern, _ in self.COLUMN_REPLACE_PATTERNS:
            m = pattern.search(user_correction)
            if m:
                c1, c2 = m.group(1), m.group(2)
                c1_up = c1.upper()
                c2_up = c2.upper()
                # Find which is in the SQL
                if c1_up in sql_upper or f".{c1_up}" in sql_upper:
                    return ParsedFeedback(
                        feedback_type=FeedbackType.COLUMN_REPLACEMENT,
                        original_table=None,
                        corrected_table=None,
                        original_column=c1_up,
                        corrected_column=c2_up,
                        original_filter=None,
                        corrected_filter=None,
                        description=f"Use column {c2_up} instead of {c1_up}",
                        confidence=0.8,
                    )
                elif c2_up in sql_upper or f".{c2_up}" in sql_upper:
                    return ParsedFeedback(
                        feedback_type=FeedbackType.COLUMN_REPLACEMENT,
                        original_table=None,
                        corrected_table=None,
                        original_column=c2_up,
                        corrected_column=c1_up,
                        original_filter=None,
                        corrected_filter=None,
                        description=f"Use column {c1_up} instead of {c2_up}",
                        confidence=0.8,
                    )

        # Try FILTER patterns
        for pattern, mode in self.FILTER_PATTERNS:
            m = pattern.search(user_correction)
            if m:
                if mode == 'add':
                    filter_str = m.group(1).strip()
                    return ParsedFeedback(
                        feedback_type=FeedbackType.FILTER_ADDITION,
                        original_table=None,
                        corrected_table=None,
                        original_column=None,
                        corrected_column=None,
                        original_filter=None,
                        corrected_filter=filter_str,
                        description=f"Add filter: {filter_str}",
                        confidence=0.7,
                    )
                elif mode == 'remove':
                    filter_col = m.group(1).strip()
                    return ParsedFeedback(
                        feedback_type=FeedbackType.FILTER_REMOVAL,
                        original_table=None,
                        corrected_table=None,
                        original_column=None,
                        corrected_column=None,
                        original_filter=filter_col,
                        corrected_filter=None,
                        description=f"Remove filter on {filter_col}",
                        confidence=0.7,
                    )

        # INTENT mismatch — user wanted something different
        intent_signals = [
            "meant", "intended", "what i meant", "actually wanted",
            "i wanted", "i was asking", "should have asked",
        ]
        if any(sig in correction_lower for sig in intent_signals):
            return ParsedFeedback(
                feedback_type=FeedbackType.INTENT_CORRECTION,
                original_table=None,
                corrected_table=None,
                original_column=None,
                corrected_column=None,
                original_filter=None,
                corrected_filter=None,
                description=f"Intent correction: {user_correction}",
                confidence=0.6,
            )

        # No pattern matched
        return ParsedFeedback(
            feedback_type=FeedbackType.UNKNOWN,
            original_table=None,
            corrected_table=None,
            original_column=None,
            corrected_column=None,
            original_filter=None,
            corrected_filter=None,
            description=user_correction,
            confidence=0.0,
        )

    # -------------------------------------------------------------------------
    # SQL Correction
    # -------------------------------------------------------------------------
    def _apply_correction(self, sql: str, parsed: ParsedFeedback) -> str:
        """Apply the parsed correction to the SQL string."""
        sql_upper = sql.upper()

        if parsed.feedback_type == FeedbackType.TABLE_REPLACEMENT:
            # Replace all occurrences of original table with corrected table
            orig = parsed.original_table
            corr = parsed.corrected_table
            if orig and corr and orig in sql_upper:
                # Replace table name in FROM/JOIN clauses (careful not to corrupt field names)
                # Replace in FROM clause
                fixed = re.sub(
                    rf'\b(FROM|JOIN|LEFT JOIN|RIGHT JOIN|INNER JOIN)\s+{re.escape(orig)}\b',
                    lambda m: f"{m.group(1)} {corr}",
                    sql,
                    count=1,
                    flags=re.IGNORECASE,
                )
                # Also replace JOIN alias refs (e.g., "LFA1.LIFNR" → "KNA1.LIFNR")
                fixed = re.sub(
                    rf'\b{re.escape(orig)}\.(\w+)',
                    f'{corr}.\\1',
                    fixed,
                    count=10,
                )
                return fixed
            return sql

        elif parsed.feedback_type == FeedbackType.COLUMN_REPLACEMENT:
            orig = parsed.original_column
            corr = parsed.corrected_column
            if orig and corr:
                # Replace in SELECT clause only (not in WHERE/JOIN)
                # Find SELECT ... FROM
                select_match = re.search(r'SELECT\s+(.+?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
                if select_match:
                    select_clause = select_match.group(1)
                    if orig.upper() in select_clause.upper():
                        new_select = re.sub(
                            rf'\b{re.escape(orig)}\b',
                            corr,
                            select_clause,
                            count=1,
                            flags=re.IGNORECASE,
                        )
                        fixed = sql[:select_match.start(1)] + new_select + sql[select_match.end(1):]
                        return fixed
                return sql

        elif parsed.feedback_type == FeedbackType.FILTER_ADDITION:
            filter_cond = parsed.corrected_filter
            if filter_cond:
                if 'WHERE' in sql_upper:
                    fixed = re.sub(
                        r'(\bWHERE\b.+)',
                        rf"\1\n  AND {filter_cond}",
                        sql,
                        count=1,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                else:
                    # Find the FROM clause and insert WHERE after it
                    from_match = re.search(r'(\bFROM\b.+)', sql, re.IGNORECASE | re.DOTALL)
                    if from_match:
                        pos = from_match.end()
                        fixed = sql[:pos] + f"\n WHERE {filter_cond}" + sql[pos:]
                    else:
                        fixed = sql + f"\n WHERE {filter_cond}"
                return fixed
            return sql

        elif parsed.feedback_type == FeedbackType.FILTER_REMOVAL:
            col = parsed.original_filter
            if col:
                # Remove WHERE condition on this column
                # Pattern: AND col = '...' OR AND col >= '...'
                fixed = re.sub(
                    rf"\bAND\s+\w+\.?{re.escape(col)}\w*\s*(?:=|>=|<=|<|>)\s*'[^']*'",
                    '',
                    sql,
                    count=1,
                    flags=re.IGNORECASE,
                )
                # Also remove standalone WHERE col = '...'
                fixed = re.sub(
                    rf"\bWHERE\s+\w+\.?{re.escape(col)}\w*\s*(?:=|>=|<=|<|>)\s*'[^']*'",
                    'WHERE MANDT',
                    fixed,
                    count=1,
                    flags=re.IGNORECASE,
                )
                return fixed
            return sql

        # INTENT_CORRECTION: return original (supervisor will re-route)
        return sql

    # -------------------------------------------------------------------------
    # Memory Update
    # -------------------------------------------------------------------------
    def _update_memory(
        self,
        domain: str,
        parsed: ParsedFeedback,
        original_sql: str,
        corrected_sql: str,
    ) -> Dict[str, Any]:
        """Update pattern rankings and log the correction to feedback history."""
        update = {"type": parsed.feedback_type.value, "description": parsed.description}

        if parsed.feedback_type == FeedbackType.TABLE_REPLACEMENT:
            # Penalize the original table choice in this domain
            # Log a negative pattern event
            update["action"] = "table_swap"
            update["from"] = parsed.original_table
            update["to"] = parsed.corrected_table
            # Also log gotcha
            sap_memory.log_gotcha(
                pattern=f"User feedback: use {parsed.corrected_table} not {parsed.original_table} in {domain}",
                domain=domain,
                severity="warn",
                description=parsed.description,
            )

        elif parsed.feedback_type == FeedbackType.COLUMN_REPLACEMENT:
            update["action"] = "column_swap"
            update["from"] = parsed.original_column
            update["to"] = parsed.corrected_column
            sap_memory.log_gotcha(
                pattern=f"User feedback: use column {parsed.corrected_column} not {parsed.original_column}",
                domain=domain,
                severity="info",
                description=parsed.description,
            )

        elif parsed.feedback_type == FeedbackType.FILTER_ADDITION:
            update["action"] = "filter_added"
            update["filter"] = parsed.corrected_filter
            sap_memory.log_gotcha(
                pattern=f"User feedback: add filter '{parsed.corrected_filter}' in {domain}",
                domain=domain,
                severity="warn",
                description=parsed.description,
            )

        elif parsed.feedback_type == FeedbackType.INTENT_CORRECTION:
            update["action"] = "intent_mismatch"

        return update

    def _log_feedback(
        self,
        query: str,
        original_sql: str,
        user_correction: str,
        parsed: ParsedFeedback,
        corrected_sql: str,
        pattern_update: Dict,
        auth_context: Optional[Any],
    ) -> None:
        """Append feedback event to feedback history."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "query": query,
            "original_sql": original_sql,
            "corrected_sql": corrected_sql,
            "user_correction": user_correction,
            "feedback_type": parsed.feedback_type.value,
            "description": parsed.description,
            "confidence": parsed.confidence,
            "domain": "unknown",
            "role": auth_context.role_id if auth_context else "unknown",
            "applied": True,
        }
        self._feedback_history.append(record)
        # Also persist to a feedback log file
        self._append_feedback_log(record)

    def _append_feedback_log(self, record: Dict) -> None:
        FEEDBACK_LOG = sap_memory._memory_dir / "feedback_log.jsonl" if hasattr(sap_memory, '_memory_dir') else None
        if FEEDBACK_LOG:
            try:
                import pathlib
                log_path = pathlib.Path(__file__).parent.parent.parent / "memory" / "sap_sessions" / "feedback_log.jsonl"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            except Exception:
                pass  # Non-critical — feedback already processed in-memory

    @property
    def recent_feedback(self) -> List[Dict]:
        return self._feedback_history[-20:]


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
feedback_agent = FeedbackAgent()
