import json
from typing import List, Dict, Any

# ==============================================================================
# SQL RAG TEMPLATE LIBRARY (SAP S/4 HANA Proven Query Patterns)
# ==============================================================================
# This serves as the initial seed for the SQL RAG knowledge base.
# Each entry contains:
# - Intent / Description: Used for semantic embedding and retrieval.
# - Validated SQL: The proven SAP HANA query pattern with placeholders.
# - Module/Tags: For filtering by SAP functional area.

SQL_RAG_LIBRARY = [
    {
        "query_id": "VND-010",
        "intent_description": "Show all open purchase orders for a vendor. Find pending POs where delivery or invoice is not complete.",
        "natural_language_variants": [
            "What are the open purchase orders for vendor X?",
            "Show me pending POs for supplier Y",
            "List open PO lines for a vendor"
        ],
        "module": "MM",
        "tags": ["vendor", "purchase-order", "open-items", "EKKO", "EKPO"],
        "tables_used": ["EKKO", "EKPO"],
        "sql_template": """
SELECT 
    ekko.EBELN AS po_number, 
    ekko.BEDAT AS po_date, 
    ekpo.EBELP AS line_item, 
    ekpo.MATNR AS material, 
    ekpo.MENGE AS ordered_qty, 
    ekpo.NETPR AS net_price
FROM EKKO ekko
INNER JOIN EKPO ekpo 
    ON ekko.EBELN = ekpo.EBELN 
    AND ekko.MANDT = ekpo.MANDT
WHERE ekko.MANDT = '{client}'
  AND ekko.LIFNR = '{vendor_id}'
  AND ekko.LOEKZ = ''  -- Exclude deleted POs
  AND ekpo.LOEKZ = ''  -- Exclude deleted lines
  AND ekpo.ELIKZ = ''  -- Delivery not completed
ORDER BY ekko.BEDAT DESC
LIMIT {max_rows}
        """
    },
    {
        "query_id": "VND-021",
        "intent_description": "Calculate and show overdue invoices for a specific vendor based on payment terms and baseline date.",
        "natural_language_variants": [
            "Show overdue invoices for company code",
            "What invoices are past due for vendor X?",
            "List late payments for supplier"
        ],
        "module": "FI",
        "tags": ["vendor", "invoice", "overdue", "BSIK", "payment-terms"],
        "tables_used": ["BSIK", "LFA1"],
        "sql_template": """
SELECT
    bsik.LIFNR AS vendor_id,
    lfa1.NAME1 AS vendor_name,
    bsik.BELNR AS document_number,
    bsik.DMBTR AS amount_local,
    bsik.WAERS AS currency,
    bsik.ZFBDT AS baseline_date,
    bsik.ZBD3T AS net_payment_days,
    ADD_DAYS(bsik.ZFBDT, bsik.ZBD3T) AS due_date,
    DAYS_BETWEEN(ADD_DAYS(bsik.ZFBDT, bsik.ZBD3T), CURRENT_DATE) AS days_overdue
FROM BSIK bsik
INNER JOIN LFA1 lfa1 
    ON bsik.LIFNR = lfa1.LIFNR 
    AND bsik.MANDT = lfa1.MANDT
WHERE bsik.MANDT = '{client}'
  AND bsik.BUKRS IN ({allowed_bukrs})
  {vendor_filter} -- e.g. AND bsik.LIFNR = '1000'
  AND ADD_DAYS(bsik.ZFBDT, bsik.ZBD3T) < CURRENT_DATE
  AND bsik.ZLSCH != 'A' -- Exclude blocked for payment
ORDER BY days_overdue DESC
LIMIT {max_rows}
        """
    },
    {
        "query_id": "VND-001",
        "intent_description": "Get general vendor master details including name, address, and block status.",
        "natural_language_variants": [
            "Show vendor details",
            "What is the address of vendor X?",
            "Is vendor Y blocked?"
        ],
        "module": "MDG",
        "tags": ["vendor-master", "LFA1", "address", "block-status"],
        "tables_used": ["LFA1"],
        "sql_template": """
SELECT 
    LIFNR AS vendor_id,
    NAME1 AS vendor_name,
    LAND1 AS country,
    ORT01 AS city,
    SPERR AS posting_block,
    LOEVM AS deletion_flag
FROM LFA1
WHERE MANDT = '{client}'
  {vendor_filter}
        """
    },
    {
        "query_id": "VND-030",
        "intent_description": "Calculate total vendor spend grouped by vendor for a specific time period.",
        "natural_language_variants": [
            "Top vendors by spend",
            "How much did we spend with vendor X last year?",
            "Show total PO value by supplier"
        ],
        "module": "MM",
        "tags": ["vendor", "spend", "aggregation", "EKKO", "EKPO"],
        "tables_used": ["EKKO", "EKPO", "LFA1"],
        "sql_template": """
SELECT 
    ekko.LIFNR AS vendor_id,
    lfa1.NAME1 AS vendor_name,
    COUNT(DISTINCT ekko.EBELN) AS po_count,
    SUM(ekpo.NETWR) AS total_spend_value,
    ekko.WAERS AS currency
FROM EKKO ekko
INNER JOIN EKPO ekpo 
    ON ekko.EBELN = ekpo.EBELN 
    AND ekko.MANDT = ekpo.MANDT
INNER JOIN LFA1 lfa1 
    ON ekko.LIFNR = lfa1.LIFNR 
    AND ekko.MANDT = lfa1.MANDT
WHERE ekko.MANDT = '{client}'
  AND ekko.EKORG IN ({allowed_ekorgs})
  AND ekko.BEDAT >= '{start_date}' 
  AND ekko.BEDAT <= '{end_date}'
  AND ekko.LOEKZ = ''
GROUP BY ekko.LIFNR, lfa1.NAME1, ekko.WAERS
ORDER BY total_spend_value DESC
LIMIT {max_rows}
        """
    }
]

def get_sql_library() -> List[Dict[str, Any]]:
    return SQL_RAG_LIBRARY