"""
SAP Master Data SQL Pattern Library
===================================
Comprehensive proven SQL patterns for all 18 SAP Master Data domains.
Each pattern includes: intent description, business use case, and ready-to-use SQL.

Usage:
    from app.core.sql_patterns.library import get_all_patterns, PATTERNS_BY_DOMAIN
    patterns = PATTERNS_BY_DOMAIN["material_master"]
"""

from typing import Dict, List

# Auto-Generated Pattern Integration
try:
    from .auto_generated_patterns import *
except ImportError:
    pass


# ============================================================================
# 1. BUSINESS PARTNER (BP) — Vendors, Customers, Contacts
# ============================================================================

BUSINESS_PARTNER_PATTERNS = [
    {
        "intent": "Get vendor master details by vendor number",
        "business_use_case": "Display full vendor information including name, city, country, and tax ID",
        "tables": ["LFA1"],
        "sql": """
SELECT 
    LIFNR AS VENDOR_ID,
    NAME1 AS VENDOR_NAME,
    ORT01 AS CITY,
    LAND1 AS COUNTRY,
    STCD1 AS TAX_NUMBER_1,
    STCD2 AS TAX_NUMBER_2,
    BANKS AS BANK_COUNTRY,
    BANKL AS BANK_KEY,
    BANKN AS BANK_ACCOUNT
FROM 
    LFA1
WHERE 
    MANDT = '{MANDT}'
    AND LIFNR = '{vendor_id}';
"""
    },
    {
        "intent": "Find all vendors in a specific country",
        "business_use_case": "List all approved vendors for a country for sourcing analysis",
        "tables": ["LFA1"],
        "sql": """
SELECT 
    LIFNR AS VENDOR_ID,
    NAME1 AS VENDOR_NAME,
    ORT01 AS CITY,
    LAND1 AS COUNTRY
FROM 
    LFA1
WHERE 
    MANDT = '{MANDT}'
    AND LAND1 = '{country_code}'
ORDER BY 
    NAME1;
"""
    },
    {
        "intent": "Get customer master details by customer number",
        "business_use_case": "Display full customer information for CRM or SD processing",
        "tables": ["KNA1"],
        "sql": """
SELECT 
    KUNNR AS CUSTOMER_ID,
    NAME1 AS CUSTOMER_NAME,
    ORT01 AS CITY,
    LAND1 AS COUNTRY,
    KDKG1 AS CUST_PRICE_GROUP,
    KDGRP AS CUSTOMER_GROUP
FROM 
    KNA1
WHERE 
    MANDT = '{MANDT}'
    AND KUNNR = '{customer_id}';
"""
    },
    {
        "intent": "Get vendor company code data including payment terms and reconciliation account",
        "business_use_case": "Fetch vendor's finance-specific data for AP processing",
        "tables": ["LFA1", "LFB1"],
        "sql": """
SELECT 
    v.LIFNR AS VENDOR_ID,
    v.NAME1 AS VENDOR_NAME,
    c.BUKRS AS COMPANY_CODE,
    c.HBKID AS HOUSE_BANK_ID,
    c.ZTERM AS PAYMENT_TERMS,
    c.AKONT AS RECONCILIATION_GL,
    c.WAERS AS CURRENCY
FROM 
    LFA1 v
JOIN 
    LFB1 c ON v.MANDT = c.MANDT AND v.LIFNR = c.LIFNR
WHERE 
    v.MANDT = '{MANDT}'
    AND v.LIFNR = '{vendor_id}'
    AND c.BUKRS = '{company_code}';
"""
    },
    {
        "intent": "Get Business Partner address using BP table and address services",
        "business_use_case": "Display formatted address for business letters or notifications",
        "tables": ["BUT000", "ADRC"],
        "sql": """
SELECT 
    bp.PARTNER,
    bp.NAME_ORG1 AS COMPANY_NAME,
    addr.STREET,
    addr.CITY1 AS CITY,
    addr.POST_CODE1 AS POSTAL_CODE,
    addr.REGION AS STATE,
    addr.COUNTRY
FROM 
    BUT000 bp
LEFT JOIN 
    ADRC addr ON bp.PARTNER = addr.ADDRNUMBER
WHERE 
    bp.PARTNER = '{partner_id}';
"""
    },
    {
        "intent": "Find customers by sales district and region",
        "business_use_case": "Regional sales analysis and territory management",
        "tables": ["KNA1"],
        "sql": """
SELECT 
    KUNNR AS CUSTOMER_ID,
    NAME1 AS CUSTOMER_NAME,
    ORT01 AS CITY,
    REGIO AS REGION,
    BZIRK AS SALES_DISTRICT
FROM 
    KNA1
WHERE 
    MANDT = '{MANDT}'
    AND REGIO = '{region_code}'
    AND BZIRK = '{sales_district}';
"""
    }
]


# ============================================================================
# 2. MATERIAL MASTER (MM) — Materials, Products, Articles
# ============================================================================

MATERIAL_MASTER_PATTERNS = [
    {
        "intent": "Get material basic details with English description",
        "business_use_case": "Display material overview for procurement or production planning",
        "tables": ["MARA", "MAKT"],
        "sql": """
SELECT 
    m.MATNR AS MATERIAL_ID,
    m.MTART AS MATERIAL_TYPE,
    m.MATKL AS MATERIAL_GROUP,
    m.MEINS AS BASE_UNIT,
    m.BRGEW AS GROSS_WEIGHT,
    m.NTGEW AS NET_WEIGHT,
    m.GEWEI AS WEIGHT_UNIT,
    t.MAKTX AS MATERIAL_DESCRIPTION
FROM 
    MARA m
JOIN 
    MAKT t ON m.MATNR = t.MATNR
WHERE 
    m.MANDT = '{MANDT}'
    AND m.MATNR = '{material_id}'
    AND t.SPRAS = 'E';
"""
    },
    {
        "intent": "Get material stock levels by plant and storage location",
        "business_use_case": "Check current inventory levels for availability confirmation",
        "tables": ["MARA", "MARD"],
        "sql": """
SELECT 
    s.MATNR AS MATERIAL_ID,
    s.WERKS AS PLANT,
    s.LGORT AS STORAGE_LOCATION,
    s.LABST AS UNRESTRICTED_STOCK,
    s.INSME AS QUALITY_INSPECTION_STOCK,
    s.UMLME AS TRANSFER_STOCK,
    s.SPSTOCK AS BLOCKED_STOCK,
    m.MEINS AS UNIT
FROM 
    MARD s
JOIN 
    MARA m ON s.MATNR = m.MATNR AND s.MANDT = m.MANDT
WHERE 
    s.MANDT = '{MANDT}'
    AND s.MATNR = '{material_id}'
    AND s.WERKS = '{plant_id}';
"""
    },
    {
        "intent": "Get material valuation data including moving average and standard prices",
        "business_use_case": "Fetch material cost for pricing or variance analysis",
        "tables": ["MBEW", "MARA"],
        "sql": """
SELECT 
    v.MATNR AS MATERIAL_ID,
    v.BWKEY AS VALUATION_AREA,
    v.BKLAS AS VALUATION_CLASS,
    v.VPRSV AS PRICE_CONTROL,
    CASE v.VPRSV 
        WHEN 'V' THEN v.VERPR 
        WHEN 'S' THEN v.STPRS 
    END AS CURRENT_PRICE,
    v.PEINH AS PRICE_UNIT,
    v.VERPR AS MOVING_AVG_PRICE,
    v.STPRS AS STANDARD_PRICE,
    m.MEINS AS UNIT
FROM 
    MBEW v
JOIN 
    MARA m ON v.MATNR = m.MATNR AND v.MANDT = m.MANDT
WHERE 
    v.MANDT = '{MANDT}'
    AND v.MATNR = '{material_id}'
    AND v.BWKEY = '{valuation_area}';
"""
    },
    {
        "intent": "Get material work scheduling data for a specific plant",
        "business_use_case": "Review MRP parameters and scheduling for production or procurement",
        "tables": ["MARC", "MARA"],
        "sql": """
SELECT 
    p.MATNR AS MATERIAL_ID,
    p.WERKS AS PLANT,
    p.DISMM AS MRP_TYPE,
    p.DISPO AS MRP_CONTROLLER,
    p.MINBE AS REORDER_POINT,
    p.EISBE AS SAFETY_STOCK,
    p.BSTRF AS LOT_SIZE,
    p.LGPRO AS ISSUING_STORAGE_LOC,
    m.MEINS AS BASE_UNIT
FROM 
    MARC p
JOIN 
    MARA m ON p.MATNR = m.MATNR AND p.MANDT = m.MANDT
WHERE 
    p.MANDT = '{MANDT}'
    AND p.MATNR = '{material_id}'
    AND p.WERKS = '{plant_id}';
"""
    },
    {
        "intent": "Find materials by material type and material group",
        "business_use_case": "Category-based material lookup for catalog browsing",
        "tables": ["MARA", "MAKT"],
        "sql": """
SELECT 
    m.MATNR AS MATERIAL_ID,
    t.MAKTX AS MATERIAL_DESCRIPTION,
    m.MTART AS MATERIAL_TYPE,
    m.MATKL AS MATERIAL_GROUP,
    m.MEINS AS BASE_UNIT
FROM 
    MARA m
JOIN 
    MAKT t ON m.MATNR = t.MATNR AND m.MANDT = t.MANDT
WHERE 
    m.MANDT = '{MANDT}'
    AND m.MTART = '{material_type}'
    AND t.SPRAS = 'E'
ORDER BY 
    t.MAKTX;
"""
    },
    {
        "intent": "Get total plant-wide stock for a material including all storage locations",
        "business_use_case": "Aggregate inventory view for supply chain dashboard",
        "tables": ["MARD", "MARA"],
        "sql": """
SELECT 
    MATNR AS MATERIAL_ID,
    WERKS AS PLANT,
    SUM(LABST) AS TOTAL_UNRESTRICTED,
    SUM(INSME) AS TOTAL_QM_STOCK,
    SUM(UMLME) AS TOTAL_TRANSFER,
    SUM(SPSTOCK) AS TOTAL_BLOCKED
FROM 
    MARD
WHERE 
    MANDT = '{MANDT}'
    AND MATNR = '{material_id}'
    AND WERKS = '{plant_id}'
GROUP BY 
    MATNR, WERKS;
"""
    }
]


