"""
temporal_engine.py — Phase 7: Temporal Analysis Engine
=====================================================
Comprehensive temporal analysis for Longitudinal Corporate Memory.
Builds on TemporalGraphRAG (graph_store.py) to enable deep time-series
analysis across SAP FI/CO, MM-PUR, SD, and QM.

Sub-systems:
  1. FiscalYearEngine      — Multi-FY slicing, period grouping, FY comparisons
  2. TimeSeriesAggregator  — Date truncation, rolling windows, trend detection
  3. SupplierPerformanceIndex — Composite delivery/quality/price scoring
  4. CustomerLifetimeValue   — Revenue, discount, payment, churn analysis
  5. EconomicCycleTagger   — Historical macro events as queryable date ranges

Usage:
  from app.core.temporal_engine import TemporalEngine
  te = TemporalEngine()

  # Fiscal year analysis
  result = te.fiscal_year_analysis(
      query="vendor spend by month for FY2020 through FY2024",
      tables=["EKKO", "EKPO", "LFA1"],
  )

  # Supplier performance
  spi = te.supplier_performance_index(
      vendor_id="LIFNR-001",
      start_fy="2020",
      end_fy="2024",
  )

  # CLV
  clv = te.customer_lifetime_value(customer_id="KUNNR-10000142")
"""

import re
from datetime import date, datetime, timedelta
from typing import Dict, Any, List, Optional, Literal, Tuple
from dataclasses import dataclass
from enum import Enum


# ============================================================================
# PART 1: FISCAL YEAR ENGINE
# ============================================================================

class FiscalYearVariant(Enum):
    """SAP Fiscal Year variants."""
    CALENDAR = "calendar"           # Jan-Dec (most European companies)
    APRIL = "april"               # April-March (UK, India, Australia)
    JULY = "july"                 # July-June (Australia, some India)
    OCTOBER = "october"            # Oct-Sep (US retail often)
    SPECIAL = "special"            # 4-4-5 calendar, 13 periods


@dataclass
class FiscalPeriod:
    """Represents a fiscal year + period combination."""
    fy: int           # e.g., 2024
    variant: str      # calendar, april, july, october, special
    period: int       # 1-12 (or 1-13 for 4-4-5)
    start_date: date
    end_date: date
    is_current: bool = False

    def label(self) -> str:
        return f"FY{self.fy}P{self.period:02d}"

    def year_label(self) -> str:
        return f"FY{self.fy}"


@dataclass
class FiscalYearSlice:
    """A multi-period fiscal year slice."""
    fy_start: int
    fy_end: int
    periods: List[FiscalPeriod]
    label: str  # e.g., "FY2020" or "FY2020-FY2024"


