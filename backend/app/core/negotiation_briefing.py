"""
negotiation_briefing.py — Phase 8: Negotiation Briefing Generator
============================================================
Synthesizes 20 years of SAP data into a structured, actionable
negotiation brief for procurement and sales contract renewals.

Input:  customer/vendor ID + negotiation type (price increase, contract renewal, etc.)
Output: A complete negotiation brief with:
  - Relationship history summary
  - Price sensitivity analysis
  - Competitive positioning
  - Risk assessment
  - Recommended negotiation tactics
  - BATNA (Best Alternative to a Negotiated Agreement)

The brief is designed to be read by a procurement manager or sales rep
15 minutes before a negotiation — actionable, data-driven, not verbose.

Usage:
  from app.core.negotiation_briefing import NegotiationBriefingGenerator
  gen = NegotiationBriefingGenerator()
  brief = gen.generate(customer_id="KUNNR-10000142", entity_type="customer")
  print(brief.format_text())
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Literal
from enum import Enum


# ============================================================================
# Data Models
# ============================================================================

class EntityType(Enum):
    CUSTOMER = "customer"
    VENDOR = "vendor"


class NegotiationType(Enum):
    PRICE_INCREASE = "price_increase"
    CONTRACT_RENEWAL = "contract_renewal"
    NEW_CONTRACT = "new_contract"
    VOLUME_REVISION = "volume_revision"
    TERMS_REVISION = "terms_revision"


class SensitivityTier(Enum):
    HIGHLY_SENSITIVE = "HIGHLY_SENSITIVE"   # < 4.0 PSI
    MODERATELY_SENSITIVE = "MODERATELY_SENSITIVE"  # 4-6 PSI
    LOW_SENSITIVE = "LOW_SENSITIVE"          # > 6.0 PSI
    INSENSITIVE = "INSENSITIVE"              # > 8.0 PSI


@dataclass
class RelationshipSnapshot:
    """A single-year snapshot of the relationship."""
    year: int
    revenue_or_spend: float
    order_count: int
    avg_order_value: float
    discount_pct: float
    payment_days_actual: float
    payment_days_contractual: float
    payment_score: float
    return_rate: float
    active_months: int        # months with at least one order


@dataclass
class PriceIncreaseRecord:
    """A historical price increase attempt."""
    year: int
    proposed_increase_pct: float
    accepted_increase_pct: float
    outcome: str              # "accepted", "rejected", "renegotiated", "churned"
    context: str              # brief description of what happened


@dataclass
class NegotiationBrief:
    """Complete negotiation brief for an entity."""
    entity_id: str
    entity_name: str
    entity_type: EntityType
    negotiation_type: NegotiationType
    relationship_years: int
    first_order_date: str
    last_order_date: str

    # Relationship history
    snapshots: List[RelationshipSnapshot]
    price_increase_history: List[PriceIncreaseRecord]

    # Computed scores
    price_sensitivity_index: float
    sensitivity_tier: SensitivityTier
    payment_reliability_score: float
    clv_tier: str

    # Key facts
    total_revenue_20yr: float
    avg_annual_revenue: float
    current_year_revenue: float
    revenue_trend_5yr: float        # CAGR or % change
    total_discounts_20yr: float
    avg_discount_pct: float

    # Risk assessment
    churn_risk: str                 # "LOW", "MODERATE", "HIGH", "CRITICAL"
    churn_evidence: List[str]
    concentration_risk: str          # How dependent is this entity on us?
    competitive_threat: str         # Evidence of dual-sourcing or competitor activity

    # BATNA
    batna: str
    batna_strength: float           # 0-10

    # Recommendation
    recommended_increase_pct: float
    max_acceptable_increase_pct: float
    recommended_discount: float
    top_tactics: List[str]
    bottom_line: str

    # Meta
    generated_at: str
    data_quality: str                # "HIGH" (>5yr data), "MEDIUM" (2-5yr), "LOW" (<2yr)


# ============================================================================
# SQL Generators — these produce the raw SAP queries
# ============================================================================

class NegotiationSQLGenerator:
    """
    Generates the SAP SQL queries needed to build a negotiation brief.
    These are standalone SQL strings that can be executed against SAP HANA.
    """

    @staticmethod
    def relationship_summary_sql(entity_id: str, entity_type: EntityType, years_back: int = 20) -> str:
        """
        Annual revenue, order count, average order value per year.
        For customers: VBAP.NETWR. For vendors: EKPO.NETWR.
        """
        now = datetime.now().year
        cutoff = now - years_back

        if entity_type == EntityType.CUSTOMER:
            return f"""
SELECT
    YEAR(VBAK.AUDAT) AS ORDER_YEAR,
    SUM(VBAP.NETWR) AS ANNUAL_REVENUE,
    COUNT(DISTINCT VBAK.VBELN) AS ORDER_COUNT,
    AVG(VBAP.NETWR) AS AVG_ORDER_VALUE,
    COUNT(DISTINCT MONTH(VBAK.AUDAT)) AS ACTIVE_MONTHS,
    MIN(VBAK.AUDAT) AS FIRST_ORDER_DATE,
    MAX(VBAK.AUDAT) AS LAST_ORDER_DATE
FROM VBAK
JOIN VBAP ON VBAK.VBELN = VBAP.VBELN
WHERE VBAK.KUNNR = '{entity_id}'
  AND VBAK.AUDAT >= '{cutoff}0101'
  AND VBAK.FKSTV = ''
GROUP BY YEAR(VBAK.AUDAT)
ORDER BY ORDER_YEAR
""".strip()

        else:  # VENDOR
            return f"""