# ============================================================================
# 3. PURCHASING (MM-PUR) — Purchase Orders, Info Records, Source Lists
# ============================================================================

PURCHASING_PATTERNS = [
    {
        "intent": "Get purchase order header and item details",
        "business_use_case": "Display full PO information including vendor, date, and item data",
        "tables": ["EKKO", "EKPO"],
        "sql": """
SELECT 
    h.EBELN AS PO_NUMBER,
    h.BUKRS AS COMPANY_CODE,
    h.BSART AS PO_TYPE,
    h.LIFNR AS VENDOR_ID,
    h.EKORG AS PURCHASING_ORG,
    h.EKGRP AS PURCHASING_GROUP,
    h.BEDAT AS PO_DATE,
    h.WAERS AS CURRENCY,
    i.EBELP AS PO_ITEM,
    i.MATNR AS MATERIAL_ID,
    i.TXZ01 AS SHORT_TEXT,
    i.MENGE AS ORDER_QUANTITY,
    i.MEINS AS UNIT,
    i.NETPR AS NET_PRICE,
    i.PEINH AS PRICE_UNIT,
    i.WERKS AS PLANT,
    i.LGORT AS DELIVERY_ADDRESS
FROM 
    EKKO h
JOIN 
    EKPO i ON h.EBELN = i.EBELN AND h.MANDT = i.MANDT
WHERE 
    h.MANDT = '{MANDT}'
    AND h.EBELN = '{po_number}';
"""
    },
    {
        "intent": "Find purchasing info records for a vendor and material",
        "business_use_case": "Check existing negotiated pricing before creating a new PO",
        "tables": ["EINA", "EINE"],
        "sql": """
SELECT 
    r.INFNR AS INFO_RECORD,
    r.LIFNR AS VENDOR_ID,
    r.MATNR AS MATERIAL_ID,
    r.MEINS AS ORDER_UNIT,
    o.EKORG AS PURCHASING_ORG,
    o.WERKS AS PLANT,
    o.NETWR AS NET_PRICE_VALUE,
    o.PEINH AS PRICE_UNIT,
    o.APLFZ AS PLANNED_DELIVERY_DAYS
FROM 
    EINA r
JOIN 
    EINE o ON r.INFNR = o.INFNR AND r.MANDT = o.MANDT
WHERE 
    r.MANDT = '{MANDT}'
    AND r.LIFNR = '{vendor_id}'
    AND r.MATNR = '{material_id}'
    AND o.EKORG = '{purchasing_org}';
"""
    },
    {
        "intent": "Get open purchase orders for a vendor",
        "business_use_case": "Review outstanding PO commitments with a specific supplier",
        "tables": ["EKKO", "EKPO"],
        "sql": """
SELECT 
    h.EBELN AS PO_NUMBER,
    h.BEDAT AS PO_DATE,
    h.LIFNR AS VENDOR_ID,
    i.EBELP AS ITEM,
    i.MATNR AS MATERIAL_ID,
    i.TXZ01 AS DESCRIPTION,
    i.MENGE AS ORDER_QTY,
    i.MEINS AS UNIT,
    i.WEMNG AS RECEIVED_QTY,
    i.NETPR AS NET_PRICE
FROM 
    EKKO h
JOIN 
    EKPO i ON h.EBELN = i.EBELN AND h.MANDT = i.MANDT
WHERE 
    h.MANDT = '{MANDT}'
    AND h.LIFNR = '{vendor_id}'
    AND i.WEMNG < i.MENGE  -- Open quantity remaining
ORDER BY 
    h.BEDAT;
"""
    },
    {
        "intent": "Get source list for a material specifying authorized vendors",
        "business_use_case": "Determine which vendors are approved for a material",
        "tables": ["EORD"],
        "sql": """
SELECT 
    MATNR AS MATERIAL_ID,
    WERKS AS PLANT,
    LIFNR AS VENDOR_ID,
    FLIEF AS FIXED_VENDOR,
    EKORG AS PURCHASING_ORG,
    DATAB AS VALID_FROM,
    DATBI AS VALID_TO
FROM 
    EORD
WHERE 
    MANDT = '{MANDT}'
    AND MATNR = '{material_id}'
    AND WERKS = '{plant_id}'
    AND DATBI >= CURRENT_DATE;
"""
    },
    {
        "intent": "Get contract/agreement header details",
        "business_use_case": "Review contract terms before processing",
        "tables": ["EKKO"],
        "sql": """
SELECT 
    EBELN AS CONTRACT_NUMBER,
    BUKRS AS COMPANY_CODE,
    BSART AS DOC_TYPE,
    LIFNR AS VENDOR_ID,
    WAERS AS CURRENCY,
    KTWRT AS VALUE_LIMIT,
    BONDB AS BONUS_DEADLINE,
    ABRDN AS MINIMUM_ORDER_VALUE,
    BEDAT AS CREATION_DATE,
    KDATB AS VALID_FROM,
    KDATV AS VALID_TO
FROM 
    EKKO
WHERE 
    MANDT = '{MANDT}'
    AND EBELN = '{contract_number}'
    AND BSTYP = 'K';  -- K = Contract
"""
    }
]


# ============================================================================
# 4. SALES & DISTRIBUTION (SD) — Sales Orders, Pricing, Partners
# ============================================================================

SALES_DISTRIBUTION_PATTERNS = [
    {
        "intent": "Get sales order header and item details",
        "business_use_case": "Display complete sales order with pricing and partner functions",
        "tables": ["VBAK", "VBAP"],
        "sql": """
SELECT 
    h.VBELN AS SALES_ORDER,
    h.KUNAG AS SOLD_TO_CUSTOMER,
    h.KUNWE AS SHIP_TO_CUSTOMER,
    h.BSTKD AS PURCHASE_ORDER,
    h.ERDAT AS ORDER_DATE,
    h.AUART AS ORDER_TYPE,
    h.WAERK AS CURRENCY,
    i.POSNR AS LINE_ITEM,
    i.MATNR AS MATERIAL_ID,
    i.ARKTX AS DESCRIPTION,
    i.KWMENG AS ORDER_QUANTITY,
    i.KMEINS AS UNIT,
    i.NETWR AS NET_VALUE,
    i.PSTDV AS DELIVERY_DATE
FROM 
    VBAK h
JOIN 
    VBAP i ON h.VBELN = i.VBELN AND h.MANDT = i.MANDT
WHERE 
    h.MANDT = '{MANDT}'
    AND h.VBELN = '{sales_order}';
"""
    },
    {
        "intent": "Get customer-specific material info and pricing conditions",
        "business_use_case": "Check customer-specific pricing before creating a quote",
        "tables": ["KNMT", "KONP"],
        "sql": """
SELECT 
    m.KUNNR AS CUSTOMER_ID,
    m.MATNR AS MATERIAL_ID,
    m.KDMAT AS CUSTOMER_MATERIAL,
    m.KPEIN AS CONDITION_RECORD,
    p.KSCHL AS CONDITION_TYPE,
    p.KBETR AS CONDITION_VALUE,
    p.KMEIH AS CONDITION_UNIT
FROM 
    KNMT m
JOIN 
    KONP p ON m.KPEIN = p.KNUMH
WHERE 
    m.MANDT = '{MANDT}'
    AND m.KUNNR = '{customer_id}'
    AND m.MATNR = '{material_id}';
"""
    },
    {
        "intent": "Find sales orders by customer and date range",
        "business_use_case": "Historical sales review for a customer",
        "tables": ["VBAK", "VBAP"],
        "sql": """
SELECT 
    h.VBELN AS SALES_ORDER,
    h.ERDAT AS ORDER_DATE,
    h.KUNAG AS CUSTOMER,
    i.POSNR AS ITEM,
    i.MATNR AS MATERIAL,
    i.KWMENG AS QUANTITY,
    i.NETWR AS ORDER_VALUE
FROM 
    VBAK h
JOIN 
    VBAP i ON h.VBELN = i.VBELN AND h.MANDT = i.MANDT
WHERE 
    h.MANDT = '{MANDT}'
    AND h.KUNAG = '{customer_id}'
    AND h.ERDAT BETWEEN '{start_date}' AND '{end_date}'
ORDER BY 
    h.ERDAT DESC;
"""
    },
    {
        "intent": "Get shipping conditions and route determination for a sales order",
        "business_use_case": "Review delivery logistics for order fulfillment",
        "tables": ["VBAK", "LIKP"],
        "sql": """
SELECT 
    v.VBELN AS DELIVERY_NUMBER,
    v.KUNNR AS DELIVERY_RECIPIENT,
    v.VSTEL AS SHIPPING_POINT,
    v.ROUTE AS ROUTE_CODE,
    v.LDDAT AS LOADING_DATE,
    v.WADAT AS GOODS_ISSUE_DATE,
    v.KUNAG AS ORDER_CUSTOMER
FROM 
    LIKP v
WHERE 
    v.MANDT = '{MANDT}'
    AND v.VBELN = '{delivery_document}';
"""
    },
    {
        "intent": "Get sales district and partner function assignments for a customer",
        "business_use_case": "Determine sales organization and distribution channel assignments",
        "tables": ["KNVP"],
        "sql": """
SELECT 
    KUNNR AS CUSTOMER_ID,
    VKORG AS SALES_ORG,
    VTWEG AS DIST_CHANNEL,
    SPART AS DIVISION,
    KUNNR AS PARTNER_NUMBER,
    PARVW AS PARTNER_TYPE,
    LIFNR AS VENDOR_IF_AGENT
FROM 
    KNVP
WHERE 
    MANDT = '{MANDT}'
    AND KUNNR = '{customer_id}';
"""
    }
]


