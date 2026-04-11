from typing import Dict, List

IS_UTILITIES_TABLES = {
    "EGERR": {
        "description": "Master data table for IS-U module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "IS-U"
    }
}

IS_UTILITIES_SQL_PATTERNS = [
    {
        "intent": "Get basic details from EGERR.",
        "sql": """
SELECT * FROM EGERR WHERE ID = '{id}';
"""
    }
]