class FiscalYearEngine:
    """
    Handles SAP fiscal year variant logic and multi-FY slicing.
    Supports: Calendar (Jan-Dec), April-based (India FY April-March),
    July-based, October-based, and 4-4-5 Special.
    """

    def __init__(self, default_variant: str = "calendar"):
        self.default_variant = default_variant
        # Map company code to fiscal variant (would come from T001 in real SAP)
        self._company_fy_map: Dict[str, str] = {}

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def parse_fy_expression(self, fy_expr: str) -> Tuple[int, int]:
        """
        Parse a fiscal year expression like "FY2024", "FY2020-FY2024",
        "2020-2024", "last 3 years", "current FY".
        Returns (fy_start, fy_end).
        """
        now = datetime.now().date()
        current_fy = self._get_fy_for_date(now)

        expr = fy_expr.strip().upper()

        # "current FY"
        if "CURRENT" in expr or expr in ("CY", "THIS FY", "THIS YEAR"):
            return current_fy, current_fy

        # "last FY" / "prior FY"
        if "LAST" in expr and "YEAR" in expr or expr in ("PY", "PRIOR FY"):
            prior_fy = current_fy - 1
            return prior_fy, prior_fy

        # "last N years"
        m = re.search(r'LAST\s+(\d+)\s+YEARS?', expr)
        if m:
            n = int(m.group(1))
            return current_fy - n + 1, current_fy

        # "FY2020-FY2024"
        m = re.search(r'FY(\d{4})\s*[-–]\s*FY(\d{4})', expr)
        if m:
            return int(m.group(1)), int(m.group(2))

        # "FY2020"
        m = re.search(r'FY(\d{4})', expr)
        if m:
            fy = int(m.group(1))
            return fy, fy

        # "2020-2024" (bare year range)
        m = re.search(r'^(\d{4})\s*[-–]\s*(\d{4})$', expr.strip())
        if m:
            return int(m.group(1)), int(m.group(2))

        # Fallback: current FY
        return current_fy, current_fy

    def get_fiscal_periods(
        self,
        fy_start: int,
        fy_end: int,
        variant: str = "calendar",
        periods_per_year: int = 12,
    ) -> FiscalYearSlice:
        """
        Generate all fiscal periods from fy_start to fy_end.
        For calendar variant: FY2024 = Jan 2024 - Dec 2024.
        For April variant: FY2024 = April 2024 - March 2025.
        """
        slice_periods = []
        for year in range(fy_start, fy_end + 1):
            fy_periods = self._build_fy_periods(year, variant, periods_per_year)
            slice_periods.extend(fy_periods)

        label = f"FY{fy_start}" if fy_start == fy_end else f"FY{fy_start}-FY{fy_end}"
        return FiscalYearSlice(
            fy_start=fy_start,
            fy_end=fy_end,
            periods=slice_periods,
            label=label,
        )

    def generate_fy_sql(
        self,
        fy_start: int,
        fy_end: int,
        table: str,
        date_column: str,
        variant: str = "calendar",
    ) -> Dict[str, Any]:
        """
        Generate SQL WHERE clause for fiscal year range.
        Returns {where_clause, group_by, select_labels, fiscal_periods}.

        Example for EKKO.AEDAT, FY2020-FY2022:
          WHERE EKKO.AEDAT >= '20200101' AND EKKO.AEDAT <= '20221231'
          GROUP BY YEAR(EKKO.AEDAT), MONTH(EKKO.AEDAT)
        """
        dr_start, dr_end = self._fy_date_range(fy_start, fy_end, variant)
        where = f"{table}.{date_column} >= '{dr_start.strftime('%Y%m%d')}' " \
                f"AND {table}.{date_column} <= '{dr_end.strftime('%Y%m%d')}'"

        # SAP HANA date extraction functions
        year_fn = f"YEAR({table}.{date_column})"
        month_fn = f"MONTH({table}.{date_column})"
        quarter_fn = f"QUARTER({table}.{date_column})"

        return {
            "where_clause": where,
            "select_year": year_fn,
            "select_month": month_fn,
            "select_quarter": quarter_fn,
            "group_by_year": year_fn,
            "group_by_quarter": f"{year_fn}, {quarter_fn}",
            "date_range_start": dr_start,
            "date_range_end": dr_end,
            "fiscal_years": list(range(fy_start, fy_end + 1)),
            "variant": variant,
        }

    def generate_period_comparison_sql(
        self,
        fy1: int,
        fy2: int,
        table: str,
        date_column: str,
        value_column: str,
        variant: str = "calendar",
    ) -> str:
        """
        Generate SQL comparing two fiscal years side-by-side.
        Returns a pivot-style query:
          SELECT YEAR(date_col) AS FY,
                 SUM(value_col) AS total_value
          FROM table
          WHERE (date BETWEEN FY1_start AND FY1_end OR
                 date BETWEEN FY2_start AND FY2_end)
          GROUP BY YEAR(date_col)
        """
        r1s, r1e = self._fy_date_range(fy1, fy1, variant)
        r2s, r2e = self._fy_date_range(fy2, fy2, variant)

        return f"""
SELECT
    YEAR({table}.{date_column}) AS FISCAL_YEAR,
    SUM({table}.{value_column}) AS TOTAL_VALUE,
    COUNT(*) AS RECORD_COUNT
FROM {table}
WHERE (
    ({table}.{date_column} >= '{r1s.strftime('%Y%m%d')}'
     AND {table}.{date_column} <= '{r1e.strftime('%Y%m%d')}')
    OR
    ({table}.{date_column} >= '{r2s.strftime('%Y%m%d')}'
     AND {table}.{date_column} <= '{r2e.strftime('%Y%m%d')}')
)
GROUP BY YEAR({table}.{date_column})
ORDER BY FISCAL_YEAR
"""

    def detect_fiscal_variant_from_company(self, company_code: str) -> str:
        """Look up fiscal variant for a company code. Defaults to calendar."""
        return self._company_fy_map.get(company_code, self.default_variant)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _get_fy_for_date(self, d: date, variant: str = "calendar") -> int:
        """Return the fiscal year for a given date."""
        if variant == "calendar":
            return d.year
        elif variant == "april":
            return d.year if d.month >= 4 else d.year - 1
        elif variant == "july":
            return d.year if d.month >= 7 else d.year - 1
        elif variant == "october":
            return d.year if d.month >= 10 else d.year - 1
        return d.year

    def _fy_date_range(self, fy: int, variant: str, periods: int = 12) -> Tuple[date, date]:
        """Return (start_date, end_date) of a fiscal year."""
        if variant == "calendar":
            return date(fy, 1, 1), date(fy, 12, 31)
        elif variant == "april":
            return date(fy, 4, 1), date(fy + 1, 3, 31)
        elif variant == "july":
            return date(fy, 7, 1), date(fy + 1, 6, 30)
        elif variant == "october":
            return date(fy, 10, 1), date(fy + 1, 9, 30)
        # special 4-4-5: 52 weeks + 1 extra day, approximated here
        return date(fy, 1, 1), date(fy, 12, 31)

    def _build_fy_periods(
        self, fy: int, variant: str, periods: int
    ) -> List[FiscalPeriod]:
        """Build 12 or 13 fiscal periods for a given fiscal year."""
        now = datetime.now().date()
        result = []
        for p in range(1, periods + 1):
            if variant == "calendar":
                start = date(fy, p, 1)
                end = date(fy, p, 28) if p in (4, 6, 9, 11) else (
                    date(fy, 2, 29) if (fy % 4 == 0 and (fy % 100 != 0 or fy % 400 == 0)) else date(fy, 2, 28)
                ) if p == 2 else date(fy, p, 31)
            elif variant == "april":
                month = ((p + 2) % 12) + 1
                adj_year = fy if month >= 4 else fy + 1
                start = date(adj_year, month, 1)
                end = (start + timedelta(days=27)).replace(day=min(start.day + 27, {
                    1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31
                }.get(month, 28)))
            elif variant == "july":
                month = ((p + 5) % 12) + 1
                adj_year = fy if month >= 7 else fy + 1
                start = date(adj_year, month, 1)
                end = date(adj_year, month, {
                    1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30,
                    7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31
                }.get(month, 30))
            else:
                start = date(fy, p, 1)
                end = date(fy, p, 28)

            result.append(FiscalPeriod(
                fy=fy,
                variant=variant,
                period=p,
                start_date=start,
                end_date=end,
                is_current=(start <= now <= end),
            ))
        return result


# ============================================================================
# PART 2: TIME-SERIES AGGREGATOR
# ============================================================================

