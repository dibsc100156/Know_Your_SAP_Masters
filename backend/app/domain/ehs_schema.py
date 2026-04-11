from typing import Dict, List

EHS_TABLES = {
    "ESTRH": {
        "description": "Master data table for EHS module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "EHS"
    }
}

EHS_SQL_PATTERNS = [
    {
        "intent": "Get basic details from ESTRH.",
        "sql": """
SELECT * FROM ESTRH WHERE ID = '{id}';
"""
    }
]