# ============================================================================
# 5. WAREHOUSE MANAGEMENT (WM/EWM) — Storage Bins, HU, Transfers
# ============================================================================

WAREHOUSE_MANAGEMENT_PATTERNS = [
    {
        "intent": "Get storage bin location details",
        "business_use_case": "Locate specific materials in warehouse",
        "tables": ["LAGP", "MARD"],
        "sql": """
SELECT 
    l.LGNUM AS WAREHOUSE_NO,
    l.LGTYP AS STORAGE_TYPE,
    l.LGPLA AS STORAGE_BIN,
    l.KOORA AS BIN_COORD_A,
    l.KOORB AS BIN_COORD_B,
    l.KOORC AS BIN_COORD_C,
    s.MATNR AS MATERIAL_ID,
    s.LGORT AS STORAGE_LOCATION,
    s.LABST AS QUANTITY
FROM 
    LAGP l
LEFT JOIN 
    MARD s ON l.LGNUM = s.LGNUM AND l.LGTYP = s.LGTYP AND l.LGPLA = s.LGORT
WHERE 
    l.MANDT = '{MANDT}'
    AND l.LGNUM = '{warehouse_number}'
    AND l.LGTYP = '{storage_type}'
    AND l.LGPLA = '{storage_bin}';
"""
    },
    {
        "intent": "Get handling unit contents and hierarchy",
        "business_use_case": "Check what items are packed in a handling unit",
        "tables": ["VEKP", "V EPO"],
        "sql": """
SELECT 
    h.VENUM AS HU_NUMBER,
    h.EXIDV AS EXTERNAL_ID,
    h.HUTYPE AS HU_TYPE,
    h.UEVEL AS PARENT_HU,
    i.VEPOS AS ITEM_NO,
    i.MATNR AS MATERIAL_ID,
    i.NEUAL AS ALT_UNIT,
    i.NEMNG AS QUANTITY
FROM 
    VEKP h
LEFT JOIN 
    VEPO i ON h.VENUM = i.VENUM AND h.MANDT = i.MANDT
WHERE 
    h.MANDT = '{MANDT}'
    AND h.VENUM = '{handling_unit}';
"""
    },
    {
        "intent": "Get stock in warehouse management versus plant storage location",
        "business_use_case": "Reconcile WM-level and IM-level inventory",
        "tables": ["LQUA", "MARD"],
        "sql": """
SELECT 
    q.MATNR AS MATERIAL_ID,
    q.LGNUM AS WAREHOUSE_NO,
    q.BWLVS AS MOVEMENT_TYPE,
    q.VERID AS PRODUCTION_VERSION,
    q.GMANG AS QUANTITY,
    m.MLABS AS WM_UNRESTRICTED,
    m.LABST AS IM_UNRESTRICTED
FROM 
    LQUA q
JOIN 
    MARD m ON q.MATNR = m.MATNR AND q.MANDT = m.MANDT
WHERE 
    q.MANDT = '{MANDT}'
    AND q.MATNR = '{material_id}'
    AND q.LGNUM = '{warehouse_number}';
"""
    },
    {
        "intent": "Find transfer orders for goods movement",
        "business_use_case": "Track stock transfers between warehouse locations",
        "tables": ["LTBK", "LTAK"],
        "sql": """
SELECT 
    b.BANFN AS REQUISITION,
    k.TANUM AS TRANSFER_ORDER,
    k.BWLVS AS MOVEMENT_TYPE,
    k.DATUM AS POSTING_DATE,
    p.PLNBE AS FROM_STORAGE_BIN,
    p.NLPLA AS TO_STORAGE_BIN,
    p.MATNR AS MATERIAL_ID,
    p.GMENG AS QUANTITY
FROM 
    LTBK b
JOIN 
    LTAK k ON b.TANUM = k.TANUM AND b.MANDT = k.MANDT
JOIN 
    LTAP p ON k.TANUM = p.TANUM AND k.MANDT = p.MANDT
WHERE 
    k.MANDT = '{MANDT}'
    AND k.TANUM = '{transfer_order}';
"""
    }
]


# ============================================================================
# 6. QUALITY MANAGEMENT (QM) — Inspection Plans, Lots, Characteristics
# ============================================================================

QUALITY_MANAGEMENT_PATTERNS = [
    {
        "intent": "Get inspection lot details and status",
        "business_use_case": "Review quality inspection status for received goods",
        "tables": ["QALS", "QMEL"],
        "sql": """
SELECT 
    l.LOTNUMBER AS INSPECTION_LOT,
    l.MATNR AS MATERIAL_ID,
    l.WERKS AS PLANT,
    l.ART AS INSPECTION_TYPE,
    l.STAT AS LOT_STATUS,
    l.QWDAT AS INSPECTION_DATE,
    l.ERSTDAT AS START_DATE,
    l.ENDDAT AS COMPLETION_DATE,
    l.URSACH AS DEFECT_CODE,
    e.MNGWA AS INSPECTED_QTY,
    e.MGEIG AS ACCEPTED_QTY,
    e.MGEIN AS REJECTED_QTY
FROM 
    QALS l
LEFT JOIN 
    QMEL e ON l.LOTNUMBER = e.LOTNUMBER AND l.MANDT = e.MANDT
WHERE 
    l.MANDT = '{MANDT}'
    AND l.LOTNUMBER = '{inspection_lot}';
"""
    },
    {
        "intent": "Get inspection plan master data for a material",
        "business_use_case": "View the defined inspection plan before execution",
        "tables": ["MAPL", "PLMK", "PLPO"],
        "sql": """
SELECT 
    m.MATNR AS MATERIAL_ID,
    m.WERKS AS PLANT,
    m.PLNNR AS PLAN_GROUP,
    m.PLNTY AS PLAN_TYPE,
    p.PLNME AS PLAN_DESCRIPTION,
    p.ART AS INSPECTION_TYPE,
    o.VORNR AS OPERATIONS_SEQ,
    o.ARBPL AS WORK_CENTER,
    o.STEUS AS CONTROL_KEY,
    o.MGEIG AS INSPECTION_QTY_SAMPLE
FROM 
    MAPL m
JOIN 
    PLMK p ON m.PLNNR = p.PLNNR AND m.PLNTY = p.PLNTY AND m.MANDT = p.MANDT
JOIN 
    PLPO o ON p.PLNNR = o.PLNNR AND p.PLNKN = o.PLNKN AND p.MANDT = o.MANDT
WHERE 
    m.MANDT = '{MANDT}'
    AND m.MATNR = '{material_id}'
    AND m.WERKS = '{plant_id}';
"""
    },
    {
        "intent": "Get usage decision for an inspection lot",
        "business_use_case": "Determine if lot was accepted or rejected",
        "tables": ["QALS", "QMSV"],
        "sql": """
SELECT 
    l.LOTNUMBER AS INSPECTION_LOT,
    l.MATNR AS MATERIAL_ID,
    l.ART AS INSPECTION_TYPE,
    l.STAT AS STATUS,
    CASE l.FSOKD 
        WHEN 'R' THEN 'REJECTED' 
        WHEN 'A' THEN 'ACCEPTED' 
        ELSE 'PENDING' 
    END AS USAGE_DECISION,
    l.QWDAT AS DECISION_DATE,
    l.VERAN AS DECISION_CODE,
    v.VDATU AS COMPLETION_DATE
FROM 
    QALS l
LEFT JOIN 
    QMSV v ON l.LOTNUMBER = v.QALSQMSV_QALS AND l.MANDT = v.MANDT
WHERE 
    l.MANDT = '{MANDT}'
    AND l.LOTNUMBER = '{inspection_lot}';
"""
    },
    {
        "intent": "Get defect recording and codes for a quality notification",
        "business_use_case": "Document and track quality issues with root cause",
        "tables": ["QMFE", "QMMA"],
        "sql": """
SELECT 
    f.DOKNR AS NOTIFICATION_NO,
    f.FENUM AS DEFECT_ITEM,
    f.MNGFO AS DEFECT_QTY,
    f.MSEHT AS DEFECT_TEXT,
    f.URFZN AS DEFECT_CODE_GROUP,
    f.URFZN AS DEFECT_CODE,
    m.MNCOD AS DAMAGE_CODE,
    m.MNSTR AS DAMAGE_SHORT_TEXT,
    m.MNZEF AS RESPONSIBLE_PARTY
FROM 
    QMFE f
LEFT JOIN 
    QMMA m ON f.DOKNR = m.DOKNR AND f.FENUM = m.FENUM AND f.MANDT = m.MANDT
WHERE 
    f.MANDT = '{MANDT}'
    AND f.DOKNR = '{notification_number}';
"""
    }
]


