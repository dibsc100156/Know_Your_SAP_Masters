from typing import Dict, List

TAXATION_INDIA_TABLES = {
    "J_1IG_HSN_SAC": {
        "description": "Master data table for CIN module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "CIN"
    }
}

TAXATION_INDIA_SQL_PATTERNS = [
    {
        "intent": "Get basic details from J_1IG_HSN_SAC.",
        "sql": """
SELECT * FROM J_1IG_HSN_SAC WHERE ID = '{id}';
"""
    }
]
