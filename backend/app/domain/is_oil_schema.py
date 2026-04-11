from typing import Dict, List

IS_OIL_TABLES = {
    "OIB_A04": {
        "description": "Master data table for IS-OIL module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "IS-OIL"
    }
}

IS_OIL_SQL_PATTERNS = [
    {
        "intent": "Get basic details from OIB_A04.",
        "sql": """
SELECT * FROM OIB_A04 WHERE ID = '{id}';
"""
    }
]