# ============================================================================
# 7. PROJECT SYSTEM (PS) — WBS, Networks, Milestones
# ============================================================================

PROJECT_SYSTEM_PATTERNS = [
    {
        "intent": "Get Work Breakdown Structure element details",
        "business_use_case": "Display project structure for Earned Value analysis",
        "tables": ["PRPS", "PROJ"],
        "sql": """
SELECT 
    p.POSID AS WBS_ELEMENT,
    p.POST1 AS WBS_DESCRIPTION,
    p.PROJN AS PROJECT_DEFINITION,
    p.PAOBJNR AS CO_OBJECT_NUMBER,
    p.PSPHI AS SUPERIOR_WBS,
    p.STATE AS WBS_STATUS,
    p.PERIV AS fiscal_YEAR_VARIANT,
    p.GSBER AS BUSINESS_AREA,
    p.ABTNR AS DEPARTMENT,
    p.RECID AS RECOVERY_INDICATOR
FROM 
    PRPS p
WHERE 
    p.MANDT = '{MANDT}'
    AND p.POSID = '{wbs_element}';
"""
    },
    {
        "intent": "Get project definition header with billing and funding data",
        "business_use_case": "Review project-level budget and milestone billing",
        "tables": ["PROJ"],
        "sql": """
SELECT 
    PSPNR AS PROJECT_ID,
    POSID AS PROJECT_DEFINITION,
    POST1 AS PROJECT_DESCRIPTION,
    VERID AS LEAD_PRODUCTION_VERSION,
    WERKS AS PLANT,
    AUTYP AS AUTHORIZATION_GROUP,
    AMPTL AS LOW_VALUE_RESERVE,
    PRCTR AS PROFIT_CENTER,
    KUNNR AS CUSTOMER,
    BUKRS AS COMPANY_CODE
FROM 
    PROJ
WHERE 
    MANDT = '{MANDT}'
    AND POSID = '{project_definition}';
"""
    },
    {
        "intent": "Get network activities and work center assignments",
        "business_use_case": "Track production or maintenance activities in a project",
        "tables": ["AFVC", "CRHD", "MAKT"],
        "sql": """
SELECT 
    n.AUFNR AS NETWORK_NUMBER,
    n.VORNR AS ACTIVITY_NO,
    n.OBJNR AS OBJECT_NUMBER,
    n.ARBID AS WORK_CENTER_ID,
    c.OBJTY AS OBJECT_TYPE,
    c.ARBPL AS WORK_CENTER,
    c.LSTAR AS ACTIVITY_TYPE,
    n.UMREN AS DENOMINATOR,
    n.AMEIN AS BASE_UNIT,
    n.ANZZL AS NUMBER_OF_PEOPLE,
    t.MAKTX AS WORK_CENTER_TEXT
FROM 
    AFVC n
LEFT JOIN 
    CRHD c ON n.ARBID = c.OBJID AND n.MANDT = c.MANDT
LEFT JOIN 
    MAKT t ON c.ARBPL = t.MATNR AND c.MANDT = t.MANDT AND t.SPRAS = 'E'
WHERE 
    n.MANDT = '{MANDT}'
    AND n.AUFNR = '{network_number}';
"""
    },
    {
        "intent": "Get project milestone billing plan",
        "business_use_case": "Track milestone-based revenue recognition",
        "tables": ["PRPS", "VBAK"],
        "sql": """
SELECT 
    p.POSID AS WBS_ELEMENT,
    p.POST1 AS DESCRIPTION,
    p.PERIV AS FISCAL_YEAR_VARIANT,
    p.PSTPR AS ACTUAL_COSTS,
    p.Plan01 AS PLAN_COSTS,
    p.GBSTK AS STATUS_INDICATOR
FROM 
    PRPS p
WHERE 
    p.MANDT = '{MANDT}'
    AND p.PROJN = '{project_definition}';
"""
    }
]


# ============================================================================
# 8. TRANSPORTATION MANAGEMENT (TM) — Shipment, Freight, Routes
# ============================================================================

TRANSPORTATION_PATTERNS = [
    {
        "intent": "Get shipment header and freight unit details",
        "business_use_case": "Track outbound or inbound shipment status",
        "tables": ["VTTK", "VTLP"],
        "sql": """
SELECT 
    h.TDNUM AS SHIPMENT_NUMBER,
    h.TDLNR AS SHP_PARTNER,
    h.WERK AS PLANT,
    h.ROUTE AS ROUTE_CODE,
    h.STATUS AS SHIPMENT_STATUS,
    h.DATBI AS VALID_FROM,
    h.TKUN2 AS DESTINATION_STORAGE_LOC,
    i.TDLNR AS FREIGHT_UNIT_LINE,
    i.MATNR AS MATERIAL_ID,
    i.NOLFA AS NO_OF_HANDLING_UNITS,
    i.BRGEW AS GROSS_WEIGHT,
    i.GEWEI AS WEIGHT_UNIT
FROM 
    VTTK h
JOIN 
    VTLP i ON h.TDNUM = i.TDNUM AND h.MANDT = i.MANDT
WHERE 
    h.MANDT = '{MANDT}'
    AND h.TDNUM = '{shipment_number}';
"""
    },
    {
        "intent": "Get outbound delivery status linked to transportation",
        "business_use_case": "Monitor delivery progress for customer promise",
        "tables": ["LIKP", "VTTK"],
        "sql": """
SELECT 
    l.VBELN AS DELIVERY_NUMBER,
    l.KUNNR AS DELIVERY_RECIPIENT,
    l.VSTEL AS SHIPPING_POINT,
    l.WADAT AS GOODS_ISSUE_DATE,
    l.TDIFNR AS REFERENCE_SHIPMENT,
    t.ROUTE AS TRANSPORTATION_ROUTE,
    t.STATUS AS SHIPMENT_STATUS
FROM 
    LIKP l
LEFT JOIN 
    VTTK t ON l.TDIFNR = t.TDNUM AND l.MANDT = t.MANDT
WHERE 
    l.MANDT = '{MANDT}'
    AND l.VBELN = '{delivery_document}';
"""
    },
    {
        "intent": "Get freight agreement rates for a carrier and route",
        "business_use_case": "Check carrier rates before planning shipment",
        "tables": ["/SCMTMS/D_TORROT", "/SCMTMS/D_TORDR"],
        "sql": """
SELECT 
    r.ROTID AS FREIGHT_ORDER_ID,
    r.DATBI AS VALID_FROM,
    r.DATAB AS VALID_TO,
    r.CARRID AS CARRIER_ID,
    r.ROUTEID AS ROUTE_ID,
    d.CITYFR AS ORIGIN_LOCATION,
    d.CITYTO AS DEST_LOCATION,
    d.DISTANCE AS DISTANCE_KM
FROM 
    /SCMTMS/D_TORROT r
LEFT JOIN 
    /SCMTMS/D_TORDR d ON r.ROTID = d.ROTID AND r.MANDT = d.MANDT
WHERE 
    r.MANDT = '{MANDT}'
    AND r.CARRID = '{carrier_id}';
"""
    }
]


# ============================================================================
# 9. CUSTOMER SERVICE (CS) — Warranties, Service Orders, Contracts
# ============================================================================

