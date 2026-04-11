from typing import Dict, List

PROJECT_SYSTEM_TABLES = {
    "PRPS": {
        "description": "Master data table for PS module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "PS"
    }
}

PROJECT_SYSTEM_SQL_PATTERNS = [
    {
        "intent": "Get basic details from PRPS.",
        "sql": """
SELECT * FROM PRPS WHERE ID = '{id}';
"""
    }
]
