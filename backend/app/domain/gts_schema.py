from typing import Dict, List

GTS_TABLES = {
    "SAPSLL_PNTPR": {
        "description": "Master data table for GTS Foreign Trade / SAP Global Trade Services.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "GTS"
    },
    # EIGER: Goods-in-Transit (GTS) — not seeded in previous runs (seed_fail_010)
    "EIGER": {
        "description": ("Goods-in-Transit tracking table (GTS). Tracks inbound/outbound shipments "
                        "under customs control. Linked to LFA1 (vendor), EKKO (PO), MKPF (material doc). "
                        "Used by GTS compliance checks and border crossing analytics."),
        "columns": [
            {"name": "GTS_ID", "type": "NVARCHAR(18)", "desc": "GTS internal ID"},
            {"name": "LIFNR", "type": "NVARCHAR(10)", "desc": "Vendor (links to LFA1.LIFNR)"},
            {"name": "EBELN", "type": "NVARCHAR(10)", "desc": "Purchase Order (links to EKKO.EBELN)"},
            {"name": "MBLNR", "type": "NVARCHAR(10)", "desc": "Material Document (links to MKPF.MBLNR)"},
            {"name": "BUDAT", "type": "DATS", "desc": "Posting Date"},
            {"name": "ERDAT", "type": "DATS", "desc": "Created On"},
            {"name": "ERNAM", "type": "NVARCHAR(12)", "desc": "Created By"},
            {"name": "WERKS", "type": "NVARCHAR(4)", "desc": "Plant"},
            {"name": "LGORT", "type": "NVARCHAR(4)", "desc": "Storage Location"},
            {"name": "STATUS", "type": "NVARCHAR(4)", "desc": "GTS Status (in-transit / cleared / blocked)"},
        ],
        "primary_keys": ["GTS_ID"],
        "foreign_keys": [("LIFNR", "LFA1"), ("EBELN", "EKKO")],
        "module": "GTS",
        "domains": ["gts", "quality_management"],
    },
}

GTS_SQL_PATTERNS = [
    {
        "intent": "Get basic details from SAPSLL_PNTPR.",
        "sql": """
SELECT * FROM SAPSLL_PNTPR WHERE ID = '{id}';
"""
    }
]
