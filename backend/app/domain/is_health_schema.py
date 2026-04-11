from typing import Dict, List

IS_HEALTH_TABLES = {
    "NPAT": {
        "description": "Master data table for IS-H module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "IS-H"
    }
}

IS_HEALTH_SQL_PATTERNS = [
    {
        "intent": "Get basic details from NPAT.",
        "sql": """
SELECT * FROM NPAT WHERE ID = '{id}';
"""
    }
]
