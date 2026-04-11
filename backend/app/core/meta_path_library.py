"""
meta_path_library.py — Pillar 5: Graph RAG — Meta-Path Library

Pre-computed, semantically meaningful JOIN path templates for common SAP
business scenarios. These bypass dynamic graph traversal for known query
patterns, improving speed, reliability, and explainability.

Each meta-path encodes:
  - Business intent (what the query is trying to answer)
  - All valid table sequences that satisfy the intent
  - Required + optional SQL filters
  - A parameterized SQL template (plug in table aliases, filters)
  - Example natural-language queries that trigger this path

Usage:
    from .meta_path_library import meta_path_library
    result = meta_path_library.match("vendor who supplied material to plant")
    if result:
        print(result["sql_template"])  # pre-assembled JOIN SQL
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import re


# ─── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class PathVariant:
    """
    A single JOIN path variant within a meta-path.
    Multiple variants exist because SAP FK graphs are dense —
    the same business question can be answered via different table sequences.
    """
    tables: List[str]                          # Ordered list of tables in JOIN
    join_conditions: List[Tuple[str, str, str]]  # (from_table, to_table, condition)
    cardinality_notes: str = ""                 # e.g., "1 info-record per vendor-material"
    score: float = 1.0                          # Preference score (higher = prefer first)
    bloom_filter: List[str] = field(default_factory=list)  # keywords that uniquely tag this variant

    def __post_init__(self):
        # Normalize tables to uppercase
        self.tables = [t.upper() for t in self.tables]
        self.join_conditions = [
            (a.upper(), b.upper(), cond) for a, b, cond in self.join_conditions
        ]


@dataclass
class MetaPath:
    """
    A semantically named, pre-computed JOIN path for a common SAP business scenario.
    """
    id: str
    name: str
    business_description: str
    domain: str
    module: str
    tags: List[str]                    # For keyword/embedding search
    variants: List[PathVariant]        # Multiple valid JOIN sequences (sorted by score desc)
    required_filters: List[str]        # Always-needed WHERE components
    optional_filters: List[str]         # May be added depending on user query
    sql_template: str                  # Parameterized SELECT template
    select_columns: Dict[str, List[str]]  # table → [columns] for SELECT clause
    group_by_columns: List[str] = field(default_factory=list)
    example_queries: List[str] = field(default_factory=list)
    confidence_boost: float = 0.2       # Add to base confidence when matched
    row_count_warning: str = ""         # e.g., "BSEG without BUKRS = all company codes"

    def best_variant(self) -> PathVariant:
        return max(self.variants, key=lambda v: v.score)


# ─── Meta-Path Definitions ────────────────────────────────────────────────────

SAP_META_PATHS: List[MetaPath] = []

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN 1 — VENDOR / BUSINESS PARTNER
# ═══════════════════════════════════════════════════════════════════════════════

SAP_META_PATHS.append(MetaPath(
    id="vendor_master_basic",
    name="Vendor Master Overview",
    business_description=(
        "Returns core vendor master data: name, address, contact, tax numbers, "
        "company-code assignments, and bank details. Foundation for any vendor query."
    ),
    domain="business_partner",
    module="BP",
    tags=["vendor", "supplier", "vendor master", "LFA1", "address", "bank details",
          "tax number", "company code vendor", "vendor overview"],
    variants=[
        PathVariant(
            tables=["LFA1", "LFB1", "LFBK", "ADRC"],
            join_conditions=[
                ("LFA1", "LFB1", "LFA1.LIFNR = LFB1.LIFNR"),
                ("LFA1", "LFBK", "LFA1.LIFNR = LFBK.LIFNR"),
                ("LFA1", "ADRC", "LFA1.ADRNR = ADRC.ADDRNUMBER"),
            ],
            cardinality_notes="1 LFA1 per vendor; 1 LFBK per bank account",
            score=1.0,
            bloom_filter=["vendor", "bank", "address", "tax"],
        ),
        PathVariant(
            tables=["BUT000", "LFA1", "LFB1", "BUT020", "ADRC"],
            join_conditions=[
                ("BUT000", "LFA1", "BUT000.PARTNER = LFA1.LIFNR"),
                ("BUT000", "LFB1", "BUT000.PARTNER = LFB1.LIFNR"),
                ("BUT000", "BUT020", "BUT000.PARTNER = BUT020.PARTNER"),
                ("BUT020", "ADRC", "BUT020.ADDRNUMBER = ADRC.ADDRNUMBER"),
            ],
            cardinality_notes="CVI link: BP Central → Vendor. Adds BP relationship layer.",
            score=0.8,
            bloom_filter=["business partner", "BP relationship"],
        ),
    ],
    required_filters=["LFA1.MANDT = :P_MANDT"],
    optional_filters=["LFA1.LIFNR = :LIFNR", "LFB1.BUKRS = :BUKRS", "LFA1.KTOKK = :VENDOR_GROUP"],
    sql_template="""
SELECT
    LFA1.LIFNR     AS vendor_code,
    LFA1.NAME1     AS vendor_name,
    LFA1.STRAS     AS street_address,
    LFA1.ORT01     AS city,
    LFA1.LAND1     AS country,
    LFA1.STCD1     AS tax_number_1,
    LFA1.STCD2     AS tax_number_2,
    LFB1.BUKRS     AS company_code,
    LFB1.AKONT     AS reconciliation_account,
    LFBK.BANKN     AS bank_account,
    LFBK.BANKL     AS bank_key,
    ADRC.TEL_NUMBER,
    ADRC.SMTP_ADDR AS email
FROM LFA1
LEFT JOIN LFB1 ON LFA1.LIFNR = LFB1.LIFNR
LEFT JOIN LFBK ON LFA1.LIFNR = LFBK.LIFNR
LEFT JOIN ADRC ON LFA1.ADRNR = ADRC.ADDRNUMBER
WHERE {filters}
ORDER BY LFA1.NAME1
""",
    select_columns={
        "LFA1": ["LIFNR", "NAME1", "STRAS", "ORT01", "LAND1", "STCD1", "STCD2", "KTOKK"],
        "LFB1": ["BUKRS", "AKONT", "ZAHLS"],
        "LFBK": ["BANKN", "BANKL", "BKONT"],
        "ADRC": ["TEL_NUMBER", "SMTP_ADDR"],
        "BUT000": ["PARTNER", "BU_GROUP"],
        "BUT020": ["ADDRNUMBER", "PERSNUMBER"],
    },
    example_queries=[
        "show me vendor master data for vendor 1000",
        "vendor overview with address and bank details",
        "list all vendors with their tax numbers",
        "vendor company code assignment",
        "what is the reconciliation account for vendor?",
    ],
    confidence_boost=0.25,
    row_count_warning="LFA1 is replicated across all company codes — always filter LIFNR or BUKRS",
))

SAP_META_PATHS.append(MetaPath(
    id="vendor_material_relationship",
    name="Vendor-Material Sourcing Relationship",
    business_description=(
        "Maps the relationship between a vendor and the materials they supply or "
        "can supply. Covers purchasing info records (source list, conditions, origin), "
        "vendor evaluations, and material-qualified vendors. Core of supplier scouting."
    ),
    domain="purchasing",
    module="MM-PUR",
    tags=["vendor material", "info record", "source list", "purchasing info record",
          "EINA", "EINE", "EORD", "LFBW", "vendor evaluation", "material qualification",
          "vendor can supply", "supplying vendor", "sourcing"],
    variants=[
        PathVariant(
            tables=["LFA1", "EINA", "EINE", "MARA", "MAKT"],
            join_conditions=[
                ("LFA1", "EINA", "LFA1.LIFNR = EINA.LIFNR"),
                ("EINA", "EINE", "EINA.INFNR = EINE.INFNR AND EINA.LIFNR = EINE.LIFNR AND EINA.EKORG = EINE.EKORG"),
                ("EINA", "MARA", "EINA.MATNR = MARA.MATNR"),
                ("MARA", "MAKT", "MARA.MATNR = MAKT.MATNR AND MAKT.SPRAS = 'E'"),
            ],
            cardinality_notes="1 EINA per vendor-material-org combination; EINE is org-specific",
            score=1.0,
            bloom_filter=["info record", "purchasing conditions", "net price", "effective price"],
        ),
        PathVariant(
            tables=["LFA1", "EORD", "MARA", "MARC", "MAKT"],
            join_conditions=[
                ("LFA1", "EORD", "LFA1.LIFNR = EORD.LIFNR"),
                ("EORD", "MARA", "EORD.MATNR = MARA.MATNR"),
                ("EORD", "MARC", "EORD.MATNR = MARC.MATNR AND EORD.WERKS = MARC.WERKS"),
                ("MARA", "MAKT", "MARA.MATNR = MAKT.MATNR AND MAKT.SPRAS = 'E'"),
            ],
            cardinality_notes="EORD is plant-specific source list — 1 row per vendor-material-plant",
            score=0.9,
            bloom_filter=["source list", "fixed source", "plant specific", " Automatic PO"],
        ),
        PathVariant(
            tables=["LFA1", "LFBW", "MARA", "MARC", "T001W"],
            join_conditions=[
                ("LFA1", "LFBW", "LFA1.LIFNR = LFBW.LIFNR"),
                ("LFBW", "MARA", "LFBW.MATNR = MARA.MATNR"),
                ("LFBW", "MARC", "LFBW.MATNR = MARC.MATNR AND LFBW.WERKS = MARC.WERKS"),
                ("MARC", "T001W", "MARC.WERKS = T001W.WERKS"),
            ],
            cardinality_notes="LFBW: Vendor evaluation grades per material per plant",
            score=0.6,
            bloom_filter=["vendor evaluation", "quality score", "delivered quality", "price score"],
        ),
    ],
    required_filters=["EINA.MANDT = :P_MANDT"],
    optional_filters=[
        "EINA.LIFNR = :LIFNR",
        "EINA.MATNR = :MATNR",
        "EINE.EKORG = :EKORG",
        "EINA.ESOKZ = :INFO_REC_TYPE",  # Standard / Subcontracting / Pipeline
        "MARA.MTART = :MATERIAL_TYPE",
        "EORD.WERKS = :WERKS",
        "EORD.LFDAT > :AVAIL_FROM",  # source list validity
    ],
    sql_template="""
SELECT
    LFA1.LIFNR         AS vendor_code,
    LFA1.NAME1         AS vendor_name,
    EINA.INFNR         AS info_record_number,
    EINA.MATNR         AS material_number,
    MAKT.MAKTX         AS material_description,
    MARA.MTART         AS material_type,
    EINE.EKORG         AS purchasing_org,
    EINE.ESOKZ         AS info_record_type,
    EINE.NETPR         AS net_price,
    EINE.PEINH         AS price_unit,
    EINE.WAERS         AS currency,
    EINE.DATAB         AS effective_from,
    EINE.DATBI         AS effective_to,
    EINE.MWSKZ         AS tax_code,
    EORD.WERKS         AS plant,
    EORD.LIFRE         AS fixed_vendor,
    T001W.NAME1        AS plant_name,
    LFBW.DZEZT         AS evaluation_score
