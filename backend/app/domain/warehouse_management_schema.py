from typing import Dict, List

WAREHOUSE_MANAGEMENT_TABLES = {
    "LAGP": {
        "description": "Master data table for WM module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "WM"
    }
}

WAREHOUSE_MANAGEMENT_SQL_PATTERNS = [
    {
        "intent": "Get basic details from LAGP.",
        "sql": """
SELECT * FROM LAGP WHERE ID = '{id}';
"""
    }
]