CUSTOMER_SERVICE_PATTERNS = [
    {
        "intent": "Get service contract header and coverage",
        "business_use_case": "Review active service contracts for a customer equipment",
        "tables": ["VBAK", "ASMD", "BGMK"],
        "sql": """
SELECT 
    h.VBELN AS CONTRACT_NUMBER,
    h.KUNNR AS CUSTOMER_ID,
    h.ERDAT AS CREATION_DATE,
    h.ERNAM AS CREATED_BY,
    h.VDATU AS START_DATE,
    h.ANNUL AS EXPIRY_DATE,
    m.SERNR AS SERIAL_NUMBER,
    m.MATNR AS EQUIPMENT_ID,
    g.STMNR AS WARRANTY_FROM,
    g.STNDT AS WARRANTY_TO,
    g.QMGRP AS damage_code_GROUP
FROM 
    VBAK h
JOIN 
    ASMD m ON h.VBELN = m.VBELN AND h.MANDT = m.MANDT
LEFT JOIN 
    BGMK g ON m.SERNR = g.SERNR AND m.MANDT = g.MANDT
WHERE 
    h.MANDT = '{MANDT}'
    AND h.VBELN = '{service_contract}';
"""
    },
    {
        "intent": "Get equipment master and installed base data",
        "business_use_case": "Locate installed equipment for field service dispatch",
        "tables": ["EQUI", "ADRC"],
        "sql": """
SELECT 
    e.EQUNR AS EQUIPMENT_NUMBER,
    e.MATNR AS MATERIAL_ID,
    e.SERNR AS SERIAL_NUMBER,
    e.INSTLOCATION AS INSTALLED_AT_LOCATION,
    e.HEQNR AS SUPERIOR_EQUIPMENT,
    e.TIDNR AS TECHNICAL_OBJECT_IDENTIFICATION,
    a.STREET AS INSTALLATION_ADDRESS,
    a.CITY1 AS CITY,
    a.REGION AS REGION
FROM 
    EQUI e
LEFT JOIN 
    ADRC a ON e.ADRNR = a.ADDRNUMBER AND e.MANDT = a.MANDT
WHERE 
    e.MANDT = '{MANDT}'
    AND e.EQUNR = '{equipment_number}';
"""
    },
    {
        "intent": "Get service notification details with problem symptoms",
        "business_use_case": "Document customer complaints and symptom codes",
        "tables": ["QMEL", "QMFE"],
        "sql": """
SELECT 
    n.QMNUM AS NOTIFICATION_NUMBER,
    n.QMART AS NOTIFICATION_TYPE,
    n.ERDAT AS CREATED_ON,
    n.ERNAME AS CREATED_BY,
    n.INSDT AS INSTALLATION_DATE,
    n.TISMH AS SYMPTOM_CODE_GROUP,
    n.QMTXT AS SHORT_TEXT_DESCRIPTION,
    f.URFZN AS DEFECT_CODE_GROUP,
    f.URFZT AS DEFECT_CODE,
    f.MNGFO AS DEFECT_QTY
FROM 
    QMEL n
LEFT JOIN 
    QMFE f ON n.QMNUM = f.DOKNR AND n.MANDT = f.MANDT
WHERE 
    n.MANDT = '{MANDT}'
    AND n.QMNUM = '{notification_number}';
"""
    },
    {
        "intent": "Get task list for preventive maintenance of equipment",
        "business_use_case": "View scheduled maintenance cycles for a piece of equipment",
        "tables": ["IHPA", "PLPO", "CRHD"],
        "sql": """
SELECT 
    p.AUFNR AS MAINTENANCE_ORDER,
    p.PLNTY AS PLAN_TYPE,
    p.PLNNR AS TASK_LIST_GROUP,
    p.ARNDT AS RELEASE_DATE,
    p.ILART AS MAINTENANCE_PLAN_TYPE,
    o.VORNR AS OPERATIONS_SEQ,
    o.ARBPL AS WORK_CENTER,
    o.ANLZU AS ALLOCATION_MEASURE,
    c.VERWE AS WORK_CENTER_CATEGORY
FROM 
    IHPA p
JOIN 
    PLPO o ON p.PLNNR = o.PLNNR AND p.MANDT = o.MANDT
LEFT JOIN 
    CRHD c ON o.ARBID = c.OBJID AND o.MANDT = c.MANDT
WHERE 
    p.MANDT = '{MANDT}'
    AND p.AUFNR = '{maintenance_order}';
"""
    }
]


# ============================================================================
# 10. ENVIRONMENT, HEALTH & SAFETY (EHS) — Substances, DG, Specifications
# ============================================================================

EHS_PATTERNS = [
    {
        "intent": "Get dangerous goods specification for a material",
        "business_use_case": "Check hazmat classification for shipping compliance",
        "tables": ["ESTRH", "MARA"],
        "sql": """
SELECT 
    s.SPUUID AS SPECIFICATION_UUID,
    s.STEXT AS SPEC_DESCRIPTION,
    s.STTYP AS SPEC_TYPE,
    s.STSYS AS SYSTEM_STATUS,
    s.STUSE AS USE_STATUS,
    s.MATNR AS MATERIAL_ID,
    m.MAKTX AS MATERIAL_DESCRIPTION,
    m.MTART AS MATERIAL_TYPE
FROM 
    ESTRH s
JOIN 
    MARA m ON s.MATNR = m.MATNR AND s.MANDT = m.MANDT
WHERE 
    s.MANDT = '{MANDT}'
    AND s.MATNR = '{material_id}';
"""
    },
    {
        "intent": "Get workplace health and safety incident details",
        "business_use_case": "Document and report workplace incidents",
        "tables": ["HSEC", "HSEA"],
        "sql": """
SELECT 
    e.EUUID AS INCIDENT_UUID,
    e.DESCL AS INCIDENT_DESCRIPTION,
    e.OCCDT AS OCCURRENCE_DATE,
    e.RECTP AS RECORDING_TYPE,
    e.RECTY AS RECORD_CATEGORY,
    e.INJTP AS INCIDENT_TYPE,
    a.DOCUUID AS LINKED_DOCUMENT,
    a.RECTY AS DOC_CATEGORY
FROM 
    HSEC e
LEFT JOIN 
    HSEA a ON e.EUUID = a.EUUID AND e.MANDT = a.MANDT
WHERE 
    e.MANDT = '{MANDT}'
    AND e.EUUID = '{incident_uuid}';
"""
    },
    {
        "intent": "Get substance data for hazardous material registration",
        "business_use_case": "Maintain REACH compliance for chemical substances",
        "tables": ["ESTVH", "MARA"],
        "sql": """
SELECT 
    v.SUUID AS SUBSTANCE_UUID,
    v.BEZ50 AS SUBSTANCE_NAME,
    v.CASNR AS CAS_NUMBER,
    v.EINAR AS EINECS_NUMBER,
    v.KEKZR AS REACH_REG_STATUS,
    v.VERIV AS REACH_VERSION,
    m.MATNR AS REFERENCE_MATERIAL,
    m.MAKTX AS MATERIAL_DESC
FROM 
    ESTVH v
LEFT JOIN 
    MARA m ON v.SUUID = m.MATNR AND v.MANDT = m.MANDT
WHERE 
    v.MANDT = '{MANDT}'
    AND v.SUUID = '{substance_uuid}';
"""
    }
]


# ============================================================================
# 11. VARIANT CONFIGURATION (LO-VC) — Configurable Materials, Classes, BOMs
# ============================================================================

VARIANT_CONFIGURATION_PATTERNS = [
    {
        "intent": "Get configurable material dependencies and constraints",
        "business_use_case": "Review variant pricing and dependency rules",
        "tables": ["KLAH", "CABN", "CUOBJ"],
        "sql": """
SELECT 
    c.OBjek AS CONFIGURATION_OBJECT,
    c.MATNR AS MATERIAL_NUMBER,
    c.KLART AS CLASS_TYPE,
    c.CUOBV AS CLASS_BASED_VIEW,
    b.ATINN AS CHARACTERISTIC_INTERNAL,
    b.ATBEZ AS CHARACTERISTIC_NAME,
    b.ATWTB AS CHARACTERISTIC_VALUE_TEXT
FROM 
    CUOBJ c
LEFT JOIN 
    CABN b ON c.KLART = b.KLART AND c.MANDT = b.MANDT
WHERE 
    c.MANDT = '{MANDT}'
    AND c.OBJEK = '{configuration_object}';
"""
    },
    {
        "intent": "Get class and characteristic assignments for a material",
        "business_use_case": "View configuration profile and class assignments",
        "tables": ["INOB", "KLAH", "KLAH"],
        "sql": """
SELECT 
    i.CUOBJ AS CONFIG_OBJECT,
    i.MATNR AS MATERIAL_ID,
    i.OBJEK AS OBJECT_INTERNAL_ID,
    k.KLART AS CLASS_TYPE,
    k.CLASS AS CLASS_NUMBER,
    k.KLBEZ AS CLASS_DESCRIPTION
FROM 
    INOB i
JOIN 
    KLAH k ON i.CLASS = k.KLASS AND i.KLART = k.KLART AND i.MANDT = k.MANDT
WHERE 
    i.MANDT = '{MANDT}'
    AND i.MATNR = '{material_id}';
"""
    },
    {
        "intent": "Get BOM explosion for a configurable material at a plant",
        "business_use_case": "Determine components required for a specific configuration",
        "tables": ["STPO", "MAST", "MARA"],
        "sql": """
SELECT 
    b.STLTY AS BOM_ITEM_CATEGORY,
    b.STLNR AS BOM_NUMBER,
    b.STLKN AS BOM_ITEM_NODE,
    b.IDNRK AS COMPONENT_NUMBER,
    b.MENGE AS QUANTITY,
    b.MEINS AS UNIT_OF_MEASURE,
    b.POSTP AS ITEM_CATEGORY_GROUP,
    m.MAKTX AS COMPONENT_DESCRIPTION,
    m.MTART AS COMPONENT_TYPE
FROM 
    STPO b
JOIN 
    MAST a ON b.STLNR = a.STLNR AND b.STLTY = a.STLTY AND b.MANDT = a.MANDT
JOIN 
    MARA m ON b.IDNRK = m.MATNR AND b.MANDT = m.MANDT
WHERE 
    b.MANDT = '{MANDT}'
    AND a.STLNR = '{bom_number}'
    AND a.WERKS = '{plant_id}';
"""
    }
]