FROM EINA
JOIN LFA1 ON EINA.LIFNR = LFA1.LIFNR
LEFT JOIN EINE ON EINA.INFNR = EINE.INFNR
LEFT JOIN EORD ON EINA.LIFNR = EORD.LIFNR AND EINA.MATNR = EORD.MATNR
LEFT JOIN MARA ON EINA.MATNR = MARA.MATNR
LEFT JOIN MAKT ON MARA.MATNR = MAKT.MATNR AND MAKT.SPRAS = 'E'
LEFT JOIN MARC ON EORD.MATNR = MARC.MATNR AND EORD.WERKS = MARC.WERKS
LEFT JOIN T001W ON MARC.WERKS = T001W.WERKS
LEFT JOIN LFBW ON LFA1.LIFNR = LFBW.LIFNR AND EINA.MATNR = LFBW.MATNR AND MARC.WERKS = LFBW.WERKS
WHERE {filters}
ORDER BY LFA1.NAME1, EINA.MATNR
""",
    select_columns={
        "EINA": ["INFNR", "LIFNR", "MATNR", "ESOKZ", "ERNAM", "ERDAT"],
        "EINE": ["EKORG", "ESOKZ", "NETPR", "PEINH", "WAERS", "DATAB", "DATBI", "MWSKZ"],
        "LFA1": ["LIFNR", "NAME1", "KTOKK"],
        "EORD": ["WERKS", "LIFRE", "LFDAT"],
        "MARA": ["MATNR", "MTART", "MATKL"],
        "MAKT": ["MAKTX"],
        "T001W": ["NAME1"],
        "LFBW": ["DZEZT", "DZEER"],
    },
    example_queries=[
        "show me vendors who supply material 100-100",
        "purchasing info records for vendor 3000",
        "source list for material at plant 1000",
        "which vendors are qualified for material X at plant Y",
        "vendor-material purchasing conditions",
        "last purchase price for vendor 1000 material 200-500",
        "what is the net price in info record for vendor/material/org",
        "vendor evaluation scores for material",
        "supplying vendors for material",
    ],
    confidence_boost=0.3,
    row_count_warning="EINA is huge (all info records) — always filter LIFNR or MATNR or EKORG",
))

SAP_META_PATHS.append(MetaPath(
    id="vendor_financial_exposure",
    name="Vendor Financial Exposure (Payables + On-Order)",
    business_description=(
        "Complete financial picture of a vendor: open invoices (BSIK), cleared items (BSAK), "
        "on-order quantities via scheduling agreements (EKES), open purchase orders (EKPO), "
        "and info records (last agreed price). Used for payment risk, cash forecasting, "
        "and vendor resilience assessment."
    ),
    domain="financial_accounting",
    module="FI",
    tags=["vendor open items", "vendor cleared items", "accounts payable", "vendor exposure",
          "payables aging", "on order", "open PO", "scheduling agreement", "vendor balance",
          "payment block", "dunning area", "BSIK", "BSAK", "payment terms", "LFB1"],
    variants=[
        PathVariant(
            tables=["LFA1", "LFB1", "T001", "BSIK", "BSAK"],
            join_conditions=[
                ("LFA1", "LFB1", "LFA1.LIFNR = LFB1.LIFNR"),
                ("LFA1", "BSIK", "LFA1.LIFNR = BSIK.LIFNR"),
                ("BSIK", "T001", "BSIK.BUKRS = T001.BUKRS"),
                ("LFA1", "BSAK", "LFA1.LIFNR = BSAK.LIFNR"),
            ],
            cardinality_notes="BSIK/BSAK are secondary indexes — 1 row per line item",
            score=1.0,
            bloom_filter=["open items", "cleared items", "invoice", "payment", "dunning"],
        ),
        PathVariant(
            tables=["LFA1", "EKKO", "EKPO", "EKES"],
            join_conditions=[
                ("LFA1", "EKKO", "LFA1.LIFNR = EKKO.LIFNR"),
                ("EKKO", "EKPO", "EKKO.EBELN = EKPO.EBELN"),
                ("EKKO", "EKES", "EKKO.EBELN = EKES.EBELN"),
            ],
            cardinality_notes="EKES = scheduling agreement confirmations (on-order quantities)",
            score=0.9,
            bloom_filter=["on order", "schedule agreement", "delivered quantity", "confirmed quantity", "open PO"],
        ),
        PathVariant(
            tables=["LFA1", "LFB1", "BSIK", "EKKO", "EKPO"],
            join_conditions=[
                ("LFA1", "LFB1", "LFA1.LIFNR = LFB1.LIFNR"),
                ("LFA1", "BSIK", "LFA1.LIFNR = BSIK.LIFNR"),
                ("LFA1", "EKKO", "LFA1.LIFNR = EKKO.LIFNR"),
                ("EKKO", "EKPO", "EKKO.EBELN = EKPO.EBELN"),
            ],
            cardinality_notes="Combines payables (FI) + on-order (MM) for total vendor exposure",
            score=0.85,
            bloom_filter=["total exposure", "liability", "outstanding", "commitment"],
        ),
    ],
    required_filters=["LFA1.MANDT = :P_MANDT"],
    optional_filters=[
        "LFA1.LIFNR = :LIFNR",
        "BSIK.BUKRS = :BUKRS",
        "BSIK.ZAHLS = :PAYMENT_TERMS",
        "BSIK.ZINKZ = :DUNNING_BLOCK",
        "EKKO.BSART = :PO_TYPE",
        "EKKO.EKGRP = :PURCHASING_GROUP",
        "EKPO.PO_REL_CODE = 'X'",  # Released only
    ],
    sql_template="""
SELECT
    LFA1.LIFNR         AS vendor_code,
    LFA1.NAME1         AS vendor_name,
    LFB1.ZAHLS         AS payment_terms_key,
    LFB1.ZAHLS_TEXT    AS payment_terms_description,
    -- Open items (invoices posted, not yet paid)
    SUM(BSIK.DMBTR)    AS open_items_amount,
    COUNT(BSIK.BELNR)  AS open_invoice_count,
    -- Cleared items (last 90 days)
    SUM(BSAK.DMBTR)    AS cleared_items_amount,
    -- On-order via scheduling agreements
    SUM(EKES.WAMNG)    AS confirmed_on_order_qty,
    SUM(EKES.BAMNG)    AS delivered_qty,
    -- Open PO value
    SUM(EKPO.NETWR)    AS open_po_value,
    COUNT(DISTINCT EKKO.EBELN) AS open_po_count
FROM LFA1
LEFT JOIN LFB1 ON LFA1.LIFNR = LFB1.LIFNR AND LFB1.BUKRS = :BUKRS
LEFT JOIN BSIK ON LFA1.LIFNR = BSIK.LIFNR AND BSIK.BUKRS = :BUKRS
LEFT JOIN BSAK ON LFA1.LIFNR = BSAK.LIFNR AND BSAK.BUKRS = :BUKRS AND BSAK.AUGDT >= :DATE_90DAYS
LEFT JOIN EKKO ON LFA1.LIFNR = EKKO.LIFNR AND EKKO.BSART IN ('MK', 'WK')
LEFT JOIN EKPO ON EKKO.EBELN = EKPO.EBELN AND EKPO.ELIKZ = ''
LEFT JOIN EKES ON EKKO.EBELN = EKES.EBELN AND EKPO.EBELP = EKES.EBELP
WHERE LFA1.LIFNR = :LIFNR
GROUP BY LFA1.LIFNR, LFA1.NAME1, LFB1.ZAHLS, LFB1.ZAHLS_TEXT
""",
    select_columns={
        "LFA1": ["LIFNR", "NAME1"],
        "LFB1": ["ZAHLS", "ZAHLS_TEXT", "ZINTR"],
        "BSIK": ["BELNR", "BUZEI", "BUKRS", "DMBTR", "WAERS", "ZBD1T", "ZBD2T", "ZBD3T"],
        "BSAK": ["BELNR", "DMBTR", "AUGDT"],
        "EKKO": ["EBELN", "BSART", "BEDAT"],
        "EKPO": ["EBELP", "NETWR", "WEMNG", "MENGE"],
        "EKES": ["EBTYP", "WAMNG", "BAMNG"],
    },
    example_queries=[
        "what is the open invoice amount for vendor 1000",
        "vendor payment terms and dunning area",
        "total vendor exposure including on-order",
        "vendor accounts payable aging",
        "open items for vendor with payment block",
        "vendor cleared items in last 90 days",
        "scheduling agreement confirmed quantities",
        "vendor payment risk assessment",
    ],
    confidence_boost=0.25,
    row_count_warning="BSIK without BUKRS = all company codes; always add BUKRS. BSEG-level granularity available via BSEG aggregation.",
))

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN 2 — PROCUREMENT (P2P)
# ═══════════════════════════════════════════════════════════════════════════════

SAP_META_PATHS.append(MetaPath(
    id="procure_to_pay",
    name="Procure-to-Pay (P2P) Document Chain",
    business_description=(
        "Full procurement cycle: vendor selection → purchase order → goods receipt (GR) → "
        "invoice verification (MM invoices) → accounting document (FI). Links MM-PUR "
        "documents to FI line items. Used for auditing, three-way match, and spend analytics."
    ),
    domain="purchasing",
    module="MM-PUR",
    tags=["purchase order", "goods receipt", "invoice verification", "GR/IR",
          "procure to pay", "P2P", "EKKO", "EKPO", "MKPF", "MSEG", "BKPF", "BSEG",
          "three way match", "驻", "MIRO", "lifecycle", "procurement analytics"],
    variants=[
        PathVariant(
            tables=["LFA1", "EKKO", "EKPO", "MSEG", "MKPF", "BKPF", "BSEG"],
            join_conditions=[
                ("LFA1", "EKKO", "LFA1.LIFNR = EKKO.LIFNR"),
                ("EKKO", "EKPO", "EKKO.EBELN = EKPO.EBELN"),
                ("EKPO", "MSEG", "EKPO.EBELN = MSEG.EBELN AND EKPO.EBELP = MSEG.EBELP AND MSEG.BWART IN ('101', '102')"),
                ("MSEG", "MKPF", "MSEG.MBLNR = MKPF.MBLNR AND MSEG.MJAHR = MKPF.MJAHR"),
                ("MSEG", "BKPF", "MSEG.BUKRS = BKPF.BUKRS AND MSEG.KUNNR = BKPF.BELNR AND MSEG.GJAHR = BKPF.GJAHR"),
                ("BKPF", "BSEG", "BKPF.BELNR = BSEG.BELNR AND BKPF.GJAHR = BSEG.GJAHR AND BKPF.BUKRS = BSEG.BUKRS"),
            ],
            cardinality_notes="MSEG BWART 101=GR, 102=Reversal. GR/IR clearing via MSEG-KUNNR=BELNR.",
            score=1.0,
            bloom_filter=["goods receipt", "invoice", "GR/IR", "MIRO", "lifecycle"],
        ),
        PathVariant(
            tables=["LFA1", "EKKO", "EKPO", "EBAN", "RKPF"],
            join_conditions=[
                ("LFA1", "EKKO", "LFA1.LIFNR = EKKO.LIFNR"),
                ("EKKO", "EKPO", "EKKO.EBELN = EKPO.EBELN"),
                ("EKPO", "EBAN", "EKPO.BANFN = EBAN.BANFN AND EKPO.BNFPO = EBAN.BNFPO"),
                ("EBAN", "RKPF", "EBAN.RSNUM = RKPF.RSNUM"),
            ],
            cardinality_notes="Via PR (EBAN) and reservation (RKPF) — shows planned vs. ordered",
            score=0.7,
            bloom_filter=["purchase requisition", "PR", "reservation", "planned"],
        ),
    ],
    required_filters=["EKKO.MANDT = :P_MANDT"],
    optional_filters=[
        "EKKO.LIFNR = :LIFNR",
        "EKKO.BEDAT BETWEEN :DATE_FROM AND :DATE_TO",
        "EKKO.BSART = :PO_TYPE",
        "EKKO.EKGRP = :PURCHASING_GROUP",
        "EKPO.WERKS = :WERKS",
        "MSEG.BWART IN ('101', '102')",
        "BSEG.ZUONR = :PO_NUMBER",  # PO number in assignment field
        "BKPF.BUKRS = :BUKRS",
    ],
    sql_template="""
SELECT
    EKKO.EBELN         AS po_number,
    EKKO.BEDAT         AS po_date,
    EKKO.BSART         AS po_type,
    LFA1.LIFNR         AS vendor_code,
    LFA1.NAME1         AS vendor_name,
    EKPO.EBELP         AS po_item,
    EKPO.MATNR         AS material,
    EKPO.TXZ01         AS short_text,
    EKPO.MENGE         AS po_quantity,
    EKPO.NETWR         AS po_value,
    EKPO.WAERS         AS currency,
    MSEG.BWART         AS movement_type,
    MSEG.BUDAT         AS posting_date,
    MSEG.MBLNR         AS material_doc,
    MSEG.MENGE         AS gr_quantity,
    MKPF.CPUDT         AS gr_doc_date,
    BKPF.BELNR         AS accounting_doc,
    BKPF.GJAHR         AS fiscal_year,
    BSEG.DMBTR         AS invoice_amount,
    BSEG.HKONT         AS gl_account,
    SKA1.SAKNR         AS gl_account_code,
    SKA1.KTOPL         AS chart_of_accounts