SELECT
    YEAR(EKKO.AEDAT) AS ORDER_YEAR,
    SUM(EKPO.NETWR) AS ANNUAL_SPEND,
    COUNT(DISTINCT EKKO.EBELN) AS PO_COUNT,
    AVG(EKPO.NETWR) AS AVG_PO_VALUE,
    COUNT(DISTINCT MONTH(EKKO.AEDAT)) AS ACTIVE_MONTHS,
    MIN(EKKO.AEDAT) AS FIRST_ORDER_DATE,
    MAX(EKKO.AEDAT) AS LAST_ORDER_DATE
FROM EKKO
JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
WHERE EKKO.LIFNR = '{entity_id}'
  AND EKKO.AEDAT >= '{cutoff}0101'
  AND EKKO.LOEKZ = ''
  AND EKPO.LOEKZ = ''
GROUP BY YEAR(EKKO.AEDAT)
ORDER BY ORDER_YEAR
""".strip()

    @staticmethod
    def discount_analysis_sql(entity_id: str, entity_type: EntityType, years_back: int = 20) -> str:
        """Annual discount analysis — KONV condition types."""
        now = datetime.now().year
        cutoff = now - years_back

        if entity_type == EntityType.CUSTOMER:
            return f"""
SELECT
    YEAR(VBAK.AUDAT) AS ORDER_YEAR,
    SUM(VBAP.NETWR) AS GROSS_REVENUE,
    SUM(CASE WHEN KONV.KSCHL IN ('KB01', 'K007', 'K020')
        THEN KONV.KBETR ELSE 0 END) AS TOTAL_DISCOUNT_AMT,
    ROUND(100.0 * SUM(CASE WHEN KONV.KSCHL IN ('KB01', 'K007', 'K020')
        THEN KONV.KBETR ELSE 0 END) / NULLIF(SUM(VBAP.NETWR), 0), 2) AS DISCOUNT_PCT,
    SUM(CASE WHEN KONV.KSCHL = 'KB01'
        THEN KONV.KBETR ELSE 0 END) AS MANUAL_DISCOUNT_PCT,
    SUM(CASE WHEN KONV.KSCHL = 'K007'
        THEN KONV.KBETR ELSE 0 END) AS VOLUME_DISCOUNT_PCT
FROM VBAK
JOIN VBAP ON VBAK.VBELN = VBAP.VBELN
JOIN KONV ON VBAP.KNUMV = KONV.KNUMV
WHERE VBAK.KUNNR = '{entity_id}'
  AND VBAK.AUDAT >= '{cutoff}0101'
  AND KONV.KAPPL = 'V'
  AND KONV.KRECH = ''
GROUP BY YEAR(VBAK.AUDAT)
ORDER BY ORDER_YEAR
""".strip()

        else:  # VENDOR
            return f"""
SELECT
    YEAR(EKKO.AEDAT) AS ORDER_YEAR,
    SUM(EKPO.NETWR) AS GROSS_SPEND,
    SUM(CASE WHEN KONV.KSCHL IN ('PB00', 'PBXX')
        THEN KONV.KBETR ELSE 0 END) AS TOTAL_DISCOUNT_AMT,
    ROUND(100.0 * SUM(CASE WHEN KONV.KSCHL IN ('PB00', 'PBXX')
        THEN KONV.KBETR ELSE 0 END) / NULLIF(SUM(EKPO.NETWR), 0), 2) AS DISCOUNT_PCT
FROM EKKO
JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
JOIN KONV ON EKPO.KNUMV = KONV.KNUMV
WHERE EKKO.LIFNR = '{entity_id}'
  AND EKKO.AEDAT >= '{cutoff}0101'
  AND KONV.KAPPL = 'M'
GROUP BY YEAR(EKKO.AEDAT)
ORDER BY ORDER_YEAR
""".strip()

    @staticmethod
    def payment_behavior_sql(entity_id: str, entity_type: EntityType, years_back: int = 20) -> str:
        """Payment days vs contractual terms."""
        now = datetime.now().year
        cutoff = now - years_back

        if entity_type == EntityType.CUSTOMER:
            return f"""
SELECT
    YEAR(BSID.BUDAT) AS PAYMENT_YEAR,
    COUNT(DISTINCT BSID.BELNR) AS INVOICE_COUNT,
    AVG(BSID.ZBD3T) AS AVG_DAYS_TO_PAY,
    MAX(BSID.ZBD3T) AS MAX_DAYS_TO_PAY,
    KNVV.ZAHLS AS CONTRACTUAL_TERMS,
    ROUND(100.0 - LEAST(100.0, AVG(GREATEST(0, BSID.ZBD3T - KNVV.ZAHLS)) * 2), 0) AS PAYMENT_SCORE,
    COUNT(CASE WHEN BSID.ZBD3T > KNVV.ZAHLS THEN 1 END) AS LATE_INVOICE_COUNT,
    ROUND(COUNT(CASE WHEN BSID.ZBD3T > KNVV.ZAHLS THEN 1 END) * 100.0 /
        NULLIF(COUNT(*), 0), 2) AS LATE_INVOICE_RATE
FROM BSID
JOIN KNA1 ON BSID.KUNNR = KNA1.KUNNR
JOIN KNVV ON KNA1.KUNNR = KNVV.KUNNR
  AND BSID.VKORG = KNVV.VKORG
  AND BSID.VTWEG = KNVV.VTWEG
  AND BSID.SPART = KNVV.SPART
WHERE BSID.KUNNR = '{entity_id}'
  AND BSID.BUDAT >= '{cutoff}0101'
  AND BSID.SHKZG = 'S'
GROUP BY YEAR(BSID.BUDAT), KNVV.ZAHLS
ORDER BY PAYMENT_YEAR
""".strip()

        else:  # VENDOR
            return f"""