class Granularity(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass
class TimeSeriesQuery:
    """Structured time-series aggregation query."""
    table: str
    value_column: str
    date_column: str
    granularity: Granularity
    start_date: date
    end_date: date
    group_by_columns: List[str]   # e.g., ["LIFNR", "BUKRS"]
    aggregation: str             # SUM, AVG, COUNT, MIN, MAX
    where_extra: str = ""        # Additional WHERE conditions
    order_by: str = "period_start"
    limit: int = 500


class TimeSeriesAggregator:
    """
    Builds SAP HANA time-series aggregation queries with proper date
    truncation and rolling window functions.

    Handles: DAILY / WEEKLY / MONTHLY / QUARTERLY / YEARLY granularity.
    Supports: rolling averages, cumulative sums, period-over-period comparisons.
    """

    # SAP HANA date functions
    DATE_FNS = {
        "daily": {
            "trunc": "TO_DATE({table}.{col}, 'DD/MM/YYYY')",
            "label": "DAY({table}.{col})",
            "group_by": "DAY({table}.{col})",
        },
        "weekly": {
            "trunc": "ADD_DAYS({table}.{col}, -DAYOFWEEK({table}.{col}) + 1)",
            "label": "ADD_DAYS({table}.{col}, -DAYOFWEEK({table}.{col}) + 1) AS WEEK_START",
            "group_by": "ADD_DAYS({table}.{col}, -DAYOFWEEK({table}.{col}) + 1)",
        },
        "monthly": {
            "trunc": "STARTOFMONTH({table}.{col})",
            "label": "STARTOFMONTH({table}.{col}) AS MONTH_START",
            "group_by": "YEAR({table}.{col}), MONTH({table}.{col})",
        },
        "quarterly": {
            "trunc": "START OF QUARTER({table}.{col})",
            "label": "START OF QUARTER({table}.{col}) AS QUARTER_START",
            "group_by": "YEAR({table}.{col}), QUARTER({table}.{col})",
        },
        "yearly": {
            "trunc": "STARTOFYEAR({table}.{col})",
            "label": "STARTOFYEAR({table}.{col}) AS FYEAR_START",
            "group_by": "YEAR({table}.{col})",
        },
    }

    def build_aggregation_query(self, tsq: TimeSeriesQuery) -> Tuple[str, str]:
        """
        Build a time-series aggregation SQL query.

        Returns: (main_query, trend_comparison_query)
        The trend query compares each period vs the prior period.
        """
        g = self.DATE_FNS[tsq.granularity.value]
        dcol = tsq.date_column
        t = tsq.table
        
        # Substitute {table} and {col} in date function templates
        date_fn = {k: v.replace('{table}', t).replace('{col}', dcol) if isinstance(v, str) else v
                   for k, v in g.items()}

        # WHERE clause
        where = f"{t}.{dcol} >= '{tsq.start_date.strftime('%Y%m%d')}' " \
                f"AND {t}.{dcol} <= '{tsq.end_date.strftime('%Y%m%d')}'"
        if tsq.where_extra:
            where += f"\n  AND {tsq.where_extra}"

        # GROUP BY
        extra_group = ", ".join([f"{t}.{c}" for c in tsq.group_by_columns]) if tsq.group_by_columns else ""
        if extra_group:
            full_group = f"{date_fn['group_by']}, {extra_group}"
            select_extra = ", ".join([f"{t}.{c}" for c in tsq.group_by_columns]) + ", "
        else:
            full_group = date_fn['group_by']
            select_extra = ""

        # Main aggregation query
        agg_col = f"{tsq.aggregation}({t}.{tsq.value_column})"
        label_expr = date_fn['label']

        main_query = f"""
SELECT
    {label_expr},
    {select_extra}{agg_col} AS TOTAL_VALUE,
    COUNT({t}.{tsq.value_column}) AS RECORD_COUNT,
    AVG({t}.{tsq.value_column}) AS AVG_VALUE,
    MIN({t}.{tsq.value_column}) AS MIN_VALUE,
    MAX({t}.{tsq.value_column}) AS MAX_VALUE
FROM {t}
WHERE {where}
GROUP BY {full_group}
ORDER BY {date_fn['group_by']}{', ' + extra_group if extra_group else ''}
LIMIT {tsq.limit}
""".strip()

        # Rolling 3-period average (window function)
        rolling_query = f"""
SELECT
    {label_expr},
    {select_extra}{agg_col} AS TOTAL_VALUE,
    AVG({agg_col}) OVER (
        PARTITION BY {extra_group if extra_group else '1'}
        ORDER BY {date_fn['group_by']}
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS ROLLING_3P_AVG,
    {agg_col} - LAG({agg_col}, 1) OVER (
        PARTITION BY {extra_group if extra_group else '1'}
        ORDER BY {date_fn['group_by']}
    ) AS PERIOD_DELTA,
    ROUND(
        100.0 * ({agg_col} - LAG({agg_col}, 1) OVER (
            PARTITION BY {extra_group if extra_group else '1'}
            ORDER BY {date_fn['group_by']}
        )) / NULLIF(LAG({agg_col}, 1) OVER (
            PARTITION BY {extra_group if extra_group else '1'}
            ORDER BY {date_fn['group_by']}
        ), 0),
        2
    ) AS PERIOD_DELTA_PCT
FROM {t}
WHERE {where}
GROUP BY {full_group}, {date_fn['group_by']}
ORDER BY {date_fn['group_by']}
""".strip()

        return main_query, rolling_query

    def build_period_comparison(
        self,
        tsq: TimeSeriesQuery,
        comparison_start: date,
        comparison_end: date,
    ) -> str:
        """
        Compare two time periods (e.g., this quarter vs last quarter).
        """
        g = self.DATE_FNS[tsq.granularity.value]
        t = tsq.table
        dcol = tsq.date_column
        date_fn = {k: v.replace('{table}', t).replace('{col}', dcol) if isinstance(v, str) else v
                   for k, v in g.items()}

        cur_where = f"{t}.{dcol} >= '{tsq.start_date.strftime('%Y%m%d')}' AND {t}.{dcol} <= '{tsq.end_date.strftime('%Y%m%d')}'"
        comp_where = f"{t}.{dcol} >= '{comparison_start.strftime('%Y%m%d')}' AND {t}.{dcol} <= '{comparison_end.strftime('%Y%m%d')}'"

        extra_select = ", ".join([f"{t}.{c}" for c in tsq.group_by_columns]) + ", " if tsq.group_by_columns else ""
        extra_group = ", ".join([f"{t}.{c}" for c in tsq.group_by_columns]) if tsq.group_by_columns else ""

        return f"""
SELECT
    {g['label']},
    {extra_select}
    SUM(CASE WHEN period = 'CURRENT' THEN {t}.{tsq.value_column} ELSE 0 END) AS CURRENT_VALUE,
    SUM(CASE WHEN period = 'PRIOR' THEN {t}.{tsq.value_column} ELSE 0 END) AS PRIOR_VALUE,
    SUM(CASE WHEN period = 'CURRENT' THEN {t}.{tsq.value_column} ELSE 0 END) -
    SUM(CASE WHEN period = 'PRIOR' THEN {t}.{tsq.value_column} ELSE 0 END) AS DELTA,
    ROUND(100.0 * (
        SUM(CASE WHEN period = 'CURRENT' THEN {t}.{tsq.value_column} ELSE 0 END) -
        SUM(CASE WHEN period = 'PRIOR' THEN {t}.{tsq.value_column} ELSE 0 END)
    ) / NULLIF(SUM(CASE WHEN period = 'PRIOR' THEN {t}.{tsq.value_column} ELSE 0 END), 0), 2) AS DELTA_PCT
FROM (
    SELECT {t}.*, 'CURRENT' AS period, {g['label']} FROM {t} WHERE {cur_where}
    UNION ALL
    SELECT {t}.*, 'PRIOR' AS period, {g['label']} FROM {t} WHERE {comp_where}
) combined
GROUP BY {g['group_by']}{', ' + extra_group if extra_group else ''}
ORDER BY {g['group_by']}
""".strip()


# ============================================================================
# PART 3: SUPPLIER PERFORMANCE INDEX (SPI)
# ============================================================================

@dataclass
class SupplierPerformanceScore:
    """Composite supplier score across 3 dimensions."""
    vendor_id: str
    fiscal_year: str
    # Delivery reliability (0-100)
    on_time_delivery_rate: float      # % of POs delivered on or before EINDT
    avg_delivery_delay_days: float     # Average days late
    delivery_confirmed_count: int      # Number of deliveries analyzed
    # Quality (0-100)
    quality_accept_rate: float          # % of inspections with UD = 'Accept'
    defect_rate_per_po: float         # Defects per PO line
    quality_hold_days: float           # Avg days in quality hold
    # Price competitiveness (0-100)
    price_competitiveness_index: float  # Inverse of price vs. market average
    # Composite
    composite_score: float             # Weighted average (40% delivery, 35% quality, 25% price)
    grade: str                          # A / B / C / D / F


class SupplierPerformanceIndex:
    """
    Calculates a composite Supplier Performance Index (SPI) for a vendor
    over a specified fiscal year period.

    Three dimensions:
      Delivery Reliability — EKET vs. EINDT (delivery date)
      Quality — QALS usage decision (Accept/Reject/Hold)
      Price Competitiveness — EINA/EINE net price vs. benchmark

    Outputs: 0-100 score per dimension + composite + letter grade.
    """

    GRADE_THRESHOLDS = {
        "A": 85.0,
        "B": 70.0,
        "C": 55.0,
        "D": 40.0,
        "F": 0.0,
    }

    def generate_delivery_sql(self, vendor_id: str, fy_start: int, fy_end: int) -> str:
        """
        SQL: Delivery reliability — compare EKET (schedule) vs. EINDT (delivery date).
        On-time = MSEG-BUDAT <= EKET-EINDT.
        """
        return f"""
SELECT
    EKKO.LIFNR AS VENDOR_ID,
    COUNT(DISTINCT EKKO.EBELN) AS TOTAL_POS,
    COUNT(DISTINCT CASE
        WHEN MSEG.BUDAT <= EKET.EINDT THEN EKKO.EBELN
        ELSE NULL
    END) AS ON_TIME_COUNT,
    ROUND(100.0 * COUNT(DISTINCT CASE
        WHEN MSEG.BUDAT <= EKET.EINDT THEN EKKO.EBELN
        ELSE NULL
    END) / NULLIF(COUNT(DISTINCT EKKO.EBELN), 0), 2) AS ON_TIME_RATE,
    ROUND(AVG(CASE
        WHEN MSEG.BUDAT > EKET.EINDT
        THEN DAYS_BETWEEN(EKET.EINDT, MSEG.BUDAT)
        ELSE 0
    END), 1) AS AVG_DELAY_DAYS
FROM EKKO
JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
JOIN EKET ON EKPO.EBELN = EKET.EBELN AND EKPO.EBELP = EKET.EBELP
LEFT JOIN MSEG ON EKPO.EBELN = MSEG.EBELN AND EKPO.EBELP = MSEG.EBELP
WHERE EKKO.LIFNR = '{vendor_id}'
  AND EKKO.AEDAT >= '{fy_start}0101'
  AND EKKO.AEDAT <= '{fy_end}1231'
  AND EKPO.LOEKZ = ''      -- exclude deleted lines
GROUP BY EKKO.LIFNR
""".strip()

    def generate_quality_sql(self, vendor_id: str, fy_start: int, fy_end: int) -> str:
        """
        SQL: Quality — QALS usage decision codes.
        UD codes: 'AC' = Accept, 'RE' = Reject, 'HU' = Held/Undecided.
        """
        return f"""
SELECT
    QALS.LIFNUM AS VENDOR_ID,
    COUNT(*) AS TOTAL_INSPECTIONS,
    COUNT(CASE WHEN QALS.BEWERTG = 'AC' THEN 1 END) AS ACCEPT_COUNT,
    COUNT(CASE WHEN QALS.BEWERTG = 'RE' THEN 1 END) AS REJECT_COUNT,
    COUNT(CASE WHEN QALS.BEWERTG = 'HU' THEN 1 END) AS HOLD_COUNT,
    ROUND(100.0 * COUNT(CASE WHEN QALS.BEWERTG = 'AC' THEN 1 END)
        / NULLIF(COUNT(*), 0), 2) AS ACCEPT_RATE,
    ROUND(COUNT(CASE WHEN QALS.BEWERTG = 'RE' THEN 1 END)
        * 100.0 / NULLIF(COUNT(*), 0), 2) AS DEFECT_RATE
FROM QALS
WHERE QALS.LIFNUM = '{vendor_id}'
  AND QALS.QMDAT >= '{fy_start}0101'
  AND QALS.QMDAT <= '{fy_end}1231'
  AND QALS.ART = '01'  -- Receipt inspection
GROUP BY QALS.LIFNUM
""".strip()

    def generate_price_sql(self, vendor_id: str, fy_start: int, fy_end: int) -> str:
        """
        SQL: Price competitiveness — EINA net price per material-year vs. vendor average.
        A lower-than-average price = higher score.
        """
        return f"""
WITH vendor_prices AS (
    SELECT
        EINA.LIFNR AS VENDOR_ID,
        EINA.MATNR AS MATERIAL,
        YEAR(EINA.DATAB) AS PRICING_YEAR,
        AVG(EINA.NETPR / NULLIF(EINA.PEINH, 0)) AS AVG_NET_PRICE
    FROM EINE
    JOIN EINA ON EINE.INFNR = EINA.INFNR
    WHERE EINA.LIFNR = '{vendor_id}'
      AND EINA.DATAB >= '{fy_start}0101'
      AND EINA.DATBI <= '{fy_end}1231'
    GROUP BY EINA.LIFNR, EINA.MATNR, YEAR(EINA.DATAB)
),
all_vendor_avg AS (
    SELECT
        MATNR AS MATERIAL,
        PRICING_YEAR,
        AVG(AVG_NET_PRICE) AS MARKET_AVG_PRICE
    FROM vendor_prices
    GROUP BY MATNR, PRICING_YEAR
)
SELECT
    vp.VENDOR_ID,
    ROUND(100.0 - LEAST(100.0, (
        AVG(vp.AVG_NET_PRICE - av.MARKET_AVG_PRICE) / NULLIF(av.MARKET_AVG_PRICE, 0)
    ) * 100), 2) AS PRICE_COMPETITIVENESS_INDEX,
    -- Score: 100 = at market avg, <100 = more expensive, >100 = cheaper
    AVG(vp.AVG_NET_PRICE) AS AVG_PRICE,
    AVG(av.MARKET_AVG_PRICE) AS MARKET_AVG
FROM vendor_prices vp
JOIN all_vendor_avg av ON vp.MATERIAL = av.MATERIAL AND vp.PRICING_YEAR = av.PRICING_YEAR
GROUP BY vp.VENDOR_ID
""".strip()

    def composite_score(self, delivery_rate: float, quality_rate: float,
                       price_index: float) -> Tuple[float, str]:
        """Compute weighted composite score and letter grade."""
        # Weights: delivery 40%, quality 35%, price 25%
        composite = (
            delivery_rate * 0.40 +
            quality_rate * 0.35 +
            price_index * 0.25
        )
        grade = "F"
        for g, threshold in sorted(self.GRADE_THRESHOLDS.items(), key=lambda x: x[1], reverse=True):
            if composite >= threshold:
                grade = g
                break
        return round(composite, 2), grade


# ============================================================================
# PART 4: CUSTOMER LIFETIME VALUE ENGINE
# ============================================================================

@dataclass
class CLVProfile:
    """Customer Lifetime Value analysis."""
    customer_id: str
    relationship_years: float
    total_revenue: float
    total_discount: float
    net_revenue: float
    avg_order_value: float
    avg_discount_pct: float
    payment_score: float          # 0-100: based on days-to-pay vs. terms
    return_rate: float            # % of orders with returns
    order_count: int
    active_years: int             # Years with at least one order
    clv_tier: str                # PLATINUM / GOLD / SILVER / BRONZE / STANDARD


class CustomerLifetimeValueEngine:
    """
    Calculates a Customer Lifetime Value profile from 20 years of SAP data.

    Revenue:    VBAP-NETWR per order (VBAK-AUDAT)
    Discounts: KONV-KBETR for condition types 'KB01' (manual discount), 'K007' (% discount)
    Payments:  BSID-ZBD3T (days-to-pay) vs. KNVV-ZAHLS (payment terms)
    Returns:    LIKP-WBSTK = 'R' (returns)
    Churn:      Gaps > 18 months between orders = churn signal
    """

    CLV_TIERS = {
        "PLATINUM": 1000000,
        "GOLD": 500000,
        "SILVER": 100000,
        "BRONZE": 25000,
    }

    def generate_revenue_sql(self, customer_id: str, years_back: int = 20) -> str:
        """Annual revenue from VBAP-NETWR, grouped by fiscal year."""
        cutoff = datetime.now().year - years_back
        return f"""
SELECT
    VBAK.KUNNR AS CUSTOMER_ID,
    YEAR(VBAK.AUDAT) AS ORDER_YEAR,
    SUM(VBAP.NETWR) AS GROSS_REVENUE,
    COUNT(DISTINCT VBAK.VBELN) AS ORDER_COUNT,
    AVG(VBAP.NETWR) AS AVG_ORDER_VALUE,
    MIN(VBAK.AUDAT) AS FIRST_ORDER_DATE,
    MAX(VBAK.AUDAT) AS LAST_ORDER_DATE
FROM VBAK
JOIN VBAP ON VBAK.VBELN = VBAP.VBELN
WHERE VBAK.KUNNR = '{customer_id}'
  AND VBAK.AUDAT >= '{cutoff}0101'
  AND VBAK.FKSTV = ''  -- exclude billing blocks
GROUP BY VBAK.KUNNR, YEAR(VBAK.AUDAT)
ORDER BY ORDER_YEAR
""".strip()

    def generate_discount_sql(self, customer_id: str, years_back: int = 20) -> str:
        """Discount analysis from KONV — manual discounts and percentage discounts."""
        cutoff = datetime.now().year - years_back
        return f"""
SELECT
    KNA1.KUNNR AS CUSTOMER_ID,
    YEAR(VBAK.AUDAT) AS ORDER_YEAR,
    SUM(CASE WHEN KONV.KSCHL IN ('KB01', 'K007', 'K020') THEN KONV.KBETR ELSE 0 END) AS TOTAL_DISCOUNT_AMOUNT,
    SUM(CASE WHEN KONV.KSCHL IN ('KB01', 'K007', 'K020')
        THEN KONV.KBETR ELSE 0 END) * 100.0 /
        NULLIF(SUM(VBAP.NETWR), 0) AS DISCOUNT_PCT,
    SUM(CASE WHEN KONV.KSCHL = 'KB01' THEN KONV.KBETR ELSE 0 END) AS MANUAL_DISCOUNT_AMT,
    SUM(CASE WHEN KONV.KSCHL = 'K007' THEN KONV.KBETR ELSE 0 END) AS VOLUME_DISCOUNT_PCT,
    COUNT(DISTINCT VBAK.VBELN) AS DISCOUNTED_ORDER_COUNT
FROM KNA1
JOIN VBAK ON KNA1.KUNNR = VBAK.KUNNR
JOIN VBAP ON VBAK.VBELN = VBAP.VBELN
JOIN KONV ON VBAP.KNUMV = KONV.KNUMV
WHERE KNA1.KUNNR = '{customer_id}'
  AND VBAK.AUDAT >= '{cutoff}0101'
  AND KONV.KAPPL = 'V'   -- SD application
  AND KONV.KRECH = ''    -- exclude credit memos reversal
GROUP BY KNA1.KUNNR, YEAR(VBAK.AUDAT)
ORDER BY ORDER_YEAR
""".strip()

    def generate_payment_behavior_sql(self, customer_id: str, years_back: int = 20) -> str:
        """
        Payment behavior: compare BSID-ZBD3T (actual days to pay) vs.
        KNVV-ZAHLS (contractual payment terms).
        """
        cutoff = datetime.now().year - years_back
        return f"""
SELECT
    KNA1.KUNNR AS CUSTOMER_ID,
    YEAR(BSID.BUDAT) AS PAYMENT_YEAR,
    COUNT(DISTINCT BSID.BELNR) AS INVOICE_COUNT,
    AVG(BSID.ZBD3T) AS AVG_DAYS_TO_PAY,
    MAX(BSID.ZBD3T) AS MAX_DAYS_TO_PAY,
    -- Compare to contractual terms (ZAHLS)
    AVG(BSID.ZBD3T - KNVV.ZAHLS) AS AVG_TERMS_DELINQUENCY,
    -- Payment score: 100 if always on time, penalize per day late
    GREATEST(0, ROUND(100.0 - AVG(GREATEST(0, BSID.ZBD3T - KNVV.ZAHLS)) * 2, 0)) AS PAYMENT_SCORE,
    COUNT(CASE WHEN BSID.ZBD3T > KNVV.ZAHLS THEN 1 END) AS LATE_INVOICE_COUNT,
    ROUND(COUNT(CASE WHEN BSID.ZBD3T > KNVV.ZAHLS THEN 1 END) * 100.0 /
        NULLIF(COUNT(*), 0), 2) AS LATE_INVOICE_RATE
FROM KNA1
JOIN BSID ON KNA1.KUNNR = BSID.KUNNR
JOIN KNVV ON KNA1.KUNNR = KNVV.KUNNR
  AND BSID.VKORG = KNVV.VKORG
  AND BSID.VTWEG = KNVV.VTWEG
  AND BSID.SPART = KNVV.SPART
WHERE KNA1.KUNNR = '{customer_id}'
  AND BSID.BUDAT >= '{cutoff}0101'
  AND BSID.SHKZG = 'S'  -- debit items only
GROUP BY KNA1.KUNNR, YEAR(BSID.BUDAT)
ORDER BY PAYMENT_YEAR
""".strip()

    def generate_churn_signal_sql(self, customer_id: str) -> str:
        """
        Identify order gaps > 18 months (churn signal).
        """
        return f"""
WITH order_dates AS (
    SELECT DISTINCT VBAK.KUNNR, VBAK.AUDAT
    FROM VBAK
    WHERE VBAK.KUNNR = '{customer_id}'
    ORDER BY VBAK.AUDAT
),
gaps AS (
    SELECT
        od1.AUDAT AS ORDER_DATE,
        od2.AUDAT AS NEXT_ORDER_DATE,
        DAYS_BETWEEN(od1.AUDAT, od2.AUDAT) AS DAYS_GAP
    FROM order_dates od1
    JOIN order_dates od2 ON od2.AUDAT > od1.AUDAT
    WHERE NOT EXISTS (
        SELECT 1 FROM order_dates od3
        WHERE od3.AUDAT > od1.AUDAT AND od3.AUDAT < od2.AUDAT
    )
)
SELECT
    KUNNR,
    ORDER_DATE,
    NEXT_ORDER_DATE,
    DAYS_GAP,
    CASE WHEN DAYS_GAP > 540 THEN 'CHURN_SIGNAL'  -- 18 months
         WHEN DAYS_GAP > 365 THEN 'AT_RISK'
         ELSE 'ACTIVE'
    END AS CHURN_STATUS
FROM gaps
WHERE DAYS_GAP > 365
ORDER BY ORDER_DATE
""".strip()

    def compute_clv_tier(self, total_revenue: float) -> str:
        """Assign CLV tier based on total revenue."""
        for tier, threshold in sorted(self.CLV_TIERS.items(), key=lambda x: x[1], reverse=True):
            if total_revenue >= threshold:
                return tier
        return "STANDARD"


# ============================================================================
# PART 5: ECONOMIC CYCLE TAGGER
# ============================================================================

@dataclass
class MacroEvent:
    """A historical macro event that maps to date ranges."""
    name: str
    description: str
    start_date: date
    end_date: date
    category: str           # 'crisis' | 'boom' | 'regulation' | 'geopolitical'
    affected_tables: List[str]  # Which SAP tables to filter
    affected_domains: List[str] # MM, FI, SD, etc.
    severity: str             # 'major' | 'moderate' | 'minor'
    tags: List[str]


class EconomicCycleTagger:
    """
    Maps historical macro events to SAP queryable date ranges.
    Enables queries like:
      "Which vendors showed highest default rates within 90 days of the 2008 crisis?"
      "How did our procurement prices behave during the 2022 inflation surge?"

    Events: 2008 Financial Crisis, 2011 Euro Debt Crisis,
    2015 China Slowdown, 2020 COVID-19, 2022 Inflation Surge,
    2023 Rate Hike Cycle, etc.
    """

    DEFAULT_EVENTS: List[MacroEvent] = [
        MacroEvent(
            name="2008 Global Financial Crisis",
            description="Lehman collapse, credit freeze, demand collapse",
            start_date=date(2008, 9, 15),  # Lehman: Sep 15, 2008
            end_date=date(2009, 6, 30),
            category="crisis",
            affected_tables=["EKKO", "EKPO", "EINA", "LFA1", "BSIK", "MSEG"],
            affected_domains=["purchasing", "financials", "material_master"],
            severity="major",
            tags=["financial_crisis", "credit_freeze", "supply_chain_collapse", "bankruptcy"],
        ),
        MacroEvent(
            name="2011 Eurozone Debt Crisis",
            description="PIIGS sovereign debt, EU bailout, Euro fear",
            start_date=date(2011, 4, 1),
            end_date=date(2012, 3, 31),
            category="crisis",
            affected_tables=["BSIK", "BSAK", "BKPF", "EKKO", "LFA1"],
            affected_domains=["financials", "purchasing"],
            severity="moderate",
            tags=["euro_crisis", "sovereign_debt", "payment_terms_extended"],
        ),
        MacroEvent(
            name="2015 China Slowdown + Commodity Crash",
            description="China growth fears, oil price collapse, commodity rout",
            start_date=date(2015, 6, 1),
            end_date=date(2016, 2, 29),
            category="crisis",
            affected_tables=["MSEG", "MKPF", "EKKO", "EINA", "MBEW"],
            affected_domains=["material_master", "purchasing"],
            severity="moderate",
            tags=["china_slowdown", "commodity_crash", "oil_price", "raw_materials"],
        ),
        MacroEvent(
            name="2020 COVID-19 Pandemic",
            description="Global lockdowns, supply chain disruption, demand shift",
            start_date=date(2020, 3, 1),
            end_date=date(2021, 3, 31),
            category="crisis",
            affected_tables=["EKKO", "EKPO", "LIKP", "VBAK", "MSEG", "MKPF", "BSIK"],
            affected_domains=["purchasing", "sales_distribution", "material_master", "financials"],
            severity="major",
            tags=["covid", "lockdown", "supply_chain", "demand_shift", "essential_goods"],
        ),
        MacroEvent(
            name="2021 Supply Chain Crisis",
            description="Semiconductor shortage, shipping chaos, container rates 10x",
            start_date=date(2021, 4, 1),
            end_date=date(2022, 3, 31),
            category="crisis",
            affected_tables=["EKKO", "EKPO", "EINA", "MSEG", "LIKP"],
            affected_domains=["purchasing", "material_master", "sales_distribution"],
            severity="major",
            tags=["supply_chain", "semiconductor", "shipping", "lead_times"],
        ),
        MacroEvent(
            name="2022 Inflation Surge + Rate Hikes",
            description="CPI peaks, Fed/ECB rapid rate hikes, margin compression",
            start_date=date(2022, 3, 1),
            end_date=date(2023, 12, 31),
            category="crisis",
            affected_tables=["EKKO", "EKPO", "EINA", "KONV", "BSEG", "BKPF"],
            affected_domains=["purchasing", "financials", "sales_distribution"],
            severity="major",
            tags=["inflation", "interest_rates", "margin_compression", "price_increases"],
        ),
        MacroEvent(
            name="2005-2007 Global Economic Boom",
            description="Pre-crisis expansion, easy credit, commodity supercycle",
            start_date=date(2005, 1, 1),
            end_date=date(2007, 12, 31),
            category="boom",
            affected_tables=["VBAK", "VBAP", "EKKO", "MSEG", "MBEW"],
            affected_domains=["sales_distribution", "purchasing", "material_master"],
            severity="major",
            tags=["commodity_supercycle", "credit_expansion", "growth"],
        ),
        MacroEvent(
            name="2017-2018 Global Sync Growth",
            description="Synchronized global expansion, ISM at 60+",
            start_date=date(2017, 6, 1),
            end_date=date(2018, 12, 31),
            category="boom",
            affected_tables=["VBAK", "VBAP", "EKKO", "MBEW"],
            affected_domains=["sales_distribution", "purchasing", "material_master"],
            severity="moderate",
            tags=["sync_growth", "global_expansion", "trade"],
        ),
    ]

    def __init__(self, events: Optional[List[MacroEvent]] = None):
        self.events = events or self.DEFAULT_EVENTS

    def find_events_in_range(self, start: date, end: date) -> List[MacroEvent]:
        """Find all macro events that overlap with a given date range."""
        return [e for e in self.events if e.end_date >= start and e.start_date <= end]

    def find_events_by_tag(self, tag: str) -> List[MacroEvent]:
        """Find all events with a given tag."""
        return [e for e in self.events if tag in e.tags]

    def generate_event_filter_sql(
        self,
        event: MacroEvent,
        table: str,
        date_column: str,
    ) -> str:
        """Generate a WHERE clause that isolates an event period."""
        return (
            f"{table}.{date_column} >= '{event.start_date.strftime('%Y%m%d')}' "
            f"AND {table}.{date_column} <= '{event.end_date.strftime('%Y%m%d')}'"
        )

    def generate_event_comparison_sql(
        self,
        event: MacroEvent,
        baseline_start: date,
        baseline_end: date,
        table: str,
        date_column: str,
        value_column: str,
        entity_column: str,  # e.g., 'LIFNR' or 'MATNR'
        aggregation: str = "SUM",
    ) -> str:
        """
        Compare metrics DURING an event vs. the equivalent period before it.
        Returns: event-period value vs. baseline-period value with delta.
        """
        duration_days = (event.end_date - event.start_date).days
        # Equivalent baseline before the event
        baseline_event_start = date(
            event.start_date.year - 1, event.start_date.month, event.start_date.day
        )
        baseline_event_end = baseline_event_start + timedelta(days=duration_days)

        return f"""
SELECT
    '{event.name}' AS EVENT_NAME,
    '{event.category}' AS EVENT_CATEGORY,
    {aggregation}(CASE WHEN {table}.{date_column} >= '{event.start_date.strftime('%Y%m%d')}'
        AND {table}.{date_column} <= '{event.end_date.strftime('%Y%m%d')}'
        THEN {table}.{value_column} ELSE 0 END) AS EVENT_PERIOD_VALUE,
    {aggregation}(CASE WHEN {table}.{date_column} >= '{baseline_event_start.strftime('%Y%m%d')}'
        AND {table}.{date_column} <= '{baseline_event_end.strftime('%Y%m%d')}'
        THEN {table}.{value_column} ELSE 0 END) AS BASELINE_PERIOD_VALUE,
    {aggregation}(CASE WHEN {table}.{date_column} >= '{event.start_date.strftime('%Y%m%d')}'
        AND {table}.{date_column} <= '{event.end_date.strftime('%Y%m%d')}'
        THEN {table}.{value_column} ELSE 0 END) -
    {aggregation}(CASE WHEN {table}.{date_column} >= '{baseline_event_start.strftime('%Y%m%d')}'
        AND {table}.{date_column} <= '{baseline_event_end.strftime('%Y%m%d')}'
        THEN {table}.{value_column} ELSE 0 END) AS DELTA,
    ROUND(100.0 * (
        {aggregation}(CASE WHEN {table}.{date_column} >= '{event.start_date.strftime('%Y%m%d')}'
            AND {table}.{date_column} <= '{event.end_date.strftime('%Y%m%d')}'
            THEN {table}.{value_column} ELSE 0 END) -
        {aggregation}(CASE WHEN {table}.{date_column} >= '{baseline_event_start.strftime('%Y%m%d')}'
            AND {table}.{date_column} <= '{baseline_event_end.strftime('%Y%m%d')}'
            THEN {table}.{value_column} ELSE 0 END)
    ) / NULLIF({aggregation}(CASE WHEN {table}.{date_column} >= '{baseline_event_start.strftime('%Y%m%d')}'
        AND {table}.{date_column} <= '{baseline_event_end.strftime('%Y%m%d')}'
        THEN {table}.{value_column} ELSE 0 END), 0), 2) AS DELTA_PCT,
    {aggregation}(CASE WHEN {table}.{date_column} >= '{event.start_date.strftime('%Y%m%d')}'
        AND {table}.{date_column} <= '{event.end_date.strftime('%Y%m%d')}'
        THEN 1 ELSE 0 END) AS EVENT_RECORD_COUNT
FROM {table}
WHERE {table}.{date_column} >= '{baseline_event_start.strftime('%Y%m%d')}'
  AND {table}.{date_column} <= '{event.end_date.strftime('%Y%m%d')}'
""".strip()

    def summarize_vendor_behavior_during_event(
        self,
        event: MacroEvent,
        vendor_id: str,
    ) -> str:
        """
        SQL: How did a specific vendor behave during a macro event?
        - Did they default (no POs)?
        - Did prices change?
        - Did delivery performance change?
        """
        return f"""
-- Vendor {vendor_id} behavior during {event.name} ({event.start_date} to {event.end_date})

-- 1. PO Volume during event vs prior year
SELECT
    'EVENT_PERIOD' AS PERIOD_TYPE,
    COUNT(DISTINCT EKKO.EBELN) AS PO_COUNT,
    SUM(EKPO.NETWR) AS TOTAL_PO_VALUE,
    AVG(EKPO.NETWR / NULLIF(EKPO.MENGE, 0)) AS AVG_UNIT_PRICE,
    COUNT(DISTINCT EKKO.LIFNR) AS ACTIVE_VENDORS
FROM EKKO
JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
WHERE EKKO.AEDAT >= '{event.start_date.strftime('%Y%m%d')}'
  AND EKKO.AEDAT <= '{event.end_date.strftime('%Y%m%d')}'
  AND EKKO.LIFNR = '{vendor_id}'
  AND EKPO.LOEKZ = ''

UNION ALL

SELECT
    'BASELINE_PERIOD' AS PERIOD_TYPE,
    COUNT(DISTINCT EKKO.EBELN) AS PO_COUNT,
    SUM(EKPO.NETWR) AS TOTAL_PO_VALUE,
    AVG(EKPO.NETWR / NULLIF(EKPO.MENGE, 0)) AS AVG_UNIT_PRICE,
    COUNT(DISTINCT EKKO.LIFNR) AS ACTIVE_VENDORS
FROM EKKO
JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
WHERE EKKO.AEDAT >= '{date(event.start_date.year - 1, event.start_date.month, event.start_date.day).strftime('%Y%m%d')}'
  AND EKKO.AEDAT <= '{date(event.end_date.year - 1, event.end_date.month, event.end_date.day).strftime('%Y%m%d')}'
  AND EKKO.LIFNR = '{vendor_id}'
  AND EKPO.LOEKZ = ''
""".strip()


# ============================================================================
# PART 6: UNIFIED TEMPORAL ENGINE — FACADE
# ============================================================================

class TemporalEngine:
    """
    Unified facade for all Phase 7 temporal analysis capabilities.
    Use this as the single entry point.
    """

    def __init__(self):
        self.fy_engine = FiscalYearEngine()
        self.ts_aggregator = TimeSeriesAggregator()
        self.spi = SupplierPerformanceIndex()
        self.clv_engine = CustomerLifetimeValueEngine()
        self.econ_tagger = EconomicCycleTagger()

    # -------------------------------------------------------------------------
    # Fiscal Year Analysis
    # -------------------------------------------------------------------------
    def fiscal_year_analysis(
        self,
        query: str,
        tables: List[str],
        date_column: str,
        value_column: str,
        entity_column: Optional[str] = None,
        fy_expression: str = "last 3 years",
        granularity: str = "monthly",
    ) -> Dict[str, Any]:
        """
        Main entry for fiscal year analysis.

        Args:
            query: Natural language description (for documentation)
            tables: SAP tables involved
            date_column: Date column for FY filtering (e.g., 'AEDAT')
            value_column: Value to aggregate (e.g., 'NETWR', 'MENGE')
            entity_column: Optional entity to group by (e.g., 'LIFNR', 'MATNR')
            fy_expression: Expression like 'FY2020-FY2024', 'last 5 years'
            granularity: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'yearly'

        Returns: dict with generated SQL, FY range info, and metadata
        """
        fy_start, fy_end = self.fy_engine.parse_fy_expression(fy_expression)
        entity_col = entity_column or (tables[0] + "." + tables[0][:3] + "NR")  # fallback

        # Build FY range SQL
        fy_sql = self.fy_engine.generate_fy_sql(
            fy_start, fy_end, tables[0], date_column
        )

        # Build time-series aggregation
        from_date = fy_sql["date_range_start"]
        to_date = fy_sql["date_range_end"]
        gran = Granularity(granularity)

        group_by_cols = [entity_col] if entity_column else []
        tsq = TimeSeriesQuery(
            table=tables[0],
            value_column=value_column,
            date_column=date_column,
            granularity=gran,
            start_date=from_date,
            end_date=to_date,
            group_by_columns=group_by_cols,
            aggregation="SUM",
        )
        main_sql, rolling_sql = self.ts_aggregator.build_aggregation_query(tsq)

        return {
            "query_description": query,
            "fy_range": {"start": fy_start, "end": fy_end, "label": f"FY{fy_start}-FY{fy_end}"},
            "granularity": granularity,
            "tables": tables,
            "fy_sql": fy_sql,
            "aggregation_sql": main_sql,
            "rolling_sql": rolling_sql,
            "fy_comparison_sql": self.fy_engine.generate_period_comparison_sql(
                fy_start, fy_end, tables[0], date_column, value_column
            ),
        }

    # -------------------------------------------------------------------------
    # Supplier Performance
    # -------------------------------------------------------------------------
    def supplier_performance_index(
        self,
        vendor_id: str,
        start_fy: str = "last 3 years",
    ) -> Dict[str, Any]:
        """Generate all 3 SPI dimension SQLs for a vendor."""
        fy_start, fy_end = self.fy_engine.parse_fy_expression(start_fy)
        return {
            "vendor_id": vendor_id,
            "analysis_period": f"FY{fy_start} to FY{fy_end}",
            "delivery_sql": self.spi.generate_delivery_sql(vendor_id, fy_start, fy_end),
            "quality_sql": self.spi.generate_quality_sql(vendor_id, fy_start, fy_end),
            "price_sql": self.spi.generate_price_sql(vendor_id, fy_start, fy_end),
        }

    # -------------------------------------------------------------------------
    # Customer Lifetime Value
    # -------------------------------------------------------------------------
    def customer_lifetime_value(
        self,
        customer_id: str,
        years_back: int = 20,
    ) -> Dict[str, Any]:
        """Generate all CLV dimension SQLs for a customer."""
        return {
            "customer_id": customer_id,
            "analysis_period_years": years_back,
            "revenue_sql": self.clv_engine.generate_revenue_sql(customer_id, years_back),
            "discount_sql": self.clv_engine.generate_discount_sql(customer_id, years_back),
            "payment_sql": self.clv_engine.generate_payment_behavior_sql(customer_id, years_back),
            "churn_sql": self.clv_engine.generate_churn_signal_sql(customer_id),
        }

    # -------------------------------------------------------------------------
    # Economic Cycle Analysis
    # -------------------------------------------------------------------------
    def economic_cycle_analysis(
        self,
        event_name: Optional[str] = None,
        date_range: Optional[Tuple[date, date]] = None,
        entity_column: str = "LIFNR",
        value_column: str = "NETWR",
        table: str = "EKKO",
        date_column: str = "AEDAT",
    ) -> Dict[str, Any]:
        """
        Analyze entity behavior during macro economic events.

        If event_name given: analyze that specific event.
        If date_range given: find all events in that range and analyze them.
        """
        if date_range:
            events = self.econ_tagger.find_events_in_range(date_range[0], date_range[1])
        elif event_name:
            events = [e for e in self.econ_tagger.events if event_name.lower() in e.name.lower()]
        else:
            events = self.econ_tagger.DEFAULT_EVENTS

        results = []
        for event in events:
            results.append({
                "event_name": event.name,
                "description": event.description,
                "category": event.category,
                "severity": event.severity,
                "start_date": event.start_date,
                "end_date": event.end_date,
                "duration_days": (event.end_date - event.start_date).days,
                "event_filter_sql": self.econ_tagger.generate_event_filter_sql(event, table, date_column),
                "comparison_sql": self.econ_tagger.generate_event_comparison_sql(
                    event,
                    date_range[0] if date_range else date(event.start_date.year - 1, event.start_date.month, event.start_date.day),
                    date_range[1] if date_range else event.end_date,
                    table, date_column, value_column, entity_column
                ),
                "vendor_behavior_sql": self.econ_tagger.summarize_vendor_behavior_during_event(event, entity_column),
            })

        return {
            "events_found": len(results),
            "events": results,
            "analysis_config": {
                "table": table,
                "date_column": date_column,
                "value_column": value_column,
                "entity_column": entity_column,
            }
        }