FROM EKKO
JOIN LFA1 ON EKKO.LIFNR = LFA1.LIFNR
JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
LEFT JOIN MSEG ON EKKO.EBELN = MSEG.EBELN AND EKPO.EBELP = MSEG.EBELP AND MSEG.BWART IN ('101', '102')
LEFT JOIN MKPF ON MSEG.MBLNR = MKPF.MBLNR AND MSEG.MJAHR = MKPF.MJAHR
LEFT JOIN MSEG AS MSEG_INV ON MSEG.KUNNR = MSEG_INV.KUNNR AND MSEG.KUNNR = BKPF.BELNR
LEFT JOIN BKPF ON MSEG.KUNNR = BKPF.BELNR AND MSEG.GJAHR = BKPF.GJAHR
LEFT JOIN BSEG ON BKPF.BELNR = BSEG.BELNR AND BKPF.GJAHR = BSEG.GJAHR AND BKPF.BUKRS = BSEG.BUKRS
LEFT JOIN SKA1 ON BSEG.HKONT = SKA1.SAKNR
WHERE {filters}
ORDER BY EKKO.BEDAT DESC, EKKO.EBELN, EKPO.EBELP
""",
    select_columns={
        "EKKO": ["EBELN", "BEDAT", "BSART", "EKGRP", "WAERS"],
        "EKPO": ["EBELP", "MATNR", "TXZ01", "MENGE", "NETWR", "ELIKZ"],
        "LFA1": ["LIFNR", "NAME1"],
        "MSEG": ["MBLNR", "MJAHR", "BWART", "BUDAT", "MENGE", "DMBTR"],
        "MKPF": ["MBLNR", "MJAHR", "CPUDT"],
        "BKPF": ["BELNR", "GJAHR", "BUKRS", "BLDAT"],
        "BSEG": ["BUZEI", "HKONT", "DMBTR", "WAERS", "ZUONR"],
        "SKA1": ["SAKNR", "KTOPL", "KTOKS"],
    },
    group_by_columns=["EKKO.EBELN", "EKPO.EBELP"],
    example_queries=[
        "show me P2P cycle for vendor 1000 last month",
        "purchase orders with goods receipt and invoice",
        "three way match for PO 4500012345",
        "GR/IR clearing account balance for vendor",
        "procurement analytics by vendor and material",
        "procurement spending by purchasing group",
        "all open POs with schedule lines for vendor",
        "scheduling agreement delivery plan",
    ],
    confidence_boost=0.3,
    row_count_warning="MSEG is enormous (all material movements) — always filter EKKO.EBELN or MSEG.BUDAT range. BSEG without BUKRS returns all company codes.",
))

SAP_META_PATHS.append(MetaPath(
    id="open_purchase_orders",
    name="Open Purchase Orders",
    business_description=(
        "All unfulfilled purchase orders: ordered but not yet delivered (WEMNG < MENGE), "
        "or delivered but not yet invoiced. Covers PO headers, items, schedule lines, "
        "confirmations, and account assignments."
    ),
    domain="purchasing",
    module="MM-PUR",
    tags=["open PO", "open purchase order", "undelivered", "schedule line",
          "confirmed quantity", "delivery date", "EKPO", "EKKO", "EKES", "VBEP",
          "open schedule", "purchase order status", "open quantity"],
    variants=[
        PathVariant(
            tables=["EKKO", "EKPO", "EKKO_REF", "LFA1", "MARA"],
            join_conditions=[
                ("EKKO", "EKPO", "EKKO.EBELN = EKPO.EBELN"),
                ("EKKO", "LFA1", "EKKO.LIFNR = LFA1.LIFNR"),
                ("EKPO", "MARA", "EKPO.MATNR = MARA.MATNR"),
            ],
            cardinality_notes="Open if EKPO.WEMNG < EKPO.MENGE (goods receipt expected)",
            score=1.0,
            bloom_filter=["open po", "undelivered", "purchase order status"],
        ),
        PathVariant(
            tables=["EKKO", "EKPO", "EKES", "LFA1", "EINA"],
            join_conditions=[
                ("EKKO", "EKPO", "EKKO.EBELN = EKPO.EBELN"),
                ("EKKO", "EKES", "EKKO.EBELN = EKES.EBELN AND EKPO.EBELP = EKES.EBELP"),
                ("EKKO", "LFA1", "EKKO.LIFNR = LFA1.LIFNR"),
                ("EKPO", "EINA", "EKPO.INFNR = EINA.INFNR"),
            ],
            cardinality_notes="EKES = confirmed quantities via scheduling agreement",
            score=0.9,
            bloom_filter=["schedule agreement", "confirmed", "delivered quantity", "EKES"],
        ),
    ],
    required_filters=["EKKO.MANDT = :P_MANDT", "EKPO.LOEKZ = ''"],  # Not deleted
    optional_filters=[
        "EKKO.LIFNR = :LIFNR",
        "EKKO.EKORG = :EKORG",
        "EKPO.PO_REL_CODE = 'X'",
        "EKPO.WERKS = :WERKS",
        "EKPO.BANFN = :PR_NUMBER",  # Was converted from PR
        "EKKO.BSART = :PO_TYPE",
        "EKPO.ETENR = :SCHEDULE_LINE",  # Specific schedule line
    ],
    sql_template="""
SELECT
    EKKO.EBELN         AS po_number,
    EKKO.BEDAT         AS po_date,
    EKKO.BSART         AS po_type,
    EKKO.EKORG         AS purchasing_org,
    EKKO.EKGRP         AS purchasing_group,
    LFA1.LIFNR         AS vendor_code,
    LFA1.NAME1         AS vendor_name,
    EKPO.EBELP         AS item,
    EKPO.MATNR         AS material,
    EKPO.TXZ01         AS description,
    MARA.MTART         AS material_type,
    EKPO.MENGE         AS ordered_qty,
    EKPO.MEINS         AS order_unit,
    EKPO.NETWR         AS order_value,
    EKPO.WAERS         AS currency,
    EKPO.EKGRP         AS po_item_buyer,
    -- Delivered quantity (cumulative GR)
    (SELECT SUM(MSEG.MENGE) FROM MSEG
     WHERE MSEG.EBELN = EKPO.EBELN AND MSEG.EBELP = EKPO.EBELP
       AND MSEG.BWART IN ('101', '102')) AS delivered_qty,
    -- Remaining quantity
    (EKPO.MENGE - COALESCE((SELECT SUM(MSEG.MENGE) FROM MSEG
       WHERE MSEG.EBELN = EKPO.EBELN AND MSEG.EBELP = EKPO.EBELP
         AND MSEG.BWART IN ('101', '102')), 0)) AS remaining_qty,
    -- Invoiced value
    (SELECT SUM(BSEG.DMBTR) FROM EKKO AS EK_INV
     JOIN EKPO AS EKPO_INV ON EK_INV.EBELN = EKPO_INV.EBELN
     JOIN BKPF ON EK_INV.EBELN = BKPF.AWKEY
     JOIN BSEG ON BKPF.BELNR = BSEG.BELNR AND BKPF.GJAHR = BSEG.GJAHR
     WHERE EK_INV.EBELN = EKKO.EBELN) AS invoiced_value
FROM EKKO
JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
JOIN LFA1 ON EKKO.LIFNR = LFA1.LIFNR
LEFT JOIN MARA ON EKPO.MATNR = MARA.MATNR
WHERE {filters}
  AND EKPO.LOEKZ = ''
  AND EKPO.ELIKZ = ''
  AND (EKPO.MENGE > COALESCE((SELECT SUM(MSEG.MENGE) FROM MSEG
        WHERE MSEG.EBELN = EKPO.EBELN AND MSEG.EBELP = EKPO.EBELP
          AND MSEG.BWART IN ('101', '102')), 0))
ORDER BY EKKO.EKGRP, EKKO.EBELN, EKPO.EBELP
""",
    select_columns={
        "EKKO": ["EBELN", "BEDAT", "BSART", "EKORG", "EKGRP", "WAERS"],
        "EKPO": ["EBELP", "MATNR", "TXZ01", "MENGE", "MEINS", "NETWR", "ELIKZ", "WEMNG"],
        "LFA1": ["LIFNR", "NAME1"],
        "MARA": ["MTART", "MATKL"],
        "EKKO_REF": ["EBELN", "AEDAT"],
    },
    example_queries=[
        "all open POs for vendor 1000",
        "undelivered purchase orders at plant 1000",
        "open quantities on POs for material",
        "PO delivery schedule for next 30 days",
        "purchasing group open orders summary",
        "open PO value by vendor",
        "PO schedule lines with confirmed dates",
        "which POs are fully delivered but not invoiced",
    ],
    confidence_boost=0.25,
    row_count_warning="Subqueries over MSEG in SELECT are expensive at scale — consider materializing delivered_qty from MSEG aggregation first.",
))

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN 3 — SALES & DISTRIBUTION (O2C)
# ═══════════════════════════════════════════════════════════════════════════════

SAP_META_PATHS.append(MetaPath(
    id="order_to_cash",
    name="Order-to-Cash (O2C) Document Chain",
    business_description=(
        "Full sales cycle: sales quotation → sales order (VA01) → delivery (VL01N) → "
        "billing (VF01) → accounting (FI). Links SD documents through VBFA (document flow), "
        "maps revenue posting to FI. Used for revenue analytics, delivery completeness, "
        "and billing reconciliation."
    ),
    domain="sales_distribution",
    module="SD",
    tags=["sales order", "delivery", "billing", "invoice", "order to cash",
          "O2C", "VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "VBRP", "VBFA",
          "revenue", "billing block", "delivery status", "order flow"],
    variants=[
        PathVariant(
            tables=["KNA1", "VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "VBRP"],
            join_conditions=[
                ("KNA1", "VBAK", "KNA1.KUNNR = VBAK.KUNNR"),
                ("VBAK", "VBAP", "VBAK.VBELN = VBAP.VBELN"),
                ("VBAK", "LIKP", "VBAK.VBELN = LIKP.VGBEL AND LIKP.VGTYP = 'C'"),
                ("LIKP", "LIPS", "LIKP.VBELN = LIPS.VBELN"),
                ("LIPS", "VBRP", "LIPS.VBELN = VBRP.VBELN AND LIPS.POSNR = VBRP.POSNR"),
                ("LIPS", "VBRK", "LIPS.VBELN = VBRK.VBELN"),
            ],
            cardinality_notes="Document flow: SO → Delivery → Billing. VBFA tracks actual flow.",
            score=1.0,
            bloom_filter=["sales order", "delivery", "billing", "invoice"],
        ),
        PathVariant(
            tables=["KNA1", "VBAK", "VBAP", "VBFA", "VBUK", "VBUP"],
            join_conditions=[
                ("KNA1", "VBAK", "KNA1.KUNNR = VBAK.KUNNR"),
                ("VBAK", "VBAP", "VBAK.VBELN = VBAP.VBELN"),
                ("VBAK", "VBFA", "VBAK.VBELN = VBFA.VBELN AND VBAP.POSNR = VBFA.POSNN"),
                ("VBAK", "VBUK", "VBAK.VBELN = VBUK.VBELN"),
                ("VBAP", "VBUP", "VBAP.VBELN = VBUP.VBELN AND VBAP.POSNR = VBUP.POSNR"),
            ],
            cardinality_notes="VBFA = actual document flow (what created what). VBUK/VBUP = status.",
            score=0.95,
            bloom_filter=["document flow", "order status", "delivery status", "billing status"],
        ),
        PathVariant(
            tables=["VBAK", "VBAP", "LIPS", "VBRK", "BKPF", "BSEG", "SKA1"],
            join_conditions=[
                ("VBAK", "VBAP", "VBAK.VBELN = VBAP.VBELN"),
                ("VBAP", "LIPS", "VBAK.VBELN = LIPS.VGBEL AND VBAP.POSNR = LIPS.VGPOS"),
                ("LIPS", "VBRK", "LIPS.VBELN = VBRK.VBELN"),
                ("VBRK", "BKPF", "VBRK.VBELN = BKPF.BELNR AND VBRK.FKIMG > 0"),
                ("BKPF", "BSEG", "BKPF.BELNR = BSEG.BELNR AND BKPF.GJAHR = BSEG.GJAHR"),
                ("BSEG", "SKA1", "BSEG.HKONT = SKA1.SAKNR"),
            ],
            cardinality_notes="Links SD billing → FI revenue posting via BKPF → BSEG → G/L",
            score=0.8,
            bloom_filter=["revenue posting", "FI posting", "revenue recognition", "gl account"],
        ),
    ],
    required_filters=["VBAK.MANDT = :P_MANDT"],
    optional_filters=[
        "VBAK.KUNNR = :KUNNR",
        "VBAK.VKORG = :SALES_ORG",
        "VBAK.VTWEG = :DIST_CHAN",
        "VBAP.MATNR = :MATNR",
        "VBAK.BSTKD = :PO_NUMBER",  # Customer PO reference
        "VBRK.FKDAT BETWEEN :DATE_FROM AND :DATE_TO",
        "VBUK.FKSTK = ''",  # Not fully billed
    ],
    sql_template="""
SELECT
    VBAK.VBELN         AS sales_order,
    VBAK.BSTNK         AS customer_po,
    VBAK.BEDAT         AS order_date,
    VBAK.VKORG         AS sales_org,
    VBAK.VTWEG         AS dist_channel,
    VBAK.SPART         AS division,
    KNA1.KUNNR         AS customer,
    KNA1.NAME1         AS customer_name,
    KNA1.LAND1         AS country,
    VBAP.POSNR         AS line_item,
    VBAP.MATNR         AS material,
    VBAP.ARKTX         AS description,
    VBAP.KWMENG        AS order_qty,
    VBAP.NETWR         AS order_value,
    VBAP.WAERK         AS currency,
    -- Delivery status
    LIPS.VBELN         AS delivery_doc,
    LIPS.LFDAT         AS delivery_date,
    LIPS.LFIMG         AS delivered_qty,
    -- Billing status
    VBRK.FKDAT         AS billing_date,
    VBRK.FKIMG         AS billed_qty,
    VBRK.NETWR         AS billing_value,
    VBRK.VBELN         AS billing_doc,
    -- Revenue posting to FI
    BKPF.BELNR         AS accounting_doc,
    BSEG.HKONT         AS revenue_gl,
    SKA1.KTOKS         AS gl_account_group,
    BSEG.DMBTR         AS revenue_amount,
    VBUK.FKSTK         AS overall_billing_status,
    VBUP.FKIVK         AS item_billing_status
