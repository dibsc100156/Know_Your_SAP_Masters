from typing import Dict, List

CUSTOMER_SERVICE_TABLES = {
    "ASMD": {
        "description": "Master data table for CS module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "CS"
    }
}

CUSTOMER_SERVICE_SQL_PATTERNS = [
    {
        "intent": "Get basic details from ASMD.",
        "sql": """
SELECT * FROM ASMD WHERE ID = '{id}';
"""
    }
]
