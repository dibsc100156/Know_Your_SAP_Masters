from typing import Dict, List

REAL_ESTATE_TABLES = {
    "VICNCN": {
        "description": "Master data table for RE-FX module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "RE-FX"
    }
}

REAL_ESTATE_SQL_PATTERNS = [
    {
        "intent": "Get basic details from VICNCN.",
        "sql": """
SELECT * FROM VICNCN WHERE ID = '{id}';
"""
    }
]