FROM VBAK
JOIN KNA1 ON VBAK.KUNNR = KNA1.KUNNR
JOIN VBAP ON VBAK.VBELN = VBAP.VBELN
LEFT JOIN LIPS ON VBAK.VBELN = LIPS.VGBEL AND VBAP.POSNR = LIPS.VGPOS AND LIPS.VGTYP = 'C'
LEFT JOIN VBRK ON LIPS.VBELN = VBRK.VBELN AND LIPS.POSNR = VBRK.POSNR
LEFT JOIN BKPF ON VBRK.VBELN = BKPF.BELNR AND VBRK.GJAHR = BKPF.GJAHR
LEFT JOIN BSEG ON BKPF.BELNR = BSEG.BELNR AND BKPF.GJAHR = BSEG.GJAHR AND BSEG.BUKRS = :BUKRS
LEFT JOIN SKA1 ON BSEG.HKONT = SKA1.SAKNR
LEFT JOIN VBUK ON VBAK.VBELN = VBUK.VBELN
LEFT JOIN VBUP ON VBAP.VBELN = VBUP.VBELN AND VBAP.POSNR = VBUP.POSNR
WHERE {filters}
ORDER BY VBAK.BEDAT DESC, VBAK.VBELN, VBAP.POSNR
""",
    select_columns={
        "VBAK": ["VBELN", "BSTNK", "BEDAT", "VKORG", "VTWEG", "SPART", "WAERK"],
        "VBAP": ["POSNR", "MATNR", "ARKTX", "KWMENG", "NETWR", "FAKSP"],
        "KNA1": ["KUNNR", "NAME1", "LAND1", "KTOKD"],
        "LIPS": ["VBELN", "LFDAT", "LFIMG", "VRKME"],
        "VBRK": ["VBELN", "FKDAT", "FKIMG", "NETWR", "WAERK"],
        "VBRP": ["POSNR", "FKIMG", "NETWR"],
        "BKPF": ["BELNR", "GJAHR", "BUKRS"],
        "BSEG": ["BUZEI", "HKONT", "DMBTR", "WAERS"],
        "SKA1": ["SAKNR", "KTOKS"],
        "VBUK": ["FKSTK", "LVSTK", "ABSTK"],
        "VBUP": ["FKIVK", "LVIVK", "ABIVK"],
    },
    group_by_columns=["VBAK.VBELN", "VBAP.POSNR"],
    example_queries=[
        "order to cash cycle for customer 1000 last month",
        "sales orders with delivery and billing status",
        "revenue posting for sales order",
        "billing block on sales orders",
        "open deliveries for customer",
        "sales analytics by division and material group",
        "delivered but not billed sales orders",
        "O2C pipeline by sales org",
    ],
    confidence_boost=0.3,
    row_count_warning="VBAK without VKORG/VTWEG/SPART = all sales areas. LIPS is large — always filter by VBAK.VBELN or date range.",
))

SAP_META_PATHS.append(MetaPath(
    id="customer_open_items",
    name="Customer Open Items & Receivables",
    business_description=(
        "Outstanding receivables from customers: open invoices (BSID), cleared items (BSAD), "
        "sales data (KNVV), credit management (KNKK), and dunning data. "
        "Used for credit control, cash application, and collections."
    ),
    domain="financial_accounting",
    module="FI",
    tags=["customer", "receivables", "open items", "AR", "aging", "dunning",
          "BSID", "BSAD", "credit limit", "customer open items", "outstanding",
          "payment history", " KNKK", "KNVV"],
    variants=[
        PathVariant(
            tables=["KNA1", "KNB1", "KNVK", "BSID", "BSAD"],
            join_conditions=[
                ("KNA1", "KNB1", "KNA1.KUNNR = KNB1.KUNNR"),
                ("KNA1", "BSID", "KNA1.KUNNR = BSID.KUNNR"),
                ("BSID", "KNB1", "BSID.KUNNR = KNB1.KUNNR AND BSID.BUKRS = KNB1.BUKRS"),
                ("KNA1", "BSAD", "KNA1.KUNNR = BSAD.KUNNR"),
            ],
            cardinality_notes="BSID = open items, BSAD = cleared items. Both are BSEG secondary indexes.",
            score=1.0,
            bloom_filter=["open items", "receivables", "invoice", "payment", "outstanding"],
        ),
        PathVariant(
            tables=["KNA1", "KNVV", "BSID", "KNKK", "T001"],
            join_conditions=[
                ("KNA1", "KNVV", "KNA1.KUNNR = KNVV.KUNNR"),
                ("KNA1", "BSID", "KNA1.KUNNR = BSID.KUNNR"),
                ("KNA1", "KNKK", "KNA1.KUNNR = KNKK.KUNNR"),
                ("BSID", "T001", "BSID.BUKRS = T001.BUKRS"),
            ],
            cardinality_notes="KNVV = sales area data; KNKK = credit control area data",
            score=0.9,
            bloom_filter=["credit limit", "credit control", "sales area", "credit exposure"],
        ),
    ],
    required_filters=["KNA1.MANDT = :P_MANDT"],
    optional_filters=[
        "KNA1.KUNNR = :KUNNR",
        "BSID.BUKRS = :BUKRS",
        "BSID.ZBD1T > 0",
        "KNVV.VKORG = :SALES_ORG",
        "KNKK.KKBER = :CREDIT_CONTROL_AREA",
        "BSID.ZUONR = :REFERENCE",
    ],
    sql_template="""
SELECT
    KNA1.KUNNR         AS customer_code,
    KNA1.NAME1         AS customer_name,
    KNA1.LAND1         AS country,
    KNB1.BUKRS         AS company_code,
    KNB1.EIKTO         AS credit_account,
    -- Open items
    SUM(BSID.DMBTR)    AS open_amount,
    COUNT(BSID.BELNR)  AS open_item_count,
    MIN(BSID.ZBD1T)    AS oldest_due_days,
    -- Credit info
    KNKK.KLIME         AS credit_limit,
    KNKK.KLIMK         AS maximum_credit,
    KNKK.SKLBE         AS special_credit_limit,
    -- Sales area
    KNVV.VKORG         AS sales_org,
    KNVV.VTWEG         AS dist_channel,
    KNVV.KDGRP         AS customer_group
FROM KNA1
LEFT JOIN KNB1 ON KNA1.KUNNR = KNB1.KUNNR
LEFT JOIN BSID ON KNA1.KUNNR = BSID.KUNNR AND BSID.BUKRS = :BUKRS
LEFT JOIN BSAD ON KNA1.KUNNR = BSAD.KUNNR AND BSAD.BUKRS = :BUKRS AND BSAD.AUGDT >= :DATE_90DAYS
LEFT JOIN KNVV ON KNA1.KUNNR = KNVV.KUNNR AND KNVV.VKORG = :VKORG
LEFT JOIN KNKK ON KNA1.KUNNR = KNKK.KUNNR
WHERE {filters}
GROUP BY KNA1.KUNNR, KNA1.NAME1, KNA1.LAND1, KNB1.BUKRS, KNB1.EIKTO,
         KNKK.KLIME, KNKK.KLIMK, KNKK.SKLBE,
         KNVV.VKORG, KNVV.VTWEG, KNVV.KDGRP
ORDER BY KNA1.NAME1
""",
    select_columns={
        "KNA1": ["KUNNR", "NAME1", "LAND1", "KTOKD"],
        "KNB1": ["BUKRS", "EIKTO", "ZAHLS"],
        "BSID": ["BELNR", "BUZEI", "DMBTR", "WAERS", "ZBD1T", "ZBD2T", "ZBD3T", "FAEDT"],
        "BSAD": ["BELNR", "DMBTR", "AUGDT"],
        "KNVV": ["VKORG", "VTWEG", "KDGRP", "KLART"],
        "KNKK": ["KLIMK", "KLIME", "SKLBE", "KKBER"],
        "T001": ["BUKRS", "BUTXT"],
    },
    example_queries=[
        "outstanding invoices for customer 1000",
        "customer receivables aging",
        "credit limit and exposure for customer",
        "dunning level for customer",
        "special ledger open items by due date",
        "customer payment history",
        "AR balance by sales org",
        "overdue items for customer group",
    ],
    confidence_boost=0.25,
    row_count_warning="BSID without BUKRS = all company codes. Always filter KUNNR or BUKRS.",
))

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN 4 — MATERIAL MASTER & STOCK
# ═══════════════════════════════════════════════════════════════════════════════

SAP_META_PATHS.append(MetaPath(
    id="material_stock_position",
    name="Material Stock Position (MM + WM)",
    business_description=(
        "Complete inventory picture: unrestricted stock (MARD), restricted stock, "
        "quality inspection stock (QALS→QMAT), blocked stock, special stock (MSKA/MSLB/MKOL), "
        "valuation (MBEW), warehouse management (MLGN/MLGT/LQUA). "
        "Reconciles IM (MARD) vs. WM (LQUA) inventory."
    ),
    domain="material_master",
    module="MM",
    tags=["stock", "inventory", "on hand", "unrestricted", "restricted", "blocked",
          "quality inspection", "special stock", "valuation", "MRP", "stock position",
          "MARD", "MBEW", "MSKA", "MSLB", "MKOL", "LQUA", "warehouse", "stock value"],
    variants=[
        PathVariant(
            tables=["MARA", "MARC", "MARD", "MBEW", "MAKT", "T001W"],
            join_conditions=[
                ("MARA", "MARC", "MARA.MATNR = MARC.MATNR"),
                ("MARC", "MARD", "MARC.MATNR = MARD.MATNR AND MARC.WERKS = MARD.WERKS"),
                ("MARD", "MBEW", "MARD.MATNR = MBEW.MATNR AND MARD.BWKEY = MBEW.BWKEY"),
                ("MARA", "MAKT", "MARA.MATNR = MAKT.MATNR AND MAKT.SPRAS = 'E'"),
                ("MARC", "T001W", "MARC.WERKS = T001W.WERKS"),
            ],
            cardinality_notes="MARD is 1 row per material-plant-storage location. MBEW is 1 row per material-valuation area.",
            score=1.0,
            bloom_filter=["stock", "on hand", "unrestricted", "valuation", "stock value", "plant stock"],
        ),
        PathVariant(
            tables=["MARA", "MLGN", "MLGT", "LQUA", "T001L"],
            join_conditions=[
                ("MARA", "MLGN", "MARA.MATNR = MLGN.MATNR"),
                ("MLGN", "MLGT", "MLGN.MATNR = MLGT.MATNR AND MLGN.LGNR = MLGT.LGNNR"),
                ("MLGT", "LQUA", "MLGT.MATNR = LQUA.MATNR AND MLGT.LGTYP = LQUA.LGTYP AND MLGT.LGBZL = LQUA.LGBZL"),
                ("LQUA", "T001L", "LQUA.WERKS = T001L.WERKS AND LQUA.LGORT = T001L.LGORT"),
            ],
            cardinality_notes="WM (Warehouse Management) view — 1 row per storage bin. LQUA is QU-based.",
            score=0.85,
            bloom_filter=["warehouse", "storage bin", "WM stock", "transfer order", "LQUA"],
        ),
        PathVariant(
            tables=["MARA", "MSKA", "MSLB", "MKOL", "MARD"],
            join_conditions=[
                ("MARA", "MARD", "MARA.MATNR = MARD.MATNR"),
                ("MARA", "MSKA", "MARA.MATNR = MSKA.MATNR"),
                ("MARA", "MSLB", "MARA.MATNR = MSLB.MATNR"),
                ("MARA", "MKOL", "MARA.MATNR = MKOL.MATNR"),
            ],
            cardinality_notes="Special stocks: MSKA=Customer, MSLB=Vendor, MKOL=Project. Each is 1-per-owner-per-material.",
            score=0.75,
            bloom_filter=["special stock", "customer stock", "vendor stock", "project stock", "consignment"],
        ),
    ],
    required_filters=["MARA.MANDT = :P_MANDT"],
    optional_filters=[
        "MARA.MATNR = :MATNR",
        "MARC.WERKS = :WERKS",
        "MARD.LGORT = :STORAGE_LOCATION",
        "MARA.MTART = :MATERIAL_TYPE",
        "MBEW.BKLAS = :VALUATION_CLASS",
        "MARD.Labst > 0",
        "MBEW.BWTYP = 'V'",
    ],
    sql_template="""
SELECT
    MARA.MATNR         AS material,
    MAKT.MAKTX         AS description,
    MARA.MTART         AS material_type,
    MARA.MATKL         AS material_group,
    MARC.WERKS         AS plant,
    T001W.NAME1        AS plant_name,
    MARD.LGORT         AS storage_location,
    -- IM stock (unrestricted + restricted + blocked)
    MARD.Labst         AS unrestricted_stock,
    MARD.Insme         AS quality_inspection_stock,
    MARD.Spinb         AS blocked_stock,
    MARD.Einme         AS total_stock,
    -- Valuation
    MBEW.BKLAS         AS valuation_class,
    MBEW.STPRS         AS standard_price,
    MBEW.VERPR         AS moving_avg_price,
    MBEW.PEPRX         AS previous_price,
    MBEW.BWKEY         AS valuation_area,
    (MARD.Labst * MBEW.VERPR) AS unrestricted_stock_value,
    (MARD.Einme * MBEW.VERPR) AS total_stock_value,
    MBEW.WAERS         AS currency,
    -- Special stocks
    (SELECT SUM(MSKA.LABST) FROM MSKA WHERE MSKA.MATNR = MARA.MATNR AND MSKA.WERKS = MARC.WERKS) AS customer_order_stock,
    (SELECT SUM(MSLB.LABST) FROM MSLB WHERE MSLB.MATNR = MARA.MATNR AND MSLB.WERKS = MARC.WERKS) AS vendor_stock,
    (SELECT SUM(MKOL.LABST) FROM MKOL WHERE MKOL.MATNR = MARA.MATNR AND MKOL.WERKS = MARC.WERKS) AS project_stock,
    -- MRP data
    MARC.DISMM         AS MRP_type,
    MARC.MINBE         AS reorder_point,
    MARC.MABST         AS maximum_stock,
    MARC.EISBE         AS safety_stock