SELECT
    YEAR(BSIK.BUDAT) AS PAYMENT_YEAR,
    COUNT(DISTINCT BSIK.BELNR) AS INVOICE_COUNT,
    AVG(BSIK.ZBD3T) AS AVG_DAYS_TO_PAY,
    MAX(BSIK.ZBD3T) AS MAX_DAYS_TO_PAY,
    LFB1.ZAHLS AS CONTRACTUAL_TERMS,
    ROUND(100.0 - LEAST(100.0, AVG(GREATEST(0, BSIK.ZBD3T - LFB1.ZAHLS)) * 2), 0) AS PAYMENT_SCORE,
    COUNT(CASE WHEN BSIK.ZBD3T > LFB1.ZAHLS THEN 1 END) AS LATE_INVOICE_COUNT
FROM BSIK
JOIN LFA1 ON BSIK.LIFNR = LFA1.LIFNR
JOIN LFB1 ON LFA1.LIFNR = LFB1.LIFNR
WHERE BSIK.LIFNR = '{entity_id}'
  AND BSIK.BUDAT >= '{cutoff}0101'
  AND BSIK.SHKZG = 'S'
GROUP BY YEAR(BSIK.BUDAT), LFB1.ZAHLS
ORDER BY PAYMENT_YEAR
""".strip()

    @staticmethod
    def price_increase_history_sql(entity_id: str, entity_type: EntityType, years_back: int = 20) -> str:
        """
        Reconstruct historical price increase attempts from KONV condition changes.
        Detects increases by looking at large KONV.KBETR deltas year-over-year.
        """
        now = datetime.now().year
        cutoff = now - years_back

        if entity_type == EntityType.CUSTOMER:
            return f"""
WITH yearly_pricing AS (
    SELECT
        YEAR(VBAK.AUDAT) AS PRICING_YEAR,
        VBAP.MATNR,
        AVG(KONV.KBETR) AS AVG_PRICE
    FROM VBAK
    JOIN VBAP ON VBAK.VBELN = VBAP.VBELN
    JOIN KONV ON VBAP.KNUMV = KONV.KNUMV
    WHERE VBAK.KUNNR = '{entity_id}'
      AND VBAK.AUDAT >= '{cutoff}0101'
      AND KONV.KSCHL = 'PR00'
      AND KONV.KAPPL = 'V'
    GROUP BY YEAR(VBAK.AUDAT), VBAP.MATNR
),
price_changes AS (
    SELECT
        y1.PRICING_YEAR,
        y1.MATNR,
        y1.AVG_PRICE,
        y2.AVG_PRICE AS PRIOR_PRICE,
        ROUND(100.0 * (y1.AVG_PRICE - y2.AVG_PRICE) / NULLIF(y2.AVG_PRICE, 0), 1) AS PRICE_CHANGE_PCT
    FROM yearly_pricing y1
    JOIN yearly_pricing y2 ON y1.MATNR = y2.MATNR AND y1.PRICING_YEAR = y2.PRICING_YEAR + 1
)
SELECT
    PRICING_YEAR,
    ROUND(AVG(PRICE_CHANGE_PCT), 1) AS AVG_PRICE_INCREASE_PCT,
    COUNT(DISTINCT MATNR) AS PRODUCTS_WITH_INCREASE,
    MAX(PRICE_CHANGE_PCT) AS LARGEST_INCREASE_PCT
FROM price_changes
WHERE PRICE_CHANGE_PCT > 1.0  -- only significant increases
GROUP BY PRICING_YEAR
ORDER BY PRICING_YEAR
""".strip()
        else:
            return f"""
WITH yearly_pricing AS (
    SELECT
        YEAR(EKKO.AEDAT) AS PRICING_YEAR,
        EKPO.MATNR,
        AVG(KONV.KBETR) AS AVG_PRICE
    FROM EKKO
    JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
    JOIN KONV ON EKPO.KNUMV = KONV.KNUMV
    WHERE EKKO.LIFNR = '{entity_id}'
      AND EKKO.AEDAT >= '{cutoff}0101'
      AND KONV.KSCHL = 'PB00'
      AND KONV.KAPPL = 'M'
    GROUP BY YEAR(EKKO.AEDAT), EKPO.MATNR
),
price_changes AS (
    SELECT
        y1.PRICING_YEAR,
        y1.MATNR,
        y1.AVG_PRICE,
        y2.AVG_PRICE AS PRIOR_PRICE,
        ROUND(100.0 * (y1.AVG_PRICE - y2.AVG_PRICE) / NULLIF(y2.AVG_PRICE, 0), 1) AS PRICE_CHANGE_PCT
    FROM yearly_pricing y1
    JOIN yearly_pricing y2 ON y1.MATNR = y2.MATNR AND y1.PRICING_YEAR = y2.PRICING_YEAR + 1
)
SELECT
    PRICING_YEAR,
    ROUND(AVG(PRICE_CHANGE_PCT), 1) AS AVG_PRICE_DECREASE_PCT,
    COUNT(DISTINCT MATNR) AS PRODUCTS_WITH_DECREASE
FROM price_changes
WHERE PRICE_CHANGE_PCT < -1.0
GROUP BY PRICING_YEAR
ORDER BY PRICING_YEAR
""".strip()

    @staticmethod
    def dual_sourcing_evidence_sql(entity_id: str, entity_type: EntityType) -> str:
        """
        Look for evidence that this entity has been sourcing from competitors.
        For customers: look for sudden volume drops that coincide with market events.
        For vendors: look for gaps in info record validity (DATAB/DATBI).
        """
        if entity_type == EntityType.CUSTOMER:
            return f"""
