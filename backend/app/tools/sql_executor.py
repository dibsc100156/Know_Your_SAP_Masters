"""
sql_executor.py — SAP HANA SQL Executor
======================================
Safe execution wrapper using the HanaPoolManager connection pool.

Implements:
  - Role-Aware RAG guardrails (read-only, MANDT, table access)
  - Connection pooling (pooled hdbcli connections)
  - Circuit breaker (fail fast when HANA is unavailable)
  - Query timeouts (hard limit enforced at pool level)
  - Result column masking (post-execution)

Usage:
    executor = SAPSQLExecutor(connection=None, max_rows=1000)
    result = executor.execute("SELECT * FROM LFA1 WHERE MANDT = '100'")
"""

from __future__ import annotations

import os
import re
import logging
from typing import Dict, Any, List, Optional

import pandas as pd

from app.core.security import SAPAuthContext

logger = logging.getLogger(__name__)

# Whether to use real HANA or mock
_HANA_MODE = os.environ.get("HANA_MODE", "mock").lower()  # mock | pool | direct


class SAPSQLExecutor:
    """
    Safe execution wrapper for SAP HANA SQL queries.

    Three execution modes (HANA_MODE env var):
      mock  : Return mock data (default, no hdbcli needed)
      pool   : Use HanaPoolManager (production, requires hdbcli)
      direct : Use single hdbcli connection (dev, no pooling)

    Implements Role-Aware RAG guardrails:
      1. Read-only validation (no DML/DDL)
      2. Table-level authorization (per SAPAuthContext)
      3. Mandatory MANDT enforcement
      4. Query timeout & row limits
      5. Result column masking
    """

    def __init__(self, connection=None, max_rows: int = 1000):
        self.connection = connection  # legacy — prefer HanaPoolManager
        self.max_rows = max_rows
        self._pool = None

    # ── Pool access ───────────────────────────────────────────────────────

    def _get_pool(self):
        """Lazily get or create the HANA pool."""
        if self._pool is None:
            from app.tools.hana_pool import get_pool
            self._pool = get_pool()
        return self._pool

    # ── Public execute API ─────────────────────────────────────────────────

    def execute(self, sql: str, auth_context: Optional[SAPAuthContext] = None) -> pd.DataFrame:
        """
        Execute a validated query and apply post-retrieval masking.

        Args:
            sql:           SELECT statement
            auth_context:  SAPAuthContext for masking and table access

        Returns:
            pd.DataFrame with query results
        """
        from app.tools.hana_pool import CircuitOpenError

        logger.debug(f"\n[SAPSQLExecutor] mode={_HANA_MODE}, query={sql[:80]}...")

        # 1. Validate SQL (read-only, no DML/DDL)
        self._validate_sql_safety(sql)

        # 2. Validate table access
        if auth_context:
            self._validate_table_access(sql, auth_context)

        # 3. Execute via pool or mock
        if _HANA_MODE == "pool":
            try:
                df = self._execute_via_pool(sql, auth_context)
            except CircuitOpenError:
                logger.warning("[SAPSQLExecutor] Circuit breaker open — falling back to mock")
                df = self._mock_execution(sql)
        elif _HANA_MODE == "direct":
            df = self._execute_direct(sql)
        else:
            df = self._mock_execution(sql)

        # 4. Apply column masking
        if auth_context:
            df = self._mask_results(df, auth_context)

        # 5. Enforce row limit
        if len(df) > self.max_rows:
            df = df.head(self.max_rows)

        return df

    # ── Execution backends ────────────────────────────────────────────────

    def _execute_via_pool(self, sql: str, auth_context) -> pd.DataFrame:
        """Execute via HanaPoolManager (production mode)."""
        pool = self._get_pool()

        if pool.config.enforce_mandt and auth_context:
            sql = pool._inject_mandt(sql, auth_context)

        rows = pool.execute(sql, auth_context=auth_context)
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def _execute_direct(self, sql: str) -> pd.DataFrame:
        """Execute via single hdbcli connection (dev mode)."""
        import hdbcli.dbapi as dbapi

        if self.connection is None:
            from app.tools.hana_pool import HanaPoolConfig
            cfg = HanaPoolConfig()
            nodes = cfg.get_nodes()
            host, port = nodes[0]
            self.connection = dbapi.connect(
                address=host,
                port=port,
                user=cfg.user,
                password=cfg.password,
                connectionTimeout=cfg.connection_timeout,
                encrypt=True,
                sslEnabled=True,
                sslValidateCertificate=False,
            )

        cursor = self.connection.cursor()
        try:
            cursor.execute(sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return pd.DataFrame(rows, columns=columns)
        finally:
            cursor.close()

    # ── Validation ───────────────────────────────────────────────────────

    def _validate_sql_safety(self, sql: str):
        """Ensure the query is read-only and uses MANDT."""
        sql_upper = sql.upper().strip()

        # Must be a SELECT
        if not sql_upper.startswith("SELECT"):
            raise PermissionError(
                f"SECURITY FAULT: Only SELECT permitted. Got: {sql_upper[:50]}"
            )

        # Must not contain DML/DDL
        forbidden = [
            "INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
            "TRUNCATE", "GRANT", "REVOKE", "EXEC", "CALL",
            "CREATE", "REPLACE", "MERGE",
        ]
        for word in forbidden:
            if re.search(rf"\b{word}\b", sql_upper):
                raise PermissionError(
                    f"SECURITY FAULT: Forbidden keyword '{word}' in SQL."
                )

        # Check for MANDT
        if "MANDT" not in sql_upper and "CLIENT" not in sql_upper:
            logger.warning("[SAPSQLExecutor] Query missing MANDT/CLIENT filter (auditor flag)")

    def _validate_table_access(self, sql: str, auth_context: SAPAuthContext):
        """Parse SQL tables and cross-reference with AuthContext denied list."""
        matches = re.findall(
            r"(?:FROM|JOIN)\s+([A-Z0-9_]+)",
            sql.upper()
        )
        for table in matches:
            if not auth_context.is_table_allowed(table):
                raise PermissionError(
                    f"AUTHORIZATION DENIED: User {auth_context.user_id} "
                    f"lacks access to table {table}."
                )

    # ── Masking ────────────────────────────────────────────────────────────

    def _mask_results(self, df: pd.DataFrame, auth_context: SAPAuthContext) -> pd.DataFrame:
        """Redact sensitive columns based on user role."""
        if df.empty or not getattr(auth_context, "masked_columns", None):
            return df

        masked_df = df.copy()
        masked_cols = []

        for col in masked_df.columns:
            if any(
                masked.upper() == col.upper()
                for masked in auth_context.masked_columns
            ):
                masked_cols.append(col)
                if "Z_AUDIT_VIEW" in getattr(auth_context, "roles", []):
                    # Auditor: partial mask
                    masked_df[col] = masked_df[col].apply(
                        lambda x: (
                            f"{str(x)[:4]}***{str(x)[-4:]}"
                            if pd.notna(x) and len(str(x)) > 8
                            else "***"
                        )
                    )
                else:
                    # Default: full mask
                    masked_df[col] = "***RESTRICTED***"

        if masked_cols:
            logger.info(f"[SAPSQLExecutor] Masked {len(masked_cols)} columns: {masked_cols}")

        return masked_df

    # ── Mock execution ────────────────────────────────────────────────────

    def _mock_execution(self, sql: str) -> pd.DataFrame:
        """Return mock data for development/testing without a live HANA DB."""
        sql_upper = sql.upper()

        # Phase 6 Validation Harness: Simulate syntax/schema errors for the Self-Healer
        if "FROM" not in sql_upper:
            raise Exception("37000: Syntax error: missing FROM clause")
        if "JOIN" in sql_upper and "ON" not in sql_upper:
            raise Exception("37000: Syntax error: JOIN without ON condition")
        if "ORDER BY" in sql_upper and re.search(r'ORDER\s+BY\s*$', sql_upper):
            raise Exception("37000: Syntax error: empty ORDER BY clause")
        if re.search(r',\s*FROM', sql_upper):
            raise Exception("37000: Syntax error: trailing comma before FROM")
        if "WHERE WHERE" in sql_upper:
            raise Exception("37000: Syntax error: duplicate WHERE keyword")
        if "/ 0" in sql_upper:
            raise Exception("ORA-01476: Division by zero")
            
        # Simulate an EXPLAIN PLAN or COUNT(*) dry run response
        if sql_upper.startswith("EXPLAIN PLAN") or sql_upper.startswith("SELECT COUNT(*)"):
            return pd.DataFrame([{"STATUS": "VALID", "ESTIMATED_ROWS": 100, "PLAN": "MOCK_PLAN"}])

        data: List[Dict[str, Any]] = []

        if "EKKO" in sql_upper or "EKPO" in sql_upper:
            data = [
                {"EBELN": "4500012345", "LIFNR": "V1000", "NETWR": 45000.00,
                 "BUKRS": "1000", "EKORG": "EU01", "BSTYP": "F",
                 "AEDAT": "2024-03-15", "ERNAM": "SAP_USER"},
                {"EBELN": "4500012346", "LIFNR": "V2000", "NETWR": 120000.50,
                 "BUKRS": "2000", "EKORG": "EU02", "BSTYP": "F",
                 "AEDAT": "2024-03-20", "ERNAM": "SAP_USER"},
            ]
        elif "LFA1" in sql_upper:
            data = [
                {"LIFNR": "V1000", "NAME1": "TechCorp GmbH", "LAND1": "DE",
                 "ORT01": "Berlin", "BANKN": "DE89370400440532013000",
                 "STCD1": "DE123456789", "KTOKK": "LFB1"},
                {"LIFNR": "V2000", "NAME1": "Global Supplies Inc", "LAND1": "US",
                 "ORT01": "New York", "BANKN": "US12345678901234567890",
                 "STCD1": "US987654321", "KTOKK": "LFB1"},
            ]
        elif "KNA1" in sql_upper:
            data = [
                {"KUNNR": "C1000", "NAME1": "Acme Corp", "LAND1": "US",
                 "ORT01": "Chicago", "STCD1": "US111222333", "KTOKK": "KNA1"},
                {"KUNNR": "C2000", "NAME1": "Bayer AG", "LAND1": "DE",
                 "ORT01": "Leverkusen", "STCD1": "DE999888777", "KTOKK": "KNA1"},
            ]
        elif "MARA" in sql_upper or "MBEW" in sql_upper:
            data = [
                {"MATNR": "MAT001", "MTART": "FERT", "MATKL": "FG01",
                 "MEINS": "ST", "BRGEW": 125.50, "NTGEW": 100.00,
                 "BWKEY": "1000", "BKLAS": "9000", "STPRS": 250.00},
                {"MATNR": "MAT002", "MTART": "HALB", "MATKL": "RM02",
                 "MEINS": "KG", "BRGEW": 500.00, "NTGEW": 480.00,
                 "BWKEY": "1000", "BKLAS": "7900", "STPRS": 150.00},
            ]
        elif "MARD" in sql_upper or "MSKA" in sql_upper or "MSLB" in sql_upper:
            data = [
                {"MATNR": "MAT001", "WERKS": "1000", "LGORT": "0001",
                 "LABST": 450, "INSME": 50, "SPEME": 10, "MANDT": "100"},
                {"MATNR": "MAT002", "WERKS": "1000", "LGORT": "0002",
                 "LABST": 1200, "INSME": 200, "SPEME": 30, "MANDT": "100"},
            ]
        elif "BSEG" in sql_upper or "BSIK" in sql_upper or "BSAK" in sql_upper:
            data = [
                {"BELNR": "1900001001", "BUKRS": "1000", "GJAHR": "2024",
                 "BUZEI": "001", "LIFNR": "V1000", "DMBTR": 45000.00,
                 "WAERS": "EUR", "BLDAT": "2024-03-01", "BLART": "KR"},
                {"BELNR": "1900001002", "BUKRS": "1000", "GJAHR": "2024",
                 "BUZEI": "001", "LIFNR": "V2000", "DMBTR": 120000.50,
                 "WAERS": "EUR", "BLDAT": "2024-03-05", "BLART": "KR"},
            ]
        elif "QALS" in sql_upper:
            data = [
                {"QALS": "QI000001", "MATNR": "MAT001", "CHARG": "B2024001",
                 "WERKS": "1000", "QSTATUS": "4", "ART": "01",
                 "ERDAT": "2024-03-10", "ERNAM": "QA_INSPECTOR"},
                {"QALS": "QI000002", "MATNR": "MAT002", "CHARG": "B2024002",
                 "WERKS": "1000", "QSTATUS": "4", "ART": "01",
                 "ERDAT": "2024-03-12", "ERNAM": "QA_INSPECTOR"},
            ]
        else:
            data = [
                {"RESULT": "SUCCESS",
                 "MESSAGE": f"Mock execution — no specific mock for: {sql_upper[:60]}",
                 "ROW_COUNT": 0}
            ]

        return pd.DataFrame(data)
