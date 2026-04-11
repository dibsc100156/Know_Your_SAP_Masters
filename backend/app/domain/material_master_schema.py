from typing import Dict, List

MATERIAL_MASTER_TABLES = {
    "MARA": {
        "description": "General Material Data. Contains core, plant-independent data for materials/products.",
        "columns": [
            {"name": "MATNR", "type": "NVARCHAR(40)", "desc": "Material Number"},
            {"name": "ERSDA", "type": "DATE", "desc": "Created On"},
            {"name": "ERNAM", "type": "NVARCHAR(12)", "desc": "Name of Person who Created the Object"},
            {"name": "MTART", "type": "NVARCHAR(4)", "desc": "Material Type (e.g., ROH, HALB, FERT)"},
            {"name": "MBRSH", "type": "NVARCHAR(1)", "desc": "Industry Sector"},
            {"name": "MATKL", "type": "NVARCHAR(9)", "desc": "Material Group"},
            {"name": "MEINS", "type": "NVARCHAR(3)", "desc": "Base Unit of Measure"},
            {"name": "BRGEW", "type": "DECIMAL(13,3)", "desc": "Gross Weight"},
            {"name": "NTGEW", "type": "DECIMAL(13,3)", "desc": "Net Weight"},
            {"name": "GEWEI", "type": "NVARCHAR(3)", "desc": "Weight Unit"},
        ],
        "primary_keys": ["MATNR"],
        "module": "MM"
    },
    "MAKT": {
        "description": "Material Descriptions. Contains the text descriptions of materials in various languages.",
        "columns": [
            {"name": "MATNR", "type": "NVARCHAR(40)", "desc": "Material Number"},
            {"name": "SPRAS", "type": "NVARCHAR(1)", "desc": "Language Key"},
            {"name": "MAKTX", "type": "NVARCHAR(40)", "desc": "Material description"},
            {"name": "MAKTG", "type": "NVARCHAR(40)", "desc": "Material description in uppercase for matchcodes"},
        ],
        "primary_keys": ["MATNR", "SPRAS"],
        "module": "MM"
    },
    "MARC": {
        "description": "Plant Data for Material. Contains material settings specific to a given plant.",
        "columns": [
            {"name": "MATNR", "type": "NVARCHAR(40)", "desc": "Material Number"},
            {"name": "WERKS", "type": "NVARCHAR(4)", "desc": "Plant"},
            {"name": "PSTAT", "type": "NVARCHAR(15)", "desc": "Maintenance status"},
            {"name": "EKGRP", "type": "NVARCHAR(3)", "desc": "Purchasing Group"},
            {"name": "DISMM", "type": "NVARCHAR(2)", "desc": "MRP Type"},
            {"name": "MINBE", "type": "DECIMAL(13,3)", "desc": "Reorder Point"},
            {"name": "EISBE", "type": "DECIMAL(13,3)", "desc": "Safety Stock"},
            {"name": "LGRAD", "type": "DECIMAL(3,1)", "desc": "Service Level"},
        ],
        "primary_keys": ["MATNR", "WERKS"],
        "module": "MM"
    },
    "MARD": {
        "description": "Storage Location Data for Material. Contains stock levels and settings per storage location.",
        "columns": [
            {"name": "MATNR", "type": "NVARCHAR(40)", "desc": "Material Number"},
            {"name": "WERKS", "type": "NVARCHAR(4)", "desc": "Plant"},
            {"name": "LGORT", "type": "NVARCHAR(4)", "desc": "Storage Location"},
            {"name": "LABST", "type": "DECIMAL(13,3)", "desc": "Valuated Unrestricted-Use Stock"},
            {"name": "UMLME", "type": "DECIMAL(13,3)", "desc": "Stock in transfer (from one storage location to another)"},
            {"name": "INSME", "type": "DECIMAL(13,3)", "desc": "Stock in Quality Inspection"},
        ],
        "primary_keys": ["MATNR", "WERKS", "LGORT"],
        "module": "MM"
    },
    "MBEW": {
        "description": "Material Valuation. Contains pricing, valuation classes, and moving average prices.",
        "columns": [
            {"name": "MATNR", "type": "NVARCHAR(40)", "desc": "Material Number"},
            {"name": "BWKEY", "type": "NVARCHAR(4)", "desc": "Valuation Area"},
            {"name": "BWTAR", "type": "NVARCHAR(10)", "desc": "Valuation Type"},
            {"name": "BKLAS", "type": "NVARCHAR(4)", "desc": "Valuation Class"},
            {"name": "VPRSV", "type": "NVARCHAR(1)", "desc": "Price Control Indicator (V: Moving Avg, S: Standard)"},
            {"name": "VERPR", "type": "DECIMAL(11,2)", "desc": "Moving Average Price/Periodic Unit Price"},
            {"name": "STPRS", "type": "DECIMAL(11,2)", "desc": "Standard price"},
            {"name": "PEINH", "type": "DECIMAL(5,0)", "desc": "Price Unit"},
        ],
        "primary_keys": ["MATNR", "BWKEY", "BWTAR"],
        "module": "MM"
    }
}

MATERIAL_MASTER_SQL_PATTERNS = [
    {
        "intent": "Get basic material details with English description.",
        "sql": """
SELECT 
    m.MATNR, 
    m.MTART, 
    m.MATKL, 
    m.MEINS, 
    t.MAKTX 
FROM 
    MARA m
JOIN 
    MAKT t ON m.MATNR = t.MATNR
WHERE 
    m.MATNR = '{material_id}' 
    AND t.SPRAS = 'E';  -- 'E' for English
"""
    },
    {
        "intent": "Find total unrestricted stock for a material across all storage locations in a specific plant.",
        "sql": """
SELECT 
    MATNR, 
    WERKS, 
    SUM(LABST) as TOTAL_UNRESTRICTED_STOCK
FROM 
    MARD
WHERE 
    MATNR = '{material_id}' 
    AND WERKS = '{plant_id}'
GROUP BY 
    MATNR, 
    WERKS;
"""
    },
    {
        "intent": "Get material valuation, standard price, and moving average price for a valuation area.",
        "sql": """
SELECT 
    MATNR, 
    BWKEY as VALUATION_AREA, 
    BKLAS as VALUATION_CLASS, 
    VPRSV as PRICE_CONTROL, 
    VERPR as MOVING_AVG_PRICE, 
    STPRS as STANDARD_PRICE, 
    PEINH as PRICE_UNIT
FROM 
    MBEW
WHERE 
    MATNR = '{material_id}' 
    AND BWKEY = '{valuation_area}';
"""
    }
]