FROM MARA
JOIN MARC ON MARA.MATNR = MARC.MATNR
JOIN MARD ON MARC.MATNR = MARD.MATNR AND MARC.WERKS = MARD.WERKS
JOIN MBEW ON MARD.MATNR = MBEW.MATNR AND MARD.BWKEY = MBEW.BWKEY
LEFT JOIN MAKT ON MARA.MATNR = MAKT.MATNR AND MAKT.SPRAS = 'E'
LEFT JOIN T001W ON MARC.WERKS = T001W.WERKS
WHERE {filters}
  AND MARD.Labst > 0 OR MARD.Insme > 0 OR MARD.Spinb > 0
ORDER BY MARC.WERKS, MARD.LGORT, MARA.MATNR
""",
    select_columns={
        "MARA": ["MATNR", "MTART", "MATKL"],
        "MAKT": ["MAKTX"],
        "MARC": ["WERKS", "DISMM", "MINBE", "MABST", "EISBE"],
        "MARD": ["LGORT", "Labst", "Insme", "Spinb", "Einme"],
        "MBEW": ["BWKEY", "BKLAS", "STPRS", "VERPR", "PEPRX", "WAERS"],
        "T001W": ["NAME1"],
        "MSKA": ["LABST"],
        "MSLB": ["LABST"],
        "MKOL": ["LABST"],
    },
    example_queries=[
        "current stock position for material 100-100 at plant 1000",
        "inventory valuation and stock value",
        "quality inspection stock for material",
        "special stock by owner",
        "blocked stock at warehouse",
        "MRP relevant stock for material",
        "plant stock overview by material group",
        "stock aging report",
    ],
    confidence_boost=0.25,
    row_count_warning="MARD is partitioned by plant/storage location. Query without WERKS/LGORT scans entire table. MBEW price can be plant-specific (BWKEY).",
))

SAP_META_PATHS.append(MetaPath(
    id="material_cost_rollup",
    name="Material Cost Rollup (BOM + Routing)",
    business_description=(
        "Builds standard cost of a manufactured material through multi-level BOM explosion "
        "(STKO→STPO) and routing/work center operations (CRHD→PLPO→CPHO). "
        "Used for cost estimating, make-vs-buy analysis, and variance analysis."
    ),
    domain="material_master",
    module="MM-PP",
    tags=["cost rollup", "BOM explosion", "standard cost", "routing", "work center",
          "STKO", "STPO", "MAST", "CRHD", "PLPO", "CPHO", "KALSM", "CK11N",
          "material cost", "cost estimate", "make vs buy", "costing"],
    variants=[
        PathVariant(
            tables=["MARA", "STKO", "STPO", "MAST", "CRHD", "PLPO"],
            join_conditions=[
                ("MARA", "STKO", "MARA.MATNR = STKO.MATNR AND STKO.STLST = '1'"),
                ("STKO", "STPO", "STKO.STLNR = STPO.STLNR AND STKO.STLAL = STPO.STLAL"),
                ("MARA", "MAST", "MARA.MATNR = MAST.MATNR"),
                ("MAST", "CRHD", "MAST.OBJID = CRHD.OBJID"),
                ("CRHD", "PLPO", "CRHD.OBJID = PLPO.ARBID"),
            ],
            cardinality_notes="BOM explosion requires recursive CTE. Work center ops linked via PLPO-ARBID=CRHD-OBJID.",
            score=1.0,
            bloom_filter=["BOM", "bill of materials", "cost rollup", "multi-level", "component"],
        ),
    ],
    required_filters=["MARA.MANDT = :P_MANDT", "STKO.STLST = '1'"],  # Active BOM only
    optional_filters=[
        "MARA.MATNR = :MATNR",
        "STKO.STLAL = :ALTERNATIVE_BOM",
        "STPO.POSTP = 'L'",
        "PLPO.ARBID = CRHD.OBJID AND PLPO.PLZDP > 0",
        "PLPO.BMSCH > 0",
    ],
    sql_template="""
-- NOTE: Multi-level BOM explosion requires RECURSIVE CTE on SAP HANA
-- This template shows single-level; wrap in WITH RECURSIVE for multi-level
WITH RECURSIVE bom_explosion (MATNR, COMP, QTY_PER, DEPTH, PATH, UOM) AS (
    -- Base material
    SELECT STKO.MATNR, STPO.IDNRK, STPO.MENGE, 0, CAST(STKO.MATNR AS VARCHAR(200)), STPO.MMEIN
    FROM STKO
    JOIN STPO ON STKO.STLNR = STPO.STLNR AND STKO.STLAL = STPO.STLAL
    WHERE STKO.MATNR = :TOP_MATNR AND STKO.STLST = '1'
    
    UNION ALL
    
    -- Recursive: sub-BOMs
    SELECT b.MATNR, s.IDNRK, b.QTY_PER * s.MENGE, b.DEPTH + 1,
           b.PATH || '/' || s.IDNRK, s.MMEIN
    FROM bom_explosion b
    JOIN STKO ss ON b.COMP = ss.MATNR AND ss.STLST = '1'
    JOIN STPO s ON ss.STLNR = s.STLNR AND ss.STLAL = s.STLAL
    WHERE b.DEPTH < :MAX_DEPTH
)
SELECT
    b.MATNR         AS parent_material,
    b.COMP          AS component,
    b.QTY_PER       AS quantity_per,
    b.DEPTH         AS bom_level,
    b.PATH          AS bom_path,
    m.MTART         AS component_type,
    mbw.VERPR       AS moving_avg_price,
    mbw.STPRS       AS standard_price,
    mbw.WAERS       AS currency,
    (b.QTY_PER * COALESCE(mbw.VERPR, mbw.STPRS, 0)) AS component_cost,
    ch.OBJID         AS work_center,
    pl.VGW01        AS labor_hours,
    pl.VGW02        AS machine_hours,
    pl.ARBEI        AS labor_time,
    pl.MGEIN        AS labor_unit
FROM bom_explosion b
LEFT JOIN MARA m ON b.COMP = m.MATNR
LEFT JOIN MBEW mbw ON b.COMP = mbw.MATNR
LEFT JOIN MAST ma ON b.COMP = ma.MATNR
LEFT JOIN CRHD ch ON ma.OBJID = ch.OBJID AND ch.OBJTY = 'A'
LEFT JOIN PLPO pl ON ch.OBJID = pl.ARBID
WHERE b.DEPTH <= :MAX_DEPTH
ORDER BY b.DEPTH, b.PATH;
""",
    select_columns={
        "MARA": ["MATNR", "MTART"],
        "STKO": ["STLNR", "STLAL", "STLST", "DATUV"],
        "STPO": ["IDNRK", "MENGE", "MEINS", "POSTP"],
        "MBEW": ["VERPR", "STPRS", "PEPRX", "WAERS"],
        "CRHD": ["OBJID", "OBJTY", "VERSA"],
        "PLPO": ["VGW01", "VGW02", "ARBEI", "MGEIN", "BMSCH"],
    },
    example_queries=[
        "BOM cost rollup for material FG-100",
        "multi-level BOM explosion for finished good",
        "standard cost estimate for manufactured material",
        "component cost breakdown for assembly",
        "work center rates for routing operations",
        "make vs buy decision for material",
        "material cost variance analysis",
    ],
    confidence_boost=0.2,
    row_count_warning="Multi-level BOM explosion is recursive and can be expensive. Limit MAX_DEPTH to 5. STPO.POSTP='L' filters only material items (skip text/dimensions).",
))

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN 5 — QUALITY MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

SAP_META_PATHS.append(MetaPath(
    id="inspection_lot_material",
    name="QM Inspection Lot & Material Quality",
    business_description=(
        "Quality inspection lots (QALS) linked to material receipt (MSEG), "
        "inspection characteristics (QAVE), usage decisions (QAMV), "
        "and QM task lists (MAPL→PLMK→PLPO). "
        "Used for supplier quality analysis, incoming inspection rates, and rejection trends."
    ),
    domain="quality_management",
    module="QM",
    tags=["inspection lot", "quality", "QM", "rejection", "usage decision",
          "QALS", "QAVE", "QAMV", "MAPL", "PLMK", "MSEG", "defect",
          "inspection characteristics", "sample", "AQL", "UD code"],
    variants=[
        PathVariant(
            tables=["MARA", "QALS", "QAVE", "QAMV", "MSEG", "MKPF"],
            join_conditions=[
                ("MARA", "QALS", "MARA.MATNR = QALS.MATNR"),
                ("QALS", "QAVE", "QALS.QALS = QAVE.QALS"),
                ("QAVE", "QAMV", "QALS.QALS = QAMV.QALS AND QAVE.QUNUM = QAMV.QUNUM"),
                ("QALS", "MSEG", "QALS.MATNR = MSEG.MATNR AND QALS.LIFNR = MSEG.LIFNR"),
                ("MSEG", "MKPF", "MSEG.MBLNR = MKPF.MBLNR AND MSEG.MJAHR = MKPF.MJAHR"),
            ],
            cardinality_notes="QALS is 1 per inspection lot. QAVE is per characteristic. QAMV is usage decision.",
            score=1.0,
            bloom_filter=["inspection", "rejection", "quality", "usage decision", "UD"],
        ),
        PathVariant(
            tables=["MARA", "MAPL", "PLMK", "PLPO", "QALS"],
            join_conditions=[
                ("MARA", "MAPL", "MARA.MATNR = MAPL.MATNR AND MAPL.PLNTY = 'Q'"),
                ("MAPL", "PLMK", "MAPL.PLNNR = PLMK.PLNNR AND MAPL.PLNKN = PLMK.PLNKN"),
                ("MAPL", "PLPO", "MAPL.PLNNR = PLPO.PLNNR AND MAPL.PLNKN = PLPO.PLNKN"),
                ("MARA", "QALS", "MARA.MATNR = QALS.MATNR"),
            ],
            cardinality_notes="MAPL links material to QM task list (inspection plan). PLMK = inspection characteristics.",
            score=0.8,
            bloom_filter=["inspection plan", "task list", "QM master", "characteristics"],
        ),
    ],
    required_filters=["QALS.MANDT = :P_MANDT"],
    optional_filters=[
        "QALS.MATNR = :MATNR",
        "QALS.LIFNR = :LIFNR",
        "QALS.WERKS = :WERKS",
        "QALS.QSPEZ BETWEEN :DATE_FROM AND :DATE_TO",
        "QALS.STAT IN ('Released', 'Closed')",
        "QALS.ART = '01'",
        "MSEG.BWART = '101'",
    ],
    sql_template="""
SELECT
    QALS.QALS         AS inspection_lot,
    QALS.MATNR         AS material,
    MARA.MTART         AS material_type,
    QALS.LIFNR         AS vendor,
    LFA1.NAME1         AS vendor_name,
    QALS.WERKS         AS plant,
    T001W.NAME1        AS plant_name,
    QALS.ERNAM         AS inspector,
    QALS.ERDAT         AS created_on,
    QALS.QSPEZ         AS inspection_date,
    QALS.MENGE1        AS sample_qty,
    QALS.MABST         AS used_qty,
    QALS.ENTMV         AS valuation_result,
    QALS.URSACH        AS defect_root,
    QALS.STAT          AS lot_status,
    -- Usage decision
    QAMV.QUNDZ         AS UD_code,
    QAMV.QUPAR         AS UD_parcel,
    CASE QAMV.QUNDZ
        WHEN 'A' THEN 'Accept without restr.'
        WHEN 'B' THEN 'Accept with notice'
        WHEN 'C' THEN 'Sample-destroyed accept'
        WHEN 'R' THEN 'Reject'
        WHEN 'S' THEN 'Split for usage'
        ELSE 'Pending UD'
    END                AS UD_description,
    -- Per-characteristic results
    QAVE.VCODE         AS characteristic_result,
    QAVE.MEINQ         AS inspection_unit,
    QAVE.MWVHW         AS measured_value,
    -- Link to GR
    MSEG.MBLNR         AS material_doc,
    MSEG.BUDAT         AS gr_date,
    MSEG.MENGE         AS gr_qty