# ============================================================================
# 12. REAL ESTATE MANAGEMENT (RE-FX) — Contracts, Properties, Units
# ============================================================================

REAL_ESTATE_PATTERNS = [
    {
        "intent": "Get real estate contract master data",
        "business_use_case": "Review lease terms and contract parties",
        "tables": ["VICNCN", "VIMAK"],
        "sql": """
SELECT 
    c.CONCR AS CONTRACT_NUMBER,
    c.PAYTY AS PAYMENT_TYPE,
    c.SPLIT AS SPLIT_INDICATOR,
    c.DATAB AS CONTRACT_START,
    c.DATBI AS CONTRACT_END,
    c.VTREP AS RENT_PAYMENT_TERM,
    c.KALEK AS LEASE_CONDITIONS,
    a.OBJNR AS OBJECT_NUMBER,
    a.DESKN AS SHORT_DESCRIPTION,
    a.ADRNR AS ADDRESS_NUMBER
FROM 
    VICNCN c
LEFT JOIN 
    VIMAK a ON c.MANDT = a.MANDT AND c.OBJNR = a.OBJNR
WHERE 
    c.MANDT = '{MANDT}'
    AND c.CONCR = '{contract_number}';
"""
    },
    {
        "intent": "Get real estate master data and classification",
        "business_use_case": "Property inventory and classification",
        "tables": ["IFLOT", "VIBDAO"],
        "sql": """
SELECT 
    f.TPLNR AS FUNCTIONAL_LOCATION,
    f.STRMN AS LOCATION_DESCRIPTION,
    f.BUKRS AS COMPANY_CODE,
    f.HEqui AS EQUIPMENT_LINK,
    b.OBJNR AS BUSINESS_OBJECT,
    b.USR00 AS USER_DEFINED_FIELD,
    b.TXV01 AS TEXT_FIELD_1
FROM 
    IFLOT f
LEFT JOIN 
    VIBDAO b ON f.TPLNR = b.TPLNR AND f.MANDT = b.MANDT
WHERE 
    f.MANDT = '{MANDT}'
    AND f.TPLNR LIKE '{functional_location}%';
"""
    },
    {
        "intent": "Get rent calculation and cost distribution for a property",
        "business_use_case": "Monthly rent accrual and cost center allocation",
        "tables": ["VIBDRO", "VICNCN"],
        "sql": """
SELECT 
    r.DOCNR AS RENT_DOCUMENT_NO,
    r.RCRID AS RENT_RECORD_ID,
    r.RCDAT AS RENT_RECORD_DATE,
    r.BETRH AS RENT_AMOUNT,
    r.WAERS AS CURRENCY,
    r.KOSTL AS COST_CENTER,
    r.PERIO AS ACCOUNTING_PERIOD,
    c.CONCR AS CONTRACT_REFERENCE,
    c.DATAB AS LEASE_START,
    c.DATBI AS LEASE_END
FROM 
    VIBDRO r
JOIN 
    VICNCN c ON r.CONCR = c.CONCR AND r.MANDT = c.MANDT
WHERE 
    r.MANDT = '{MANDT}'
    AND r.DOCNR = '{rent_document}';
"""
    }
]


# ============================================================================
# 13. GLOBAL TRADE SERVICES (GTS) — Compliance, Sanctioned Parties, Customs
# ============================================================================

GTS_PATTERNS = [
    {
        "intent": "Check sanctioned party list screening result for a vendor",
        "business_use_case": "Legal compliance check before engaging a new vendor",
        "tables": ["/SAPSLL/PNTPR", "/SAPSLL/PR"],
        "sql": """
SELECT 
    p.PNTID AS PARTY_ID,
    p.PARTY_NAME AS PARTY_NAME,
    p.PARTY_TYPE AS PARTY_TYPE,
    p.COUNTRY AS COUNTRY,
    p.LIFNR AS VENDOR_REFERENCE,
    p.STATUS AS SCREENING_RESULT,
    p.SCRDT AS SCREENING_DATE,
    p.SYSTM AS SOURCE_SYSTEM,
    r.PRNAME1 AS MATCHED_NAME,
    r.PRCITY AS MATCHED_CITY,
    r.PRCOUN AS MATCHED_COUNTRY
FROM 
    /SAPSLL/PNTPR p
LEFT JOIN 
    /SAPSLL/PR r ON p.PNTID = r.PNTID AND p.MANDT = r.MANDT
WHERE 
    p.MANDT = '{MANDT}'
    AND p.LIFNR = '{vendor_id}';
"""
    },
    {
        "intent": "Get customs import/export declaration status",
        "business_use_case": "Track customs clearance for cross-border shipments",
        "tables": ["/SAPSLL/DECLHEAD", "/SAPSLL/DECLITEM"],
        "sql": """
SELECT 
    h.DECL_UUID AS CUSTOMS_DECLARATION,
    h.PROFILE AS CUSTOMS_PROFILE,
    h.DECL_TYPE AS DECLARATION_TYPE,
    h.REPIN AS REP_INDICATOR,
    h.CUCAT AS CUSTOMS_CATEGORY,
    h.DECL_DATE AS DECLARATION_DATE,
    h.REEL_NO AS ENTRY_NUMBER,
    i.ITEM_NO AS LINE_ITEM,
    i.GOODS_DESCRIPTION AS ITEM_DESCRIPTION,
    i.HERKL AS COUNTRY_OF_ORIGIN,
    i.NET_WEIGHT AS ITEM_NET_WEIGHT
FROM 
    /SAPSLL/DECLHEAD h
JOIN 
    /SAPSLL/DECLITEM i ON h.DECL_UUID = i.DECL_UUID AND h.MANDT = i.MANDT
WHERE 
    h.MANDT = '{MANDT}'
    AND h.REEL_NO = '{customs_entry_number}';
"""
    }
]


# ============================================================================
# 14. IS-OIL (Oil & Gas Industry) — Tank Data, JVA, Silo Management
# ============================================================================

IS_OIL_PATTERNS = [
    {
        "intent": "Get tank or silo inventory data for a storage location",
        "business_use_case": "Tank gauging and custody transfer measurement",
        "tables": ["OIB_A04", "OIG_V"],
        "sql": """
SELECT 
    t.TANK_ID AS TANK_NUMBER,
    t.TANK_NAME AS TANK_DESCRIPTION,
    t.SITE_ID AS REFINERY_PLANT,
    t.PROD_CODE AS PRODUCT_CODE,
    v.MEASUREMENT_UUID AS MEASUREMENT_RECORD,
    v.MEASURED_VOLUME AS VOLUME,
    v.DENSITY AS DENSITY,
    v.TEMP AS TEMPERATURE,
    v.MEASURED_DATE AS GAUGING_DATE
FROM 
    OIB_A04 t
LEFT JOIN 
    OIG_V v ON t.TANK_ID = v.TANK_ID AND t.MANDT = v.MANDT
WHERE 
    t.MANDT = '{MANDT}'
    AND t.TANK_ID = '{tank_number}';
"""
    },
    {
        "intent": "Get joint venture accounting allocation share for a business partner",
        "business_use_case": "JVA cost and revenue allocation between partners",
        "tables": ["T8JV", "LFA1"],
        "sql": """
SELECT 
    j.JV_CODE AS JOINT_VENTURE_CODE,
    j.PARTNER AS PARTNER_ACCOUNT,
    j.ALLOC_SHARE AS PARTICIPATION_PERCENTAGE,
    j.COST_CENTER AS JV_COST_CENTER,
    j.REV_CENTER AS JV_REVENUE_CENTER,
    l.NAME1 AS PARTNER_NAME,
    l.LAND1 AS PARTNER_COUNTRY
FROM 
    T8JV j
JOIN 
    LFA1 l ON j.PARTNER = l.LIFNR AND j.MANDT = l.MANDT
WHERE 
    j.MANDT = '{MANDT}'
    AND j.JV_CODE = '{jv_code}';
"""
    },
    {
        "intent": "Get pipeline and transfer order status for crude or product",
        "business_use_case": "Track custody transfer movements between facilities",
        "tables": ["OIB_P01", "OIG_TRORD"],
        "sql": """
SELECT 
    p.TR_ORDER AS TRANSFER_ORDER,
    p.PIPE_SEGMENT AS PIPELINE_SEGMENT,
    p.MATERIAL AS PRODUCT,
    p.QTY_TRANSFER AS TRANSFERRED_QUANTITY,
    p.STATUS AS ORDER_STATUS,
    p.RECEIVER_ID AS RECEIVING_FACILITY,
    t.TR_ORDER AS LINKED_TRANSFER,
    t.GM_DATE AS MOVEMENT_DATE
FROM 
    OIB_P01 p
LEFT JOIN 
    OIG_TRORD t ON p.TR_ORDER = t.TR_ORDER AND p.MANDT = t.MANDT
WHERE 
    p.MANDT = '{MANDT}'
    AND p.TR_ORDER = '{transfer_order}';
"""
    }
]