-- Volume trend analysis to detect competitive switching
WITH monthly_volume AS (
    SELECT
        YEAR(VBAK.AUDAT) AS order_year,
        MONTH(VBAK.AUDAT) AS order_month,
        SUM(VBAP.NETWR) AS monthly_revenue
    FROM VBAK
    JOIN VBAP ON VBAK.VBELN = VBAP.VBELN
    WHERE VBAK.KUNNR = '{entity_id}'
      AND VBAK.AUDAT >= '20150101'
    GROUP BY YEAR(VBAK.AUDAT), MONTH(VBAK.AUDAT)
),
volume_changes AS (
    SELECT
        order_year,
        order_month,
        monthly_revenue,
        LAG(monthly_revenue, 1) OVER (ORDER BY order_year, order_month) AS PRIOR_MONTH,
        ROUND(100.0 * (monthly_revenue - LAG(monthly_revenue, 1) OVER (ORDER BY order_year, order_month))
            / NULLIF(LAG(monthly_revenue, 1) OVER (ORDER BY order_year, order_month), 0), 1) AS MOM_CHANGE_PCT
    FROM monthly_volume
)
SELECT
    order_year,
    MIN(monthly_revenue) AS LOWEST_MONTH,
    MAX(monthly_revenue) AS HIGHEST_MONTH,
    ROUND(100.0 * (MAX(monthly_revenue) - MIN(monthly_revenue)) / NULLIF(MAX(monthly_revenue), 0), 1) AS VOLUME_VOLATILITY_PCT,
    COUNT(CASE WHEN MOM_CHANGE_PCT < -20 THEN 1 END) AS SIGNIFICANT_DROP_MONTHS
FROM volume_changes
GROUP BY order_year
ORDER BY order_year
""".strip()
        else:
            return f"""
-- Vendor info record gaps — may indicate they stopped being approved supplier
SELECT
    EINA.MATNR AS MATERIAL,
    EINA.DATAB AS VALID_FROM,
    EINA.DATBI AS VALID_TO,
    CASE
        WHEN EINA.DATBI < '{datetime.now().year - 1}0101' THEN 'EXPIRED'
        WHEN EINA.DATBI >= '{datetime.now().year}0101' THEN 'CURRENT'
        ELSE 'FORMER'
    END AS STATUS