FROM QALS
JOIN MARA ON QALS.MATNR = MARA.MATNR
LEFT JOIN LFA1 ON QALS.LIFNR = LFA1.LIFNR
LEFT JOIN T001W ON QALS.WERKS = T001W.WERKS
LEFT JOIN QAVE ON QALS.QALS = QAVE.QALS
LEFT JOIN QAMV ON QALS.QALS = QAMV.QALS
LEFT JOIN MSEG ON QALS.MATNR = MSEG.MATNR AND QALS.QSPEZ = MSEG.BUDAT AND MSEG.BWART = '101'
LEFT JOIN MKPF ON MSEG.MBLNR = MKPF.MBLNR AND MSEG.MJAHR = MKPF.MJAHR
WHERE {filters}
ORDER BY QALS.ERDAT DESC, QALS.QALS DESC
""",
    select_columns={
        "QALS": ["QALS", "MATNR", "LIFNR", "WERKS", "ERNAM", "ERDAT", "QSPEZ",
                  "MENGE1", "MABST", "ENTMV", "URSACH", "STAT", "ART"],
        "QAVE": ["QUNUM", "QUPOS", "VCODE", "MEINQ", "MWVHW", "MVGE1"],
        "QAMV": ["QUNUM", "QUNDZ", "QUPAR", "TCODE4"],
        "MARA": ["MTART", "MATKL"],
        "LFA1": ["NAME1"],
        "MSEG": ["MBLNR", "MJAHR", "BUDAT", "MENGE", "BWART"],
    },
    example_queries=[
        "inspection lots for material at plant 1000",
        "vendor quality rejection rate",
        "QM usage decision for PO item",
        "quality inspection results for material",
        "incoming inspection for vendor",
        "supplier quality scorecard",
        "rejected lots with defect root cause",
        "inspection plan for material",
    ],
    confidence_boost=0.2,
    row_count_warning="QALS has inspection-type-specific fields. Always filter by ART (incoming/process/final). MSEG join can produce multiple rows if same material received multiple times.",
))

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN 6 — PROJECT SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

SAP_META_PATHS.append(MetaPath(
    id="project_costs_wbs",
    name="WBS Element Cost & Progress",
    business_description=(
        "Project costs from WBS elements (PRPS) through networks (PROJ→AFKO→AFVC), "
        "commitments (COSP/COSS for actuals,plan), purchase orders (EKKO→EKPO), "
        "and billing plans (VBAK→VBKP). Used for project steering, Earned Value Management, "
        "and CAPEX tracking."
    ),
    domain="project_system",
    module="PS",
    tags=["WBS", "project", "network", "EVM", "earned value", "project costs",
          "PRPS", "PROJ", "AFKO", "AFVC", "COSP", "COSS", "commitment",
          "budget", "actual costs", "project progress", "milestone"],
    variants=[
        PathVariant(
            tables=["PRPS", "PROJ", "AFKO", "AFVC", "COSP", "COSS"],
            join_conditions=[
                ("PRPS", "PROJ", "PRPS.PSPNR = PROJ.PSPNR"),
                ("PRPS", "AFKO", "PRPS.OBJNR = AFKO.OBJNR"),
                ("AFKO", "AFVC", "AFKO.AUFNR = AFVC.AUFNR"),
                ("PRPS", "COSP", "PRPS.OBJNR = COSP.OBJNR"),
                ("PRPS", "COSS", "PRPS.OBJNR = COSS.OBJNR"),
            ],
            cardinality_notes="COSP = actual costs, COSS = plan costs. Both keyed by OBJNR=WBS+network.",
            score=1.0,
            bloom_filter=["WBS cost", "project cost", "EVM", "budget vs actual", "commitment"],
        ),
        PathVariant(
            tables=["PRPS", "MKOL", "MARA", "EKKO", "EKPO"],
            join_conditions=[
                ("PRPS", "MKOL", "PRPS.OBJNR = MKOL.OBJNR"),
                ("MKOL", "MARA", "MKOL.MATNR = MARA.MATNR"),
                ("PRPS", "EKKO", "PRPS.PSPEL = EKKO.ANGNR"),
                ("EKKO", "EKPO", "EKKO.EBELN = EKPO.EBELN"),
            ],
            cardinality_notes="MKOL = project special stock. EKKO linked via WBS element as PO reference.",
            score=0.7,
            bloom_filter=["project PO", "project purchase", "project stock", "commitment"],
        ),
    ],
    required_filters=["PRPS.MANDT = :P_MANDT"],
    optional_filters=[
        "PRPS.PSPNR = :WBS_ELEMENT",
        "PRPS.POSID = :WBS_ID",
        "PROJ.PERIV = :FISCAL_YEAR",
        "COSP.GJAHR = :FISCAL_YEAR",
        "AFKO.AUART = :ORDER_TYPE",
        "AFVC.STATUS IN ('CLSD', 'REL')",
        "PRPS.VERAK = :PROJECT_MANAGER",
    ],
    sql_template="""
SELECT
    PRPS.POSID         AS wbs_id,
    PRPS.POST1         AS wbs_description,
    PRPS.PRHID         AS project_definition,
    PRPS.VERNR         AS version,
    PRPS.STATE         AS wbs_status,
    -- Budget
    COSP.WOG001        AS budget_labor,
    COSP.WOG002        AS budget_material,
    COSP.WOG003        AS budget_services,
    SUM(COSP.WOG001 + COSP.WOG002 + COSP.WOG003) AS total_budget,
    -- Actual costs
    COSS.WOG001        AS actual_labor,
    COSS.WOG002        AS actual_material,
    COSS.WOG003        AS actual_services,
    SUM(COSS.WOG001 + COSS.WOG002 + COSS.WOG003) AS total_actual,
    -- Commitments (open POs)
    SUM(EKPO.NETWR)    AS po_commitment,
    -- Project stock (MKOL)
    SUM(MKOL.LABST)    AS project_stock_value,
    -- Network progress
    AFVC.ISMN          AS confirmed_qty,
    AFVC.IERTA         AS actual_labor_hours,
    -- Dates
    PRPS.FAKTR         AS completion_percentage,
    PRPS.PEDTR         AS planned_finish,
    PRPS.IEDTR         AS actual_finish,
    PRPS.START         AS planned_start,
    PRPS.ISTART        AS actual_start
FROM PRPS
LEFT JOIN PROJ ON PRPS.PSPNR = PROJ.PSPNR
LEFT JOIN AFKO ON PRPS.OBJNR = AFKO.OBJNR
LEFT JOIN AFVC ON AFKO.AUFNR = AFVC.AUFNR
LEFT JOIN COSP ON PRPS.OBJNR = COSP.OBJNR AND COSP.GJAHR = :GJAHR
LEFT JOIN COSS ON PRPS.OBJNR = COSS.OBJNR AND COSS.GJAHR = :GJAHR
LEFT JOIN MKOL ON PRPS.OBJNR = MKOL.OBJNR
LEFT JOIN EKKO ON PRPS.PSPEL = EKKO.ANGNR
LEFT JOIN EKPO ON EKKO.EBELN = EKPO.EBELN
WHERE {filters}
GROUP BY PRPS.POSID, PRPS.POST1, PRPS.PRHID, PRPS.VERNR, PRPS.STATE,
         COSP.WOG001, COSP.WOG002, COSP.WOG003,
         COSS.WOG001, COSS.WOG002, COSS.WOG003,
         AFVC.ISMN, AFVC.IERTA,
         PRPS.FAKTR, PRPS.PEDTR, PRPS.IEDTR, PRPS.START, PRPS.ISTART
ORDER BY PRPS.POSID
""",
    select_columns={
        "PRPS": ["POSID", "POST1", "PRHID", "STTXT", "STATE", "FAKTR", "PEDTR", "IEDTR"],
        "PROJ": ["PSPNR", "PERIV", "PROJ_OBJECT"],
        "AFKO": ["AUFNR", "AUFPL", "GLTPS"],
        "AFVC": ["ISMN", "IERTA", "BMEI1", "STATUS"],
        "COSP": ["WRTTP", "GJAHR", "PERBL", "WOG001", "WOG002", "WOG003"],
        "COSS": ["WRTTP", "GJAHR", "PERBL", "WOG001", "WOG002", "WOG003"],
        "MKOL": ["LABST", "MEINS"],
    },
    example_queries=[
        "WBS element cost and budget for project",
        "project Earned Value Management metrics",
        "project commitment and actual costs",
        "project stock (special stock) value",
        "network activities with actual hours",
        "CAPEX project spend by WBS",
        "project milestone billing plan",
        "project cost forecast vs budget",
    ],
    confidence_boost=0.2,
    row_count_warning="COSP/COSS are period-based. Always filter GJAHR and WRTTP (costs/plan/forecast). PRPS-PSPHI gives hierarchical parent WBS.",
))

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN 7 — ASSET ACCOUNTING (RE-FX)
# ═══════════════════════════════════════════════════════════════════════════════

SAP_META_PATHS.append(MetaPath(
    id="asset_register",
    name="Asset Master & Transaction History",
    business_description=(
        "Fixed asset master (ANLA, ANLH, ANLC) with GL integration (SKA1/SKB1), "
        "corporate asset map (ANAT), insurance (INTR), and transaction history (ANEP, ANEA). "
        "Supports depreciation run, asset history, and IFRS16 lease asset tracking."
    ),
    domain="financial_accounting",
    module="FI-AA",
    tags=["asset", "fixed asset", "ANLA", "ANLH", "ANLC", "ANEP", "depreciation",
          "book depreciation", "tax depreciation", "asset class", "GL integration",
          "IFRS16", "right of use", "lease asset", "asset history"],
    variants=[
        PathVariant(
            tables=["ANLA", "ANLH", "ANLC", "T001", "SKA1", "SKB1"],
            join_conditions=[
                ("ANLA", "ANLH", "ANLA.ANLN1 = ANLH.ANLN1"),
                ("ANLA", "ANLC", "ANLA.ANLN1 = ANLC.ANLN1 AND ANLA.ANLN2 = ANLC.ANLN2"),
                ("ANLA", "T001", "ANLA.BUKRS = T001.BUKRS"),
                ("ANLA", "SKA1", "ANLA.SAKNR = SKA1.SAKNR"),
                ("SKA1", "SKB1", "SKA1.SAKNR = SKB1.SAKNR AND ANLA.BUKRS = SKB1.BUKRS"),
            ],
            cardinality_notes="ANLA = main asset number; ANLH = sub-number; ANLC = period values (APC, depreciation).",
            score=1.0,
            bloom_filter=["asset master", "depreciation", "book value", "asset class", "GL"],
        ),
        PathVariant(
            tables=["ANLA", "ANEP", "ANEA", "BKPF", "BSEG"],
            join_conditions=[
                ("ANLA", "ANEP", "ANLA.ANLN1 = ANEP.ANLN1 AND ANLA.ANLN2 = ANEP.ANLN2"),
                ("ANEP", "ANEA", "ANEP.ANLN1 = ANEA.ANLN1 AND ANEP.ANLN2 = ANEA.ANLN2 AND ANEP.BELNR = ANEA.BELNR"),
                ("ANEP", "BKPF", "ANEP.BUKRS = BKPF.BUKRS AND ANEP.BELNR = BKPF.BELNR AND ANEP.GJAHR = BKPF.GJAHR"),
                ("BKPF", "BSEG", "BKPF.BELNR = BSEG.BELNR AND BKPF.GJAHR = BSEG.GJAHR"),
            ],
            cardinality_notes="ANEP = asset transactions; ANEA = period accumulation; linked to FI docs.",
            score=0.9,
            bloom_filter=["asset transaction", "acquisition", "retirement", "asset history", "depreciation run"],
        ),
    ],
    required_filters=["ANLA.MANDT = :P_MANDT"],
    optional_filters=[
        "ANLA.ANLN1 = :ASSET_NUMBER",
        "ANLA.BUKRS = :BUKRS",
        "ANLA.ANLKL = :ASSET_CLASS",
        "ANLA.INVNR = :INSURANCE_POLICY",
        "ANLC.GJAHR = :FISCAL_YEAR",
        "BKPF.BLDAT BETWEEN :DATE_FROM AND :DATE_TO",
        "ANEP.BWART IN ('100', '200')",
    ],
    sql_template="""
SELECT
    ANLA.ANLN1         AS asset_number,
    ANLA.ANLN2         AS sub_number,
    ANLA.BUKRS         AS company_code,
    ANLA.ANLKL         AS asset_class,
    ANLA.TXT50         AS asset_description,
    ANLA.ERNAM         AS created_by,
    ANLA.ERDAT         AS capitalization_date,
    ANLA.INVNR         AS inventory_number,
    ANLA.ORT01         AS location,
    ANLA.MSTAI         AS asset_status,
    T001.BUTXT         AS company_name,
    SKA1.KTOKS         AS gl_account_group,
    SKA1.SAKNR         AS gl_account,
    -- APC (Acquisition and Production Cost)
    ANLC.AKLA0         AS apc_current_year,
    SUM(ANLC.NAFAG)    AS total_acquisition_value,
    -- Depreciation
    ANLC.GKON0         AS cumulative_depreciation,
    ANLC.NABAG         AS depreciation_this_year,
    (ANLC.AKLA0 - ANLC.GKON0) AS net_book_value,
    -- Insurance
    ANLA.INVNR         AS insurance_policy,
    INTR.VERDN         AS insurance_valid_to
