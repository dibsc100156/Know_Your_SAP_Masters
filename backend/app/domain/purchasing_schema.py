from typing import Dict, List

PURCHASING_TABLES = {
    "EKKO": {
        "description": "Purchasing Document Header. Contains document type, vendor, purchasing org, and company code.",
        "columns": [
            {"name": "EBELN", "type": "NVARCHAR(10)", "desc": "Purchasing Document Number (PO Number)"},
            {"name": "BUKRS", "type": "NVARCHAR(4)", "desc": "Company Code"},
            {"name": "BSTYP", "type": "NVARCHAR(1)", "desc": "Purchasing Document Category (F: PO, K: Contract)"},
            {"name": "BSART", "type": "NVARCHAR(4)", "desc": "Purchasing Document Type (e.g., NB for Standard PO)"},
            {"name": "LIFNR", "type": "NVARCHAR(10)", "desc": "Vendor Account Number"},
            {"name": "EKORG", "type": "NVARCHAR(4)", "desc": "Purchasing Organization"},
            {"name": "EKGRP", "type": "NVARCHAR(3)", "desc": "Purchasing Group"},
            {"name": "BEDAT", "type": "DATE", "desc": "Purchasing Document Date"},
        ],
        "primary_keys": ["EBELN"],
        "module": "MM-PUR"
    },
    "EKPO": {
        "description": "Purchasing Document Item. Contains material, quantity, plant, and net price.",
        "columns": [
            {"name": "EBELN", "type": "NVARCHAR(10)", "desc": "Purchasing Document Number"},
            {"name": "EBELP", "type": "NVARCHAR(5)", "desc": "Item Number of Purchasing Document"},
            {"name": "MATNR", "type": "NVARCHAR(40)", "desc": "Material Number"},
            {"name": "WERKS", "type": "NVARCHAR(4)", "desc": "Plant"},
            {"name": "MENGE", "type": "DECIMAL(13,3)", "desc": "Purchase Order Quantity"},
            {"name": "MEINS", "type": "NVARCHAR(3)", "desc": "Purchase Order Unit of Measure"},
            {"name": "NETPR", "type": "DECIMAL(11,2)", "desc": "Net Price in Purchasing Document (in Document Currency)"},
            {"name": "PEINH", "type": "DECIMAL(5,0)", "desc": "Price Unit"},
        ],
        "primary_keys": ["EBELN", "EBELP"],
        "module": "MM-PUR"
    }
}

PURCHASING_SQL_PATTERNS = [
    {
        "intent": "Get Purchase Order header and item details for a specific PO.",
        "sql": """
SELECT 
    h.EBELN, h.BSART, h.LIFNR, h.BEDAT,
    i.EBELP, i.MATNR, i.WERKS, i.MENGE, i.NETPR
FROM 
    EKKO h
JOIN 
    EKPO i ON h.EBELN = i.EBELN
WHERE 
    h.EBELN = '{po_number}';
"""
    },
    {
        "intent": "Find all open purchase orders for a specific vendor and material.",
        "sql": """
SELECT 
    h.EBELN, h.BEDAT, i.EBELP, i.MENGE, i.NETPR
FROM 
    EKKO h
JOIN 
    EKPO i ON h.EBELN = i.EBELN
WHERE 
    h.LIFNR = '{vendor_id}' 
    AND i.MATNR = '{material_id}';
"""
    }
]