# ============================================================================
# 15. IS-RETAIL (Retail Industry) — Articles, Assortments, Site Master
# ============================================================================

IS_RETAIL_PATTERNS = [
    {
        "intent": "Get article master extension for retail-specific attributes",
        "business_use_case": "Access retail-specific buying and logistics views",
        "tables": ["MARA", "WRS1"],
        "sql": """
SELECT 
    m.MATNR AS ARTICLE_NUMBER,
    m.MTART AS ARTICLE_TYPE,
    m.MAKTX AS ARTICLE_DESCRIPTION,
    m.MEINS AS BASE_UNIT,
    w.BZIRK AS PURCHASING_DISTRICT,
    w.EKWSL AS PURCHASING_STATUS,
    w.WHDRT AS DELIVERY_PLANT,
    w.MINLS AS MINIMUM_LOT_SIZE,
    w.MAXLS AS MAXIMUM_LOT_SIZE,
    w.LOTEX AS LOT_SIZE_FIXED,
    w.LOHI AS LOT_SIZE_FROM_TO
FROM 
    MARA m
LEFT JOIN 
    WRS1 w ON m.MATNR = w.MATNR AND m.MANDT = w.MANDT
WHERE 
    m.MANDT = '{MANDT}'
    AND m.MATNR = '{article_number}';
"""
    },
    {
        "intent": "Get site (store/warehouse) master data",
        "business_use_case": "View retail site operational parameters",
        "tables": ["T001W", "ADRC"],
        "sql": """
SELECT 
    w.WERKS AS SITE_NUMBER,
    w.NAME1 AS SITE_NAME,
    w.KUNNR AS RESPONSIBLE_CUSTOMER,
    w.LAND1 AS COUNTRY,
    w.REGIO AS REGION,
    w.CITYC AS CITY_CODE,
    w.TELF1 AS PHONE_NUMBER,
    a.STREET AS STREET_ADDRESS,
    a.POST_CODE1 AS POSTAL_CODE,
    a.CITY1 AS CITY
FROM 
    T001W w
LEFT JOIN 
    ADRC a ON w.ADRNR = a.ADDRNUMBER AND w.MANDT = a.MANDT
WHERE 
    w.MANDT = '{MANDT}'
    AND w.WERKS = '{site_number}';
"""
    },
    {
        "intent": "Get assortment module assignment for retail planning",
        "business_use_case": "Define which articles are assigned to which assortment",
        "tables": ["WRS1", "T001W"],
        "sql": """
SELECT 
    a.ASSORTMENT_MODULE AS ASSORTMENT_ID,
    a.SITE AS STORE_OR_WH,
    a.MATNR AS ARTICLE,
    a.VKORG AS SALES_ORG,
    a.VTWEG AS DISTRIBUTION_CHANNEL,
    a.AUFTY AS ASSIGNMENT_TYPE,
    a.DATAB AS VALID_FROM,
    a.DATBI AS VALID_TO,
    w.NAME1 AS SITE_NAME
FROM 
    WRS1 a
LEFT JOIN 
    T001W w ON a.SITE = w.WERKS AND a.MANDT = w.MANDT
WHERE 
    a.MANDT = '{MANDT}'
    AND a.ASSORTMENT_MODULE = '{assortment_id}';
"""
    }
]


# ============================================================================
# 16. IS-UTILITIES (Utilities Industry) — Devices, Installations, Connections
# ============================================================================

IS_UTILITIES_PATTERNS = [
    {
        "intent": "Get device location and installation history",
        "business_use_case": "Track metering equipment and installation site",
        "tables": ["EGERR", "EVBS"],
        "sql": """
SELECT 
    d.DEVICE_ID AS METER_NUMBER,
    d.SERIAL_NUM AS METER_SERIAL,
    d.DEVICE_GUID AS DEVICE_UUID,
    d.MEAS_POINT AS MEASUREMENT_POINT,
    d.INSTALLATION_DATE AS METER_INSTALL_DATE,
    d.LOC_ROOM AS LOCATION_ROOM,
    d.LOC_BUILDING AS LOCATION_BUILDING,
    v.CONNECTION_OBJECT AS INSTALLATION_POINT,
    v.INT_UI AS INSTALLATION_SEQUENCE,
    v.DATAB AS CONNECTION_START,
    v.DATBI AS CONNECTION_END
FROM 
    EGERR d
LEFT JOIN 
    EVBS v ON d.DEVICE_ID = v.DEVICE_ID AND d.MANDT = v.MANDT
WHERE 
    d.MANDT = '{MANDT}'
    AND d.DEVICE_ID = '{device_number}';
"""
    },
    {
        "intent": "Get installation object master data for a premise",
        "business_use_case": "View utility service connection for a location",
        "tables": ["EANL", "EVBS"],
        "sql": """
SELECT 
    i.INSTALLATION AS INSTALLATION_ID,
    i.ANLAGE AS INSTALLATION_POINT,
    i.SERAPH AS SERVICE_AGREEMENT,
    i.ABLESEART AS METER_READING_TYPE,
    i.VKONTO AS PREMISE_ACCOUNT,
    i.ABLEIN AS INSTALLATION_CATEGORY,
    i.DATAB AS INSTALLATION_START,
    i.DATBI AS INSTALLATION_END,
    v.ELOENR AS LOGICAL_DEVICE_LINK
FROM 
    EANL i
LEFT JOIN 
    EVBS v ON i.ANLAGE = v.ANLAGE AND i.MANDT = v.MANDT
WHERE 
    i.MANDT = '{MANDT}'
    AND i.INSTALLATION = '{installation_id}';
"""
    },
    {
        "intent": "Get connection object and locational address for a premise",
        "business_use_case": "Locate service connection for field operations",
        "tables": ["EVBS", "ADRC"],
        "sql": """
SELECT 
    c.CONNECTION_OBJECT AS CONNECTION_POINT_ID,
    c.STROMH AS ELECTRICITY_INDICATOR,
    c.GAS_IND AS GAS_INDICATOR,
    c.WASS_IND AS WATER_INDICATOR,
    c.HEIZ_IND AS HEATING_INDICATOR,
    c.ADRNR AS ADDRESS_REFERENCE,
    c.LOCATION_GUID AS LOCATION_UUID,
    a.STREET AS SERVICE_ADDRESS,
    a.HOUSE_NUM1 AS HOUSE_NUMBER,
    a.POST_CODE1 AS POSTAL_CODE,
    a.CITY1 AS CITY,
    a.REGION AS STATE
FROM 
    EVBS c
LEFT JOIN 
    ADRC a ON c.ADRNR = a.ADDRNUMBER AND c.MANDT = a.MANDT
WHERE 
    c.MANDT = '{MANDT}'
    AND c.CONNECTION_OBJECT = '{connection_object}';
"""
    }
]


# ============================================================================
# 17. IS-HEALTH (Healthcare Industry) — Patients, Cases, Providers
# ============================================================================

IS_HEALTH_PATTERNS = [
    {
        "intent": "Get patient master data and demographics",
        "business_use_case": "Patient registration and record lookup",
        "tables": ["NPAT", "NBEW"],
        "sql": """
SELECT 
    p.PATNR AS PATIENT_NUMBER,
    p.PERS_NO AS PERSONNEL_NUMBER,
    p.NAME AS PATIENT_NAME,
    p.VNAM AS FIRST_NAME,
    p.GBDAT AS DATE_OF_BIRTH,
    p.GESCHL AS GENDER,
    p.STRAS AS STREET,
    p.PSTLZ AS POSTAL_CODE,
    p.ORT01 AS CITY,
    p.LAND1 AS COUNTRY,
    p.TELF1 AS PHONE_NUMBER,
    e.NBEW1 AS EMERGENCY_CONTACT,
    e.ABWE1 AS CONTACT_RELATIONSHIP
FROM 
    NPAT p
LEFT JOIN 
    NBEW e ON p.PATNR = e.PATNR AND p.MANDT = e.MANDT
WHERE 
    p.MANDT = '{MANDT}'
    AND p.PATNR = '{patient_number}';
"""
    },
    {
        "intent": "Get patient case or visit data with diagnosis coding",
        "business_use_case": "Clinical documentation and billing linkage",
        "tables": ["NPNZ", "NPDZ"],
        "sql": """
SELECT 
    c.CASE_NUMBER AS PATIENT_CASE_ID,
    c.CASE_TYPE AS CASE_TYPE,
    c.PATNR AS PATIENT_NUMBER,
    c.BEGDT AS CASE_START_DATE,
    c.ENDDT AS CASE_END_DATE,
    c.ABRKZ AS CASE_CLOSURE_INDICATOR,
    c.PAYER AS INSURANCE_PAYER,
    d.DGNAG AS DIAGNOSIS_1,
    d.DIAGNOSIS_2 AS DIAGNOSIS_2,
    d.DGGRP AS DIAGNOSIS_GROUP,
    d.ACTION AS CLINICAL_ACTION
FROM 
    NPNZ c
LEFT JOIN 
    NPDZ d ON c.CASE_NUMBER = d.CASE_NUMBER AND c.MANDT = d.MANDT
WHERE 
    c.MANDT = '{MANDT}'
    AND c.CASE_NUMBER = '{case_number}';
"""
    },
    {
        "intent": "Get healthcare provider or hospital department master",
        "business_use_case": "Organizational structure for care delivery units",
        "tables": ["HRP1000", "T001W"],
        "sql": """
SELECT 
    o.OBJID AS ORG_UNIT_ID,
    o.STEXT AS DEPARTMENT_NAME,
    o.SHORTNAME AS SHORT_NAME,
    o.RFCIO AS FUNCTION_CATEGORY,
    o.BEGDA AS VALID_FROM,
    o.ENDDA AS VALID_TO,
    o.PUPWD AS PARENT_UNIT,
    w.WERKS AS PLANT_LINK,
    w.NAME1 AS HOSPITAL_NAME
FROM 
    HRP1000 o
LEFT JOIN 
    T001W w ON o.OBJID = w.WERKS AND o.MANDT = w.MANDT
WHERE 
    o.MANDT = '{MANDT}'
    AND o.OBJID = '{org_unit_id}';
"""
    }
]