FROM ANLA
LEFT JOIN ANLC ON ANLA.ANLN1 = ANLC.ANLN1 AND ANLA.ANLN2 = ANLC.ANLN2 AND ANLC.GJAHR = :GJAHR
LEFT JOIN T001 ON ANLA.BUKRS = T001.BUKRS
LEFT JOIN SKA1 ON ANLA.SAKNR = SKA1.SAKNR
LEFT JOIN SKB1 ON ANLA.SAKNR = SKB1.SAKNR AND ANLA.BUKRS = SKB1.BUKRS
LEFT JOIN INTR ON ANLA.ANLN1 = INTR.ANLN1
WHERE {filters}
GROUP BY ANLA.ANLN1, ANLA.ANLN2, ANLA.BUKRS, ANLA.ANLKL, ANLA.TXT50,
         ANLA.ERNAM, ANLA.ERDAT, ANLA.INVNR, ANLA.ORT01, ANLA.MSTAI,
         T001.BUTXT, SKA1.KTOKS, SKA1.SAKNR, ANLC.AKLA0, ANLC.GKON0, ANLC.NABAG, INTR.VERDN
ORDER BY ANLA.ANLKL, ANLA.ANLN1
""",
    select_columns={
        "ANLA": ["ANLN1", "ANLN2", "BUKRS", "ANLKL", "TXT50", "ERNAM", "ERDAT",
                  "INVNR", "ORT01", "MSTAI", "MSAID"],
        "ANLC": ["GJAHR", "AKLA0", "NAFAG", "GKON0", "NABAG", "AAFAR"],
        "SKA1": ["SAKNR", "KTOKS", "XTEXT"],
        "SKB1": ["SAKNR", "BUKRS", "WAERS"],
        "INTR": ["VERDN", "INSRG", "INTRG"],
        "T001": ["BUKRS", "BUTXT"],
    },
    example_queries=[
        "fixed asset register for company code",
        "asset depreciation this year",
        "net book value of all assets",
        "asset transaction history",
        "assets by class and location",
        "IFRS16 right-of-use assets",
        "retired assets this year",
        "insurance coverage for assets",
    ],
    confidence_boost=0.2,
    row_count_warning="ANLC is period-based — always filter GJAHR. ANLA has ORD43 rich text; TXT50 is short text. Multiple ANLH sub-numbers possible.",
))

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN 8 — TRANSPORTATION MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

SAP_META_PATHS.append(MetaPath(
    id="transportation_delivery",
    name="Transportation & Outbound Delivery Tracking",
    business_description=(
        "Outbound deliveries (LIKP/LIPS) linked to transportation orders (VTTK/VTTS), "
        "shipment costs (VTTK→SHPBA), shipping conditions, route (TVRO), "
        "weight/volume (VTTK-LFIMG, VTLK), and carrier (LFA1). "
        "Used for logistics cost analysis, on-time delivery, and freight management."
    ),
    domain="transportation",
    module="TM",
    tags=["transportation", "shipment", "delivery", "VTTK", "VTTS", "VTLK",
          "carrier", "freight", "route", "shipping", "outbound delivery",
          "LIKP", "LIPS", "weight", "volume", "VBAK", "T001W"],
    variants=[
        PathVariant(
            tables=["LIKP", "LIPS", "VTTK", "VTTS", "TVRO", "LFA1", "T001W"],
            join_conditions=[
                ("LIKP", "VTTK", "LIKP.TKNUM = VTTK.TKNUM"),
                ("VTTK", "VTTS", "VTTK.TKNUM = VTTS.TKNUM AND VTTK.TPLNR = VTTS.TPLNR"),
                ("VTTK", "TVRO", "VTTK.TDROPT = TVRO.TDLINE"),
                ("VTTK", "LFA1", "VTTK.LIFNR = LFA1.LIFNR"),
                ("LIKP", "T001W", "LIKP.TDWRK = T001W.WERKS"),
            ],
            cardinality_notes="1 VTTK per shipment; VTTS is per-leg. Multiple deliveries per shipment.",
            score=1.0,
            bloom_filter=["shipment", "transportation order", "carrier", "freight", "delivery tracking"],
        ),
        PathVariant(
            tables=["VBAK", "LIKP", "LIPS", "VBRK", "BSEG", "KNA1"],
            join_conditions=[
                ("VBAK", "LIKP", "VBAK.VBELN = LIKP.VGBEL AND LIKP.VGTYP = 'C'"),
                ("LIKP", "LIPS", "LIKP.VBELN = LIPS.VBELN"),
                ("LIPS", "VBRK", "LIPS.VBELN = VBRK.VBELN"),
                ("VBRK", "BSEG", "VBRK.BELNR = BSEG.BELNR AND VBRK.GJAHR = BSEG.GJAHR"),
                ("VBAK", "KNA1", "VBAK.KUNNR = KNA1.KUNNR"),
            ],
            cardinality_notes="Full O2C + freight cost link. BSEG-HKONT = freight expense account.",
            score=0.85,
            bloom_filter=["freight cost", "delivery billing", "logistics", "revenue"],
        ),
    ],
    required_filters=["LIKP.MANDT = :P_MANDT"],
    optional_filters=[
        "VTTK.TKNUM = :SHIPMENT_NUMBER",
        "VTTK.LIFNR = :CARRIER_VENDOR",
        "LIKP.WADAT BETWEEN :DATE_FROM AND :DATE_TO",
        "LIKP.TDSTL = 'X'",
        "VTTS.TDLNR = :ROUTE_ID",
        "VBAK.VKORG = :SALES_ORG",
    ],
    sql_template="""
SELECT
    VTTK.TKNUM         AS shipment_number,
    VTTK.TDLNR         AS route_id,
    TVRO.TDTEXT        AS route_description,
    VTTK.DTAMS         AS means_of_transport,
    VTTK.TRAID         AS transport_identification,
    LFA1.LIFNR         AS carrier_vendor,
    LFA1.NAME1         AS carrier_name,
    VTTK.KUNNR         AS ship_to_party,
    LIKP.VBELN         AS delivery_doc,
    LIKP.WADAT         AS goods_issue_date,
    LIKP.TDEDAT        AS pick_up_date,
    LIPS.MATNR         AS material,
    LIPS.LFIMG         AS delivered_qty,
    LIPS.NTGEW         AS net_weight,
    LIPS.GEWEI         AS weight_unit,
    LIPS.VOLUM         AS volume,
    VBRK.FKDAT         AS billing_date,
    VBRK.NETWR         AS billing_value,
    BSEG.HKONT         AS freight_expense_gl,
    BSEG.DMBTR         AS freight_cost,
    T001W.NAME1        AS plant_name,
    VBAK.VBELN         AS sales_order,
    VBAK.KUNNR         AS sold_to_party,
    KNA1.NAME1         AS customer_name
FROM VTTK
JOIN LIKP ON VTTK.TKNUM = LIKP.TKNUM
JOIN LIPS ON LIKP.VBELN = LIPS.VBELN
LEFT JOIN VTTS ON VTTK.TKNUM = VTTS.TKNUM
LEFT JOIN TVRO ON VTTK.TDROPT = TVRO.TDLINE
LEFT JOIN LFA1 ON VTTK.LIFNR = LFA1.LIFNR
LEFT JOIN VBAK ON LIKP.VGBEL = VBAK.VBELN
LEFT JOIN T001W ON LIKP.TDWRK = T001W.WERKS
LEFT JOIN VBRK ON LIPS.VBELN = VBRK.VBELN
LEFT JOIN BSEG ON VBRK.BELNR = BSEG.BELNR AND VBRK.GJAHR = BSEG.GJAHR
LEFT JOIN KNA1 ON VBAK.KUNNR = KNA1.KUNNR
WHERE {filters}
ORDER BY VTTK.TKNUM, LIKP.VBELN, LIPS.POSNR
""",
    select_columns={
        "VTTK": ["TKNUM", "TDLNR", "DTAMS", "TRAID", "LIFNR", "KUNNR", "WADAT"],
        "VTTS": ["TDLNR", "TPLNR", "ABlad", "DTWEG"],
        "TVRO": ["TDLINE", "TDTEXT", "LAND1"],
        "LIKP": ["VBELN", "WADAT", "TDEDAT", "TDSTL", "TDWRK"],
        "LIPS": ["POSNR", "MATNR", "LFIMG", "NTGEW", "GEWEI", "VOLUM", "VRKME"],
        "VBAK": ["VBELN", "KUNNR", "VKORG"],
        "VBRK": ["VBELN", "FKDAT", "NETWR", "WAERK"],
        "BSEG": ["HKONT", "DMBTR", "WAERS"],
        "KNA1": ["NAME1"],
        "LFA1": ["NAME1"],
    },
    example_queries=[
        "shipment tracking for delivery",
        "transportation costs by carrier",
        "outbound delivery logistics report",
        "freight cost by route and carrier",
        "on-time delivery performance",
        "logistics spend analytics",
        "shipping route optimization",
    ],
    confidence_boost=0.2,
))

# ═══════════════════════════════════════════════════════════════════════════════
#  DOMAIN 9 — INVENTORY & WAREHOUSE MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

SAP_META_PATHS.append(MetaPath(
    id="warehouse_quant_inventory",
    name="WM Warehouse Quant Inventory",
    business_description=(
        "Warehouse management (WM) layer: storage type (LAGP), storage bin (LDEP/LQUA), "
        "quant (LQUA), handling unit (VEKP/VEPO), transfer requirements (TB01), "
        "transfer orders (LTAK/LTAP). Reconciles HU-level and bin-level inventory."
    ),
    domain="warehouse_management",
    module="WM",
    tags=["warehouse", "storage type", "storage bin", "quant", "LQUA", "LAGP",
          "LTAK", "LTAP", "handling unit", "HU", "VEKP", "VEPO",
          "transfer order", "pick", "putaway", "WM inventory"],
    variants=[
        PathVariant(
            tables=["MARA", "MLGN", "MLGT", "LAGP", "LQUA", "T001L", "T001W"],
            join_conditions=[
                ("MARA", "MLGN", "MARA.MATNR = MLGN.MATNR"),
                ("MLGN", "MLGT", "MLGN.MATNR = MLGT.MATNR AND MLGN.LGNR = MLGT.LGNNR"),
                ("MLGT", "LAGP", "MLGT.WERKS = LAGP.WERKS AND MLGT.LGTYP = LAGP.LGTYP"),
                ("LAGP", "LQUA", "LAGP.WERKS = LQUA.WERKS AND LAGP.LGTYP = LQUA.LGTYP AND LAGP.LGBZL = LQUA.LGBZL"),
                ("LQUA", "T001L", "LQUA.WERKS = T001L.WERKS AND LQUA.LGORT = T001L.LGORT"),
                ("LAGP", "T001W", "LAGP.WERKS = T001W.WERKS"),
            ],
            cardinality_notes="LQUA is 1 row per quant (material-batch-ownership per bin). HU = handling unit.",
            score=1.0,
            bloom_filter=["storage bin", "warehouse", "quant", "pick", "putaway", "WM level"],
        ),
        PathVariant(
            tables=["LTAK", "LTAP", "MARA", "LQUA", "VEKP", "VBAK"],
            join_conditions=[
                ("LTAK", "LTAP", "LTAK.TANUM = LTAP.TANUM"),
                ("LTAP", "MARA", "LTAP.MATNR = MARA.MATNR"),
                ("LTAP", "LQUA", "LTAP.MATNR = LQUA.MATNR AND LTAP.QUNUM = LQUA.QUNUM"),
                ("LTAP", "VEKP", "LTAP.HULUN = VEKP.VENUM"),
                ("LTAK", "VBAK", "LTAP.REFBN = VBAK.VBELN"),
            ],
            cardinality_notes="LTAK/LTAP = transfer orders. VEKP/VEPO = handling unit. Links to delivery for pick.",
            score=0.8,
            bloom_filter=["transfer order", "pick order", "handling unit", "pick list"],
        ),
    ],
    required_filters=["LQUA.MANDT = :P_MANDT"],
    optional_filters=[
        "MARA.MATNR = :MATNR",
        "LQUA.WERKS = :WERKS",
        "LAGP.LGTYP = :STORAGE_TYPE",
        "LQUA.LGBZL = :STORAGE_SECTION",
        "LQUA.QLCOO = :BATCH",
        "LQUA.OWNPR = :SPECIAL_STOCK_OWNER",
        "LTAK.TDLNR = :DELIVERY",
    ],
    sql_template="""
SELECT
    LQUA.MATNR         AS material,
    MARA.MTART         AS material_type,
    LQUA.WERKS         AS plant,
    T001W.NAME1        AS plant_name,
    LAGP.LGTYP         AS storage_type,
    LAGP.LGTYP_NAME    AS storage_type_name,
    LAGP.LGBZL         AS storage_section,
    LQUA.LGNUM         AS warehouse_number,
    T001L.LGORT        AS storage_location,
    T001L.LGBUN        AS storage_location_type,
    LQUA.LGPTY         AS stock_type,
    CASE LQUA.QLABS
        WHEN '01' THEN 'Unrestricted'
        WHEN '02' THEN 'Quality Inspection'
        WHEN '03' THEN 'Blocked'
        WHEN '04' THEN 'Transfer'
        ELSE 'Other'
    END                AS stock_type_description,
    LQUA.QLABS         AS quant_stock,
    LQUA.QLSUN         AS blocked_stock,
    LQUA.QEWED         AS inspection_stock,
    LQUA.QLHOL         AS total_stock,
    LQUA.CHARG         AS batch,
    LQUA.QLPTY         AS special_stock_type,
    LQUA.LIFNR         AS vendor_batch_owner,
    LQUA.KUNNR         AS customer_batch_owner,
    LQUA.OBJNR         AS project_objnr,
    -- Handling unit
    VEKP.VENUM         AS handling_unit_number,
    VEKP.VEGRT         AS packaging_material,
    VEKP.GWEIWR        AS hu_weight,
    VEKP.GEWEI         AS weight_unit,
    -- Bin utilization
    LQUA.KZBDQ         AS blocked_for_quality,
    LQUA.QMAXT         AS max_quant_capacity,
    (LQUA.QLABS / NULLIF(LQUA.QMAXT, 0)) AS bin_utilization_pct
