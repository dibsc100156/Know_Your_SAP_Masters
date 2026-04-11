from typing import Dict, List

SALES_DISTRIBUTION_TABLES = {
    "KONP": {
        "description": "Master data table for SD module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "SD"
    }
}

SALES_DISTRIBUTION_SQL_PATTERNS = [
    {
        "intent": "Get basic details from KONP.",
        "sql": """
SELECT * FROM KONP WHERE ID = '{id}';
"""
    }
]