FROM EINA
WHERE EINA.LIFNR = '{entity_id}'
ORDER BY EINA.DATBI DESC
""".strip()


# ============================================================================
# Briefing Synthesizer — turns raw data into a NegotiationBrief
# ============================================================================

class NegotiationBriefingGenerator:
    """
    Facade for generating negotiation briefs.
    Wraps NegotiationSQLGenerator (SQL templates) + NegotiationBriefingSynthesizer (data → brief).
    """

    def __init__(self):
        self.sql_gen = NegotiationSQLGenerator()
        self.synthesizer = NegotiationBriefingSynthesizer()

    def get_sql(self, entity_id: str, entity_type: EntityType, query_type: str = "relationship") -> str:
        """Return the SAP SQL template for a given query type."""
        if query_type == "relationship":
            return self.sql_gen.relationship_summary_sql(entity_id, entity_type)
        elif query_type == "discount":
            return self.sql_gen.discount_analysis_sql(entity_id, entity_type)
        elif query_type == "payment":
            return self.sql_gen.payment_behavior_sql(entity_id, entity_type)
        elif query_type == "price_increase":
            return self.sql_gen.price_increase_history_sql(entity_id, entity_type)
        elif query_type == "dual_sourcing":
            return self.sql_gen.dual_sourcing_evidence_sql(entity_id, entity_type)
        return ""

    def generate(
        self,
        entity_id: str,
        entity_name: str,
        entity_type: EntityType,
        negotiation_type: NegotiationType,
        relationship_data: Dict[str, List[Dict]],
        price_increase_data: List[Dict],
        payment_data: List[Dict],
    ) -> NegotiationBrief:
        """Generate a complete negotiation brief from raw query results."""
        return self.synthesizer.synthesize(
            entity_id=entity_id,
            entity_name=entity_name,
            entity_type=entity_type,
            negotiation_type=negotiation_type,
            relationship_data=relationship_data,
            price_increase_data=price_increase_data,
            payment_data=payment_data,
        )


class NegotiationBriefingSynthesizer:
    """
    Takes raw query results (mock or real) and synthesizes them into
    a structured NegotiationBrief dataclass.

    In production, this receives real query results from SAP HANA.
    For demo, it accepts pre-populated result dicts.
    """

    def synthesize(
        self,
        entity_id: str,
        entity_name: str,
        entity_type: EntityType,
        negotiation_type: NegotiationType,
        relationship_data: Dict[str, List[Dict]],
        price_increase_data: List[Dict],
        payment_data: List[Dict],
        now: Optional[date] = None,
    ) -> NegotiationBrief:
        now_date = now or date.today()
        current_year = now_date.year

        # Build snapshots
        rel = relationship_data  # alias
        year_keys = sorted([r["ORDER_YEAR"] for r in rel.get("relationship", [])])
        if not year_keys:
            return self._empty_brief(entity_id, entity_name, entity_type, negotiation_type)

        snapshots = self._build_snapshots(rel)
        total_20yr = sum(s.avg_order_value * s.order_count for s in snapshots)

        # Price sensitivity — convert raw dicts to PriceIncreaseRecord
        pi_records = self._build_price_increase_history(price_increase_data)
        psi = self._compute_price_sensitivity_index(snapshots, pi_records)
        sensitivity = self._classify_sensitivity(psi)

        # Payment reliability
        payment_score = self._compute_payment_score(payment_data)

        # CLV tier
        clv_tier = self._compute_clv_tier(total_20yr)

        # Revenue trend 5yr
        recent_snapshots = [s for s in snapshots if s.year >= current_year - 5]
        revenue_trend = self._compute_revenue_trend(recent_snapshots)

        # Churn risk
        churn_risk, churn_evidence = self._assess_churn_risk(snapshots, payment_data)

        # Price increase history
        pi_history = self._build_price_increase_history(price_increase_data)

        # BATNA
        batna, batna_strength = self._assess_batna(entity_type, churn_risk, clv_tier)

        # Recommendation
        rec_increase, max_increase, rec_discount = self._compute_recommendation(
            entity_type, negotiation_type, psi, sensitivity, pi_history,
            churn_risk, clv_tier, payment_score,
        )

        # Tactics
        tactics = self._generate_tactics(
            entity_type, negotiation_type, psi, sensitivity,
            payment_score, churn_risk, pi_history,
        )

        # Data quality
        data_quality = self._assess_data_quality(year_keys)

        # Bottom line
        bottom_line = self._generate_bottom_line(
            entity_type, negotiation_type, rec_increase, churn_risk, psi, clv_tier,
        )

        return NegotiationBrief(
            entity_id=entity_id,
            entity_name=entity_name,
            entity_type=entity_type,
            negotiation_type=negotiation_type,
            relationship_years=len(year_keys),
            first_order_date=str(year_keys[0]),
            last_order_date=str(year_keys[-1]),
            snapshots=snapshots,
            price_increase_history=pi_history,
            price_sensitivity_index=psi,
            sensitivity_tier=sensitivity,
            payment_reliability_score=payment_score,
            clv_tier=clv_tier,
            total_revenue_20yr=total_20yr,
            avg_annual_revenue=total_20yr / max(len(year_keys), 1),
            current_year_revenue=next((s.avg_order_value * s.order_count
                                       for s in snapshots if s.year == current_year), 0.0),
            revenue_trend_5yr=revenue_trend,
            total_discounts_20yr=sum(s.discount_pct * (s.avg_order_value * s.order_count) / 100
                                     for s in snapshots),
            avg_discount_pct=sum(s.discount_pct for s in snapshots) / max(len(snapshots), 1),
            churn_risk=churn_risk,
            churn_evidence=churn_evidence,
            concentration_risk="MEDIUM",  # would need product-level data
            competitive_threat=self._assess_competitive_threat(snapshots),
            batna=batna,
            batna_strength=batna_strength,
            recommended_increase_pct=rec_increase,
            max_acceptable_increase_pct=max_increase,
            recommended_discount=rec_discount,
            top_tactics=tactics,
            bottom_line=bottom_line,
            generated_at=datetime.now().isoformat(),
            data_quality=data_quality,
        )

    def _build_snapshots(self, rel: Dict) -> List[RelationshipSnapshot]:
        snapshots = []
        for row in rel.get("relationship", []):
            year = int(row.get("ORDER_YEAR", 0))
            revenue = float(row.get("ANNUAL_REVENUE", 0) or 0)
            orders = int(row.get("ORDER_COUNT", 0) or 0)
            avg_ov = float(row.get("AVG_ORDER_VALUE", 0) or 0)
            disc = float(row.get("DISCOUNT_PCT", 0) or 0)
            active = int(row.get("ACTIVE_MONTHS", 0) or 0)

            # Payment data keyed by year
            pmt = next((p for p in rel.get("payment", []) if int(p.get("PAYMENT_YEAR", 0)) == year), {})
            pmt_days = float(pmt.get("AVG_DAYS_TO_PAY", 0) or 0)
            pmt_score = float(pmt.get("PAYMENT_SCORE", 0) or 0)
            ret_rate = float(row.get("RETURN_RATE", 0) or 0)

            snapshots.append(RelationshipSnapshot(
                year=year,
                revenue_or_spend=revenue,
                order_count=orders,
                avg_order_value=avg_ov if avg_ov > 0 else (revenue / max(orders, 1)),
                discount_pct=disc,
                payment_days_actual=pmt_days,
                payment_days_contractual=0.0,  # would come from payment data
                payment_score=pmt_score,
                return_rate=ret_rate,
                active_months=active,
            ))
        return snapshots

    def _compute_price_sensitivity_index(
        self,
        snapshots: List[RelationshipSnapshot],
        pi_history: List[PriceIncreaseRecord],
    ) -> float:
        """
        Price Sensitivity Index (PSI): 0-10 scale.
        Based on:
        1. How often price increases were accepted (higher = less sensitive)
        2. Volume response to past increases (higher increase = more sensitive)
        3. Discount rate (higher discount accepted = more sensitive)
        """
        if not snapshots:
            return 5.0  # neutral

        # Component 1: Discount rate (0-4 points)
        avg_disc = sum(s.discount_pct for s in snapshots) / max(len(snapshots), 1)
        disc_score = min(4.0, avg_disc / 10.0 * 4.0)  # 0% disc = 0pts, 25%+ = 4pts

        # Component 2: Price increase acceptance rate (0-4 points)
        if pi_history:
            accepted = sum(1 for p in pi_history if p.outcome == "accepted")
            renegotiated = sum(1 for p in pi_history if p.outcome == "renegotiated")
            acceptance_rate = (accepted + renegotiated * 0.5) / max(len(pi_history), 1)
            pi_score = acceptance_rate * 4.0
        else:
            pi_score = 2.0  # neutral if no history

        # Component 3: Volume stability (0-2 points)
        revenues = [s.revenue_or_spend for s in snapshots if s.revenue_or_spend > 0]
        if len(revenues) >= 2:
            avg_rev = sum(revenues) / len(revenues)
            volatility = max(revenues) / max(avg_rev, 1) - 1
            vol_score = max(0, 2.0 - volatility * 2)  # high stability = 2pts
        else:
            vol_score = 1.0

        psi = disc_score + pi_score + vol_score
        return round(min(10.0, max(0.0, psi)), 1)

    def _classify_sensitivity(self, psi: float) -> SensitivityTier:
        if psi < 4.0:
            return SensitivityTier.HIGHLY_SENSITIVE
        elif psi < 6.0:
            return SensitivityTier.MODERATELY_SENSITIVE
        elif psi < 8.0:
            return SensitivityTier.LOW_SENSITIVE
        else:
            return SensitivityTier.INSENSITIVE

    def _compute_payment_score(self, payment_data: List[Dict]) -> float:
        if not payment_data:
            return 75.0  # default
        scores = [float(p.get("PAYMENT_SCORE", 75)) for p in payment_data]
        return round(sum(scores) / len(scores), 1)

    def _compute_clv_tier(self, total_20yr: float) -> str:
        if total_20yr >= 1_000_000:
            return "PLATINUM"
        elif total_20yr >= 500_000:
            return "GOLD"
        elif total_20yr >= 100_000:
            return "SILVER"
        elif total_20yr >= 25_000:
            return "BRONZE"
        return "STANDARD"

    def _compute_revenue_trend(self, recent: List[RelationshipSnapshot]) -> float:
        """Return % change over the period (CAGR approximation)."""
        if len(recent) < 2:
            return 0.0
        sorted_s = sorted(recent, key=lambda s: s.year)
        first = sorted_s[0].revenue_or_spend
        last = sorted_s[-1].revenue_or_spend
        years = sorted_s[-1].year - sorted_s[0].year
        if first <= 0 or years == 0:
            return 0.0
        return round(100.0 * (last - first) / first, 1)

    def _assess_churn_risk(
        self,
        snapshots: List[RelationshipSnapshot],
        payment_data: List[Dict],
    ) -> tuple[str, List[str]]:
        evidence = []
        churn_risk = "LOW"

        # Check for order gaps
        years = sorted([s.year for s in snapshots])
        gaps = []
        for i in range(1, len(years)):
            if years[i] - years[i-1] > 1:
                gaps.append(f"{years[i] - years[i-1]} year gap in {years[i-1]}-{years[i]}")

        if len(gaps) >= 2:
            churn_risk = "HIGH"
            evidence.append(f"Multiple order gaps: {', '.join(gaps)}")
        elif len(gaps) == 1:
            churn_risk = "MODERATE"
            evidence.append(f"Single order gap: {gaps[0]}")

        # Check for declining revenue
        if len(snapshots) >= 3:
            recent_3 = [s.revenue_or_spend for s in snapshots[-3:]]
            if all(recent_3[i] >= recent_3[i+1] for i in range(len(recent_3)-1)):
                churn_risk = max(churn_risk, "MODERATE")
                evidence.append("Revenue declining for 3 consecutive years")

        # Payment score check
        if payment_data:
            recent_pmt = payment_data[-1] if payment_data else {}
            score = float(recent_pmt.get("PAYMENT_SCORE", 100))
            if score < 60:
                churn_risk = max(churn_risk, "HIGH")
                evidence.append(f"Payment score below 60: {score}")
            elif score < 75:
                churn_risk = max(churn_risk, "MODERATE")
                evidence.append(f"Payment score moderate: {score}")

        if not evidence:
            evidence.append("No significant churn indicators — relationship stable")

        return churn_risk, evidence

    def _build_price_increase_history(self, pi_data: List[Dict]) -> List[PriceIncreaseRecord]:
        history = []
        for row in pi_data:
            year = int(row.get("PRICING_YEAR", 0))
            change = float(row.get("AVG_PRICE_INCREASE_PCT", 0) or 0)
            if change == 0:
                continue

            if change > 0:
                outcome = "accepted" if change <= 5.0 else "renegotiated"
            else:
                outcome = "rejected"

            history.append(PriceIncreaseRecord(
                year=year,
                proposed_increase_pct=change,
                accepted_increase_pct=change,
                outcome=outcome,
                context=f"Price {change:.1f}% {'increase' if change > 0 else 'decrease'} in {year}",
            ))
        return history

    def _assess_batna(self, entity_type: EntityType, churn_risk: str, clv_tier: str) -> tuple[str, float]:
        if clv_tier == "PLATINUM":
            batna = "We cannot easily replace this account. Retain at reasonable margin."
            strength = 3.0
        elif clv_tier == "GOLD":
            batna = "Limited alternatives in short term but market has options."
            strength = 5.0
        elif clv_tier in ("SILVER", "BRONZE"):
            batna = "We have viable alternatives. Market comparison shopping feasible."
            strength = 7.0
        else:
            batna = "Easily replaceable. This is a commodity relationship."
            strength = 9.0

        # Churn risk improves or weakens BATNA
        if churn_risk == "HIGH":
            strength = min(10, strength + 1)
            batna = "They may leave regardless — use this as leverage."
        elif churn_risk == "LOW":
            strength = max(1, strength - 1)

        return batna, strength

    def _compute_recommendation(
        self,
        entity_type: EntityType,
        neg_type: NegotiationType,
        psi: float,
        sensitivity: SensitivityTier,
        pi_history: List[PriceIncreaseRecord],
        churn_risk: str,
        clv_tier: str,
        payment_score: float,
    ) -> tuple[float, float, float]:
        # Default: 3-5% for customers, 2-4% for vendors
        if entity_type == EntityType.CUSTOMER:
            base_increase = 4.0
        else:
            base_increase = 3.0

        # Adjust for sensitivity
        if sensitivity == SensitivityTier.HIGHLY_SENSITIVE:
            rec_increase = base_increase * 0.6
            max_increase = base_increase * 0.9
        elif sensitivity == SensitivityTier.MODERATELY_SENSITIVE:
            rec_increase = base_increase * 0.9
            max_increase = base_increase * 1.1
        elif sensitivity == SensitivityTier.LOW_SENSITIVE:
            rec_increase = base_increase * 1.1
            max_increase = base_increase * 1.3
        else:
            rec_increase = base_increase * 1.2
            max_increase = base_increase * 1.5

        # Adjust for churn risk
        if churn_risk == "HIGH":
            rec_increase = min(rec_increase, base_increase * 0.5)
            max_increase = min(max_increase, base_increase * 0.7)
        elif churn_risk == "LOW":
            rec_increase = rec_increase * 1.1
            max_increase = max_increase * 1.1

        # Adjust for payment score
        if payment_score < 70:
            rec_discount = 1.0  # offer small discount to improve payment behavior
        else:
            rec_discount = 0.0

        return round(rec_increase, 1), round(max_increase, 1), round(rec_discount, 1)

    def _generate_tactics(
        self,
        entity_type: EntityType,
        neg_type: NegotiationType,
        psi: float,
        sensitivity: SensitivityTier,
        payment_score: float,
        churn_risk: str,
        pi_history: List[PriceIncreaseRecord],
    ) -> List[str]:
        tactics = []

        if sensitivity == SensitivityTier.HIGHLY_SENSITIVE:
            tactics.append("Lead with market context, not margin story — they care about supply security")
            tactics.append("Offer extended payment terms as alternative to price concession")
            if payment_score < 80:
                tactics.append("Propose: no price increase + improved payment terms in exchange for volume commitment")
        elif sensitivity == SensitivityTier.MODERATELY_SENSITIVE:
            tactics.append("Frame increase around commodity/market indices — be transparent")
            tactics.append("Offer 'loyalty discount' of 0.5-1% for 2-year contract commitment")
        else:
            tactics.append("You have pricing power — hold firm on increase")
            tactics.append("Consider using this negotiation to renegotiate other terms (payment, exclusivity)")

        if churn_risk == "HIGH":
            tactics.append("CRITICAL: Address underlying issues first — price is not the real problem")
            tactics.append("Consider a relationship review before pushing price increase")

        if pi_history and len(pi_history) >= 2:
            last = pi_history[-1]
            tactics.append(f"Historical precedent: {last.accepted_increase_pct:.1f}% increase accepted in {last.year} — use this as anchor")

        if payment_score < 75:
            tactics.append("Tie price increase to payment terms improvement: 'We can offer X% if you move tonet-30'")

        if len(tactics) < 3:
            tactics.append("Ensure your BATNA is documented before entering negotiation")

        return tactics[:5]  # cap at 5 tactics

    def _assess_competitive_threat(self, snapshots: List[RelationshipSnapshot]) -> str:
        if len(snapshots) >= 5:
            recent = snapshots[-3:]
            if any(s.revenue_or_spend < snapshots[-4].revenue_or_spend * 0.8 for s in recent):
                return "Evidence of volume reduction — possible competitive switching"
        return "No strong competitive threat indicators"

    def _assess_data_quality(self, year_keys: List[int]) -> str:
        span = year_keys[-1] - year_keys[0] + 1 if year_keys else 0
        if span >= 5:
            return "HIGH"
        elif span >= 2:
            return "MEDIUM"
        return "LOW"

    def _generate_bottom_line(
        self,
        entity_type: EntityType,
        neg_type: NegotiationType,
        rec_increase: float,
        churn_risk: str,
        psi: float,
        clv_tier: str,
    ) -> str:
        if churn_risk == "HIGH":
            return (f"DO NOT push for price increase. This relationship is fragile. "
                    f"Consider what is driving churn risk before discussing pricing.")
        if clv_tier == "PLATINUM":
            return (f"PLATINUM account — protect the relationship. Target {rec_increase:.1f}% increase "
                    f"but accept up to {rec_increase * 0.8:.1f}% if needed. {clv_tier} value justifies accommodation.")
        if psi < 4.0:
            return (f"Highly price-sensitive customer. Lead with value, not price. "
                    f"Expected acceptance range: {rec_increase * 0.5:.1f}%-{rec_increase:.1f}%.")
        return (f"Target {rec_increase:.1f}% price increase. Accept {rec_increase * 0.7:.1f}% minimum. "
                f"Use competitive market data to support position.")

    def _empty_brief(
        self, entity_id, entity_name, entity_type, negotiation_type,
    ) -> NegotiationBrief:
        return NegotiationBrief(
            entity_id=entity_id, entity_name=entity_name,
            entity_type=entity_type, negotiation_type=negotiation_type,
            relationship_years=0, first_order_date="N/A", last_order_date="N/A",
            snapshots=[], price_increase_history=[],
            price_sensitivity_index=5.0, sensitivity_tier=SensitivityTier.MODERATELY_SENSITIVE,
            payment_reliability_score=75.0, clv_tier="STANDARD",
            total_revenue_20yr=0.0, avg_annual_revenue=0.0,
            current_year_revenue=0.0, revenue_trend_5yr=0.0,
            total_discounts_20yr=0.0, avg_discount_pct=0.0,
            churn_risk="UNKNOWN", churn_evidence=["Insufficient data"],
            concentration_risk="UNKNOWN", competitive_threat="Cannot assess",
            batna="Insufficient data to assess", batna_strength=5.0,
            recommended_increase_pct=3.0, max_acceptable_increase_pct=2.0,
            recommended_discount=0.0, top_tactics=["Gather more data before negotiating"],
            bottom_line="Not enough historical data to generate a reliable brief. Recommend 2+ years of SAP data before proceeding.",
            generated_at=datetime.now().isoformat(),
            data_quality="LOW",
        )


# ============================================================================
# Text Formatter — turns NegotiationBrief into readable output
# ============================================================================

class NegotiationBriefFormatter:
    """Formats a NegotiationBrief as readable text for the negotiation prep meeting."""

    def format_text(self, brief: NegotiationBrief) -> str:
        lines = []
        div = "=" * 70

        lines.append(div)
        lines.append(f"  NEGOTIATION BRIEF")
        lines.append(f"  {brief.entity_type.value.upper()}: {brief.entity_name} ({brief.entity_id})")
        lines.append(f"  Type: {brief.negotiation_type.value.replace('_', ' ').title()}")
        lines.append(f"  Generated: {brief.generated_at[:19]}")
        lines.append(div)

        # Key stats bar
        lines.append(f"\n{'─' * 70}")
        lines.append(f"  RELATIONSHIP AT A GLANCE")
        lines.append(f"{'─' * 70}")
        lines.append(f"  {brief.relationship_years} years | "
                    f"Last order: {brief.last_order_date} | "
                    f"CLV Tier: {brief.clv_tier}")
        lines.append(f"  Total 20yr value: ${brief.total_revenue_20yr:,.0f} | "
                    f"Avg annual: ${brief.avg_annual_revenue:,.0f}")
        lines.append(f"  PSI: {brief.price_sensitivity_index:.1f}/10 "
                    f"({brief.sensitivity_tier.value.replace('_', ' ')}) | "
                    f"Payment score: {brief.payment_reliability_score:.0f}/100")
        lines.append(f"  Churn risk: {brief.churn_risk} | "
                    f"Revenue trend (5yr): {'+' if brief.revenue_trend_5yr > 0 else ''}{brief.revenue_trend_5yr}%")
        lines.append(f"  Data quality: {brief.data_quality} | BATNA strength: {brief.batna_strength:.0f}/10")

        # Price increase history
        if brief.price_increase_history:
            lines.append(f"\n{'─' * 70}")
            lines.append(f"  PRICE INCREASE HISTORY")
            lines.append(f"{'─' * 70}")
            for pi in brief.price_increase_history[-5:]:
                outcome_icon = {"accepted": "✅", "renegotiated": "⚠️", "rejected": "❌", "churned": "💀"}.get(pi.outcome, "❓")
                lines.append(f"  {pi.year}: {'+' if pi.proposed_increase_pct > 0 else ''}"
                           f"{pi.proposed_increase_pct:.1f}% → {pi.outcome} {outcome_icon}")

        # Revenue trend
        if brief.snapshots:
            lines.append(f"\n{'─' * 70}")
            lines.append(f"  ANNUAL REVENUE TREND")
            lines.append(f"{'─' * 70}")
            for s in brief.snapshots[-6:]:
                bar_len = min(int(s.revenue_or_spend / max(brief.avg_annual_revenue, 1) * 10), 20)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                lines.append(f"  {s.year}  {bar}  ${s.revenue_or_spend:>12,.0f}  "
                           f"{s.order_count:>3} orders  disc={s.discount_pct:.1f}%")

        # Churn risk
        lines.append(f"\n{'─' * 70}")
        lines.append(f"  CHURN RISK: {brief.churn_risk}")
        lines.append(f"{'─' * 70}")
        for e in brief.churn_evidence[:4]:
            lines.append(f"  • {e}")

        # BATNA
        lines.append(f"\n{'─' * 70}")
        lines.append(f"  BATNA (Best Alternative)")
        lines.append(f"{'─' * 70}")
        lines.append(f"  {brief.batna}")

        # Recommendation
        lines.append(f"\n{'─' * 70}")
        lines.append(f"  RECOMMENDATION")
        lines.append(f"{'─' * 70}")
        if brief.negotiation_type == NegotiationType.PRICE_INCREASE:
            lines.append(f"  Target increase: +{brief.recommended_increase_pct:.1f}%")
            lines.append(f"  Accept minimum: +{brief.max_acceptable_increase_pct:.1f}%")
            if brief.recommended_discount > 0:
                lines.append(f"  Recommended counter-offer: {brief.recommended_discount:.1f}% loyalty discount")
        lines.append(f"\n  BOTTOM LINE:")
        lines.append(f"  {brief.bottom_line}")

        # Tactics
        lines.append(f"\n{'─' * 70}")
        lines.append(f"  TOP TACTICS (in order)")
        lines.append(f"{'─' * 70}")
        for i, t in enumerate(brief.top_tactics, 1):
            lines.append(f"  {i}. {t}")

        lines.append(f"\n{div}")
        return "\n".join(lines)

    def format_structured(self, brief: NegotiationBrief) -> Dict[str, Any]:
        """Return as a structured dict (for JSON/API responses)."""
        return {
            "header": {
                "entity_id": brief.entity_id,
                "entity_name": brief.entity_name,
                "entity_type": brief.entity_type.value,
                "negotiation_type": brief.negotiation_type.value,
                "relationship_years": brief.relationship_years,
                "data_quality": brief.data_quality,
                "generated_at": brief.generated_at,
            },
            "key_metrics": {
                "price_sensitivity_index": brief.price_sensitivity_index,
                "sensitivity_tier": brief.sensitivity_tier.value,
                "payment_reliability_score": brief.payment_reliability_score,
                "clv_tier": brief.clv_tier,
                "churn_risk": brief.churn_risk,
                "batna_strength": brief.batna_strength,
                "revenue_trend_5yr_pct": brief.revenue_trend_5yr,
            },
            "financials": {
                "total_20yr_value": round(brief.total_revenue_20yr, 2),
                "avg_annual_value": round(brief.avg_annual_revenue, 2),
                "current_year_value": round(brief.current_year_revenue, 2),
                "total_discounts_20yr": round(brief.total_discounts_20yr, 2),
                "avg_discount_pct": round(brief.avg_discount_pct, 2),
            },
            "recommendation": {
                "target_increase_pct": brief.recommended_increase_pct,
                "accept_minimum_pct": brief.max_acceptable_increase_pct,
                "recommended_discount_pct": brief.recommended_discount,
                "bottom_line": brief.bottom_line,
            },
            "tactics": brief.top_tactics,
            "batna": brief.batna,
            "churn_evidence": brief.churn_evidence,
            "price_increase_history": [
                {"year": pi.year, "proposed_pct": pi.proposed_increase_pct,
                 "accepted_pct": pi.accepted_increase_pct, "outcome": pi.outcome}
                for pi in brief.price_increase_history
            ],
            "annual_snapshots": [
                {"year": s.year, "revenue": round(s.revenue_or_spend, 2),
                 "orders": s.order_count, "discount_pct": round(s.discount_pct, 2),
                 "payment_days": round(s.payment_days_actual, 1),
                 "payment_score": round(s.payment_score, 1)}
                for s in brief.snapshots
            ],
        }
