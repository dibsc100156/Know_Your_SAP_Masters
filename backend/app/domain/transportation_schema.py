from typing import Dict, List

TRANSPORTATION_TABLES = {
    "VTTK": {
        "description": "Master data table for TM module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "TM"
    }
}

TRANSPORTATION_SQL_PATTERNS = [
    {
        "intent": "Get basic details from VTTK.",
        "sql": """
SELECT * FROM VTTK WHERE ID = '{id}';
"""
    }
]