# ============================================================================
# 18. INDIA TAXATION (CIN) — GST, HSN/SAC, TDS, Excise
# ============================================================================

INDIA_TAXATION_PATTERNS = [
    {
        "intent": "Get vendor GST registration details for India",
        "business_use_case": "Verify vendor GSTIN before processing invoices",
        "tables": ["LFA1", "J_1IGSTNOTPART"],
        "sql": """
SELECT 
    v.LIFNR AS VENDOR_ID,
    v.NAME1 AS VENDOR_NAME,
    v.STCD1 AS PAN_NUMBER,
    g.GSTIN AS VENDOR_GSTIN,
    g.GSTREG_DATE AS GST_REGISTRATION_DATE,
    g.REGION AS STATE_CODE,
    g.J_1IEXCD AS EXCISE_REGISTRATION,
    g.J_1IECC AS ECC_NUMBER
FROM 
    LFA1 v
LEFT JOIN 
    J_1IGSTNOTPART g ON v.LIFNR = g.LIFNR AND v.MANDT = g.MANDT
WHERE 
    v.MANDT = '{MANDT}'
    AND v.LIFNR = '{vendor_id}';
"""
    },
    {
        "intent": "Get HSN code master for material tax classification",
        "business_use_case": "Determine GST rate and HSN code for materials",
        "tables": ["J_1IGHSNSACMAIN", "MARA"],
        "sql": """
SELECT 
    h.HSN_CODE AS HSN_SAC_CODE,
    h.DESCR AS HSN_DESCRIPTION,
    h.GST_RATE AS APPLICABLE_GST_PERCENT,
    h.Effective_from AS EFFECTIVE_DATE,
    m.MATNR AS MATERIAL_ID,
    m.MAKTX AS MATERIAL_DESCRIPTION
FROM 
    J_1IGHSNSACMAIN h
LEFT JOIN 
    MARA m ON h.MATNR = m.MATNR AND h.MANDT = m.MANDT
WHERE 
    h.MANDT = '{MANDT}'
    AND h.HSN_CODE = '{hsn_code}';
"""
    },
    {
        "intent": "Get GST posting configuration for tax determination",
        "business_use_case": "Set up GST tax codes and account determination",
        "tables": ["J_1IAD", "J_1ISD"],
        "sql": """
SELECT 
    d.TAXCODE AS TAX_CODE,
    d.TAXNAME AS TAX_NAME,
    d.TXCD_S AS SALES_TAX_CODE,
    d.TXCD_P AS PURCHASE_TAX_CODE,
    d.SGST_RATE AS SGST_RATE,
    d.CGST_RATE AS CGST_RATE,
    d.IGST_RATE AS IGST_RATE,
    d.UGST_RATE AS UGST_RATE,
    d.CESS_RATE AS CESS_RATE,
    s.SCODE AS STATE_CODE,
    s.NAME AS STATE_NAME
FROM 
    J_1IAD d
LEFT JOIN 
    J_1ISD s ON d.SCODE = s.SCODE AND d.MANDT = s.MANDT
WHERE 
    d.MANDT = '{MANDT}'
    AND d.TAXCODE = '{tax_code}';
"""
    },
    {
        "intent": "Get e-Way Bill generation details for goods movement",
        "business_use_case": "Track GST e-Way Bill for interstate material transport",
        "tables": ["J_1ISRW", "LIKP"],
        "sql": """
SELECT 
    w.EWAYBILL_NUMBER AS EWAY_BILL_NO,
    w.DOC_NO AS REFERENCE_DOC,
    w.DOC_DATE AS DOCUMENT_DATE,
    w.DIST_FROM AS FROM_STATE,
    w.DIST_TO AS TO_STATE,
    w.TRANSPORTER_ID AS TRANSPORTER_GSTIN,
    w.VEHICLE_NO AS VEHICLE_NUMBER,
    w.DISTANCE_KM AS DISTANCE,
    l.VBELN AS DELIVERY_NUMBER,
    l.KUNNR AS CUSTOMER_GSTIN
FROM 
    J_1ISRW w
LEFT JOIN 
    LIKP l ON w.DOC_NO = l.VBELN AND w.MANDT = l.MANDT
WHERE 
    w.MANDT = '{MANDT}'
    AND w.EWAYBILL_NUMBER = '{ewaybill_number}';
"""
    }
]


# ============================================================================
# MASTER REGISTRY — All Patterns by Domain
# ============================================================================

PATTERNS_BY_DOMAIN = {
    "business_partner": BUSINESS_PARTNER_PATTERNS,
    "material_master": MATERIAL_MASTER_PATTERNS,
    "purchasing": PURCHASING_PATTERNS,
    "sales_distribution": SALES_DISTRIBUTION_PATTERNS,
    "warehouse_management": WAREHOUSE_MANAGEMENT_PATTERNS,
    "quality_management": QUALITY_MANAGEMENT_PATTERNS,
    "project_system": PROJECT_SYSTEM_PATTERNS,
    "transportation": TRANSPORTATION_PATTERNS,
    "customer_service": CUSTOMER_SERVICE_PATTERNS,
    "ehs": EHS_PATTERNS,
    "variant_configuration": VARIANT_CONFIGURATION_PATTERNS,
    "real_estate": REAL_ESTATE_PATTERNS,
    "gts": GTS_PATTERNS,
    "is_oil": IS_OIL_PATTERNS,
    "is_retail": IS_RETAIL_PATTERNS,
    "is_utilities": IS_UTILITIES_PATTERNS,
    "is_health": IS_HEALTH_PATTERNS,
    "taxation_india": INDIA_TAXATION_PATTERNS,
}


def get_all_patterns() -> Dict[str, List[Dict]]:
    """Return all patterns organized by domain."""
    return PATTERNS_BY_DOMAIN


def get_patterns_for_domain(domain: str) -> List[Dict]:
    """Return patterns for a specific domain."""
    return PATTERNS_BY_DOMAIN.get(domain.lower().replace("-", "_"), [])


def get_pattern_count() -> int:
    """Return total count of patterns across all domains."""
    return sum(len(patterns) for patterns in PATTERNS_BY_DOMAIN.values())


# Merge Auto-Generated Patterns if they exist
try:
    _auto_map = {
        "business_partner": globals().get('AUTO_BP_PATTERNS', []) + globals().get('AUTO_FI_PATTERNS', []),
        "material_master": globals().get('AUTO_MM_PATTERNS', []),
        "sales_distribution": globals().get('AUTO_SD_PATTERNS', []),
        "purchasing": globals().get('AUTO_MM_PUR_PATTERNS', []),
        "warehouse_management": globals().get('AUTO_WM_PATTERNS', []),
        "quality_management": globals().get('AUTO_QM_PATTERNS', []),
        "project_system": globals().get('AUTO_PS_PATTERNS', []) + globals().get('AUTO_CO_PATTERNS', []),
        "transportation": globals().get('AUTO_TM_PATTERNS', []),
        "customer_service": globals().get('AUTO_CS_PATTERNS', []) + globals().get('AUTO_PM_PATTERNS', []),
        "variant_configuration": globals().get('AUTO_LO_VC_PATTERNS', []),
        "real_estate": globals().get('AUTO_RE_PATTERNS', []),
        "gts": globals().get('AUTO_GTS_PATTERNS', []),
        "is_oil": globals().get('AUTO_IS_OIL_PATTERNS', []),
        "is_retail": globals().get('AUTO_IS_RETAIL_PATTERNS', []),
        "is_utilities": globals().get('AUTO_IS_UTILITY_PATTERNS', []),
        "is_health": globals().get('AUTO_IS_HEALTH_PATTERNS', []),
        "taxation_india": globals().get('AUTO_TAX_PATTERNS', []),
    }
    for _domain, _patterns in _auto_map.items():
        if _domain in PATTERNS_BY_DOMAIN:
            PATTERNS_BY_DOMAIN[_domain].extend(_patterns)
except Exception as e:
    print(f"Warning: Could not merge auto-generated patterns: {e}")