FROM LQUA
JOIN MARA ON LQUA.MATNR = MARA.MATNR
JOIN LAGP ON LQUA.WERKS = LAGP.WERKS AND LQUA.LGTYP = LAGP.LGTYP AND LQUA.LGBZL = LAGP.LGBZL
JOIN T001L ON LQUA.WERKS = T001L.WERKS AND LQUA.LGORT = T001L.LGORT
JOIN T001W ON LQUA.WERKS = T001W.WERKS
LEFT JOIN VEKP ON LQUA.HULUN = VEKP.VENUM
WHERE {filters}
  AND LQUA.QLABS > 0 OR LQUA.QLSUN > 0 OR LQUA.QEWED > 0
ORDER BY LQUA.WERKS, LAGP.LGTYP, T001L.LGORT, LQUA.MATNR
""",
    select_columns={
        "LQUA": ["LGNUM", "MATNR", "WERKS", "LGTYP", "LGBZL", "LGORT", "QUNUM",
                  "QLABS", "QLSUN", "QEWED", "QLHOL", "CHARG", "QLPTY",
                  "LIFNR", "KUNNR", "OBJNR", "HULUN", "KZBDQ", "QMAXT"],
        "MARA": ["MTART", "MATKL"],
        "LAGP": ["LGTYP", "LGTYP_NAME", "LGBZL"],
        "T001L": ["LGORT", "LGBUN", "LTEXT"],
        "T001W": ["NAME1"],
        "VEKP": ["VENUM", "VEGRT", "GWEIWR", "GEWEI", "VOLUM"],
    },
    example_queries=[
        "warehouse stock by storage type and bin",
        "quant inventory for material at plant",
        "blocked stock in warehouse",
        "handling unit details for pick",
        "transfer order for warehouse",
        "storage type capacity utilization",
        "special stock in WM",
        "pick list for delivery",
    ],
    confidence_boost=0.2,
    row_count_warning="LQUA can be very large in high-volume warehouses. Always filter WERKS and LGTYP. LQUA-QLPTY distinguishes special stock ownership.",
))


# ═══════════════════════════════════════════════════════════════════════════════
#  MetaPath Library — Search & Resolution Engine
# ═══════════════════════════════════════════════════════════════════════════════

class MetaPathLibrary:
    """
    Searchable library of pre-computed SAP meta-paths.

    Supports:
    - Exact domain/module/tag lookup
    - Keyword search (bloom filter + fuzzy match)
    - Natural language intent matching
    - Confidence-ranked result selection
    """

    def __init__(self, paths: List[MetaPath] = None):
        self.paths = paths or SAP_META_PATHS
        self._build_indices()

    def _build_indices(self):
        """Build fast lookup indices."""
        # By domain
        self._by_domain: Dict[str, List[MetaPath]] = {}
        for p in self.paths:
            self._by_domain.setdefault(p.domain, []).append(p)

        # By module
        self._by_module: Dict[str, List[MetaPath]] = {}
        for p in self.paths:
            self._by_module.setdefault(p.module, []).append(p)

        # By tag (inverted index)
        self._by_tag: Dict[str, List[MetaPath]] = {}
        for p in self.paths:
            for tag in p.tags:
                self._by_tag.setdefault(tag.lower(), []).append(p)

        # By table (which meta-paths include this table?)
        self._by_table: Dict[str, List[MetaPath]] = {}
        for p in self.paths:
            for variant in p.variants:
                for table in variant.tables:
                    self._by_table.setdefault(table, []).append(p)

    # ─── Core Search Methods ──────────────────────────────────────────────────

    def match(
        self,
        query: str,
        tables: List[str] = None,
        domain: str = None,
        module: str = None,
        top_k: int = 3,
    ) -> List[Dict]:
        """
        Primary entry point: match a natural-language query (and optional
        table hints) to the best meta-path(s).

        Returns ranked list of matches with scores, SQL templates,
        and join paths ready for injection.
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\b\w{3,}\b', query_lower))

        scored: Dict[str, float] = {}
        match_reasons: Dict[str, List[str]] = {}

        for path in self.paths:
            score = 0.0
            reasons = []

            # Domain filter
            if domain and path.domain != domain:
                continue

            # Module filter
            if module and path.module != module:
                continue

            # 1. Exact tag match (highest weight)
            path_tags_lower = [t.lower() for t in path.tags]
            for word in query_words:
                for tag in path_tags_lower:
                    if word in tag or tag in word:
                        score += 3.0
                        reasons.append(f"tag_match:{tag}")

            # 2. Bloom filter on best variant (fast keyword check)
            best = path.best_variant()
            for word in query_words:
                for bloom_tag in best.bloom_filter:
                    if word in bloom_tag.lower() or bloom_tag.lower() in word:
                        score += 2.0
                        reasons.append(f"bloom:{bloom_tag}")

            # 3. Business description match
            desc_words = set(re.findall(r'\b\w{4,}\b', path.business_description.lower()))
            overlap = query_words & desc_words
            score += len(overlap) * 1.5
            if overlap:
                reasons.append(f"desc:{overlap}")

            # 4. Table coverage (if tables are provided)
            if tables:
                path_tables = set(best.tables)
                query_tables = set(t.upper() for t in tables)
                intersection = path_tables & query_tables
                if intersection:
                    score += len(intersection) * 4.0
                    reasons.append(f"table_hit:{intersection}")

                # Check if ALL query tables are covered by this path
                uncovered = query_tables - path_tables
                if not uncovered:
                    score += 5.0
                    reasons.append("all_tables_covered")

            # 5. Example query match
            for example in path.example_queries:
                ex_words = set(re.findall(r'\b\w{3,}\b', example.lower()))
                ex_overlap = query_words & ex_words
                if ex_overlap:
                    score += 1.0 * len(ex_overlap)
                    reasons.append(f"example:{ex_overlap}")

            # 6. Domain coherence bonus
            if domain == path.domain:
                score += 1.0

            if score > 0:
                scored[path.id] = score
                match_reasons[path.id] = reasons

        # Rank and return top-k
        ranked = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for path_id, score in ranked:
            path_obj = next(p for p in self.paths if p.id == path_id)
            best = path_obj.best_variant()

            results.append({
                "path_id": path_obj.id,
                "name": path_obj.name,
                "business_description": path_obj.business_description,
                "domain": path_obj.domain,
                "module": path_obj.module,
                "match_score": round(score, 2),
                "match_reasons": match_reasons.get(path_id, []),
                "confidence_boost": path_obj.confidence_boost,
                "tables": best.tables,
                "join_conditions": best.join_conditions,
                "required_filters": path_obj.required_filters,
                "optional_filters": path_obj.optional_filters,
                "sql_template": path_obj.sql_template,
                "select_columns": path_obj.select_columns,
                "group_by_columns": path_obj.group_by_columns,
                "example_queries": path_obj.example_queries,
                "row_count_warning": path_obj.row_count_warning,
                "all_variants": [
                    {
                        "tables": v.tables,
                        "cardinality_notes": v.cardinality_notes,
                        "score": v.score,
                        "bloom_filter": v.bloom_filter,
                    }
                    for v in sorted(path_obj.variants, key=lambda x: x.score, reverse=True)
                ],
            })

        return results

    def get_by_id(self, path_id: str) -> Optional[MetaPath]:
        return next((p for p in self.paths if p.id == path_id), None)

    def get_by_domain(self, domain: str) -> List[MetaPath]:
        return self._by_domain.get(domain, [])

    def get_by_table(self, table: str) -> List[MetaPath]:
        return self._by_table.get(table.upper(), [])

    def list_all(self) -> List[Dict]:
        return [
            {
                "id": p.id,
                "name": p.name,
                "domain": p.domain,
                "module": p.module,
                "description": p.business_description,
                "tags": p.tags,
                "variant_count": len(p.variants),
                "example_queries": p.example_queries,
            }
            for p in self.paths
        ]

    def stats(self) -> Dict:
        return {
            "total_meta_paths": len(self.paths),
            "total_variants": sum(len(p.variants) for p in self.paths),
            "by_domain": {
                domain: len(paths)
                for domain, paths in self._by_domain.items()
            },
            "by_module": {
                module: len(paths)
                for module, paths in self._by_module.items()
            },
            "tables_indexed": len(self._by_table),
        }


# ── Auto-Generated Paths (from graph traversal) ──────────────────────────────
# Generated by: meta_path_auto_generator_v2.py
try:
    from app.core.sql_patterns.auto_meta_paths_v2 import AUTO_META_PATHS_V2
    _auto_converted = []
    for d in AUTO_META_PATHS_V2:
        _join_tuples = []
        for _entry in d.get('join_conditions', []):
            if isinstance(_entry, (list, tuple)) and len(_entry) == 3:
                _t1, _t2, _cond = _entry
                if isinstance(_cond, str):
                    _join_tuples.append((_t1, _t2, _cond))
        _variants = [PathVariant(
            tables=d['tables'],
            join_conditions=_join_tuples,
            cardinality_notes='',
            score=0.8,
            bloom_filter=d.get('tags', [])
        )] if _join_tuples else [PathVariant(
            tables=d['tables'],
            join_conditions=[],
            cardinality_notes='',
            score=1.0,
            bloom_filter=d.get('tags', [])
        )]
        _auto_converted.append(MetaPath(
            id=d['id'],
            name=d['name'],
            business_description=d['business_description'],
            domain=d.get('domain', 'auto_generated'),
            module=d.get('module_pair', d.get('module', 'AUTO')),
            tags=d.get('tags', []),
            variants=_variants,
            required_filters=d.get('required_filters', ['MANDT = :P_MANDT']),
            optional_filters=d.get('optional_filters', []),
            sql_template=d['sql_template'],
            select_columns={t: d['tables'] for t in d['tables']},
            example_queries=d.get('example_queries', []),
            confidence_boost=d.get('confidence_boost', 0.15),
            row_count_warning=d.get('row_count_warning', ''),
        ))
    SAP_META_PATHS.extend(_auto_converted)
    print(f"[META-PATH] Loaded {len(_auto_converted)} auto paths. Total: {len(SAP_META_PATHS)}")
except Exception as e:
    print(f"[META-PATH] Auto-paths skipped: {e}")

# Singleton
meta_path_library = MetaPathLibrary(SAP_META_PATHS)


# ─── CLI Tool ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json, sys

    print("=" * 70)
    print("  SAP Meta-Path Library")
    print("=" * 70)

    stats = meta_path_library.stats()
    print(f"\n  Total meta-paths: {stats['total_meta_paths']}")
    print(f"  Total variants:    {stats['total_variants']}")
    print(f"  Tables indexed:   {stats['tables_indexed']}")

    print("\n  By domain:")
    for domain, count in sorted(stats['by_domain'].items()):
        print(f"    {domain}: {count} path(s)")

    print("\n  By module:")
    for module, count in sorted(stats['by_module'].items()):
        print(f"    {module}: {count} path(s)")

    print("\n" + "=" * 70)
    print("  Demo Queries")
    print("=" * 70)

    demos = [
        "show me vendor who supplied material 100-100 to plant 1000",
        "open invoices for vendor Lincoln Electronics",
        "order to cash cycle for customer last month",
        "BOM cost rollup for finished good FG-100",
        "quality inspection rejection rate for vendor",
        "WBS project cost and budget",
        "warehouse stock by storage type",
        "fixed asset depreciation register",
        "transportation shipment for outbound delivery",
        "material stock position with valuation",
    ]

    for q in demos:
        print(f"\n  Query: \"{q}\"")
        results = meta_path_library.match(q, top_k=2)
        if results:
            top = results[0]
            print(f"  → Matched: {top['name']} (score={top['match_score']}, "
                  f"boost=+{top['confidence_boost']})")
            print(f"    Tables: {' → '.join(top['tables'][:6])}")
            print(f"    Reasons: {top['match_reasons'][:4]}")
        else:
            print("  → No match")

    print("\n" + "=" * 70)
    print("  Full Library")
    print("=" * 70)
    for entry in meta_path_library.list_all():
        print(f"\n  [{entry['id']}] {entry['name']}")
        print(f"    Domain: {entry['domain']} | Module: {entry['module']}")
        print(f"    Variants: {entry['variant_count']}")
        print(f"    Desc: {entry['description'][:100]}...")
        print(f"    Examples: {entry['example_queries'][:2]}")
