from typing import Dict, List

VARIANT_CONFIGURATION_TABLES = {
    "CABN": {
        "description": "Master data table for LO-VC module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "LO-VC"
    }
}

VARIANT_CONFIGURATION_SQL_PATTERNS = [
    {
        "intent": "Get basic details from CABN.",
        "sql": """
SELECT * FROM CABN WHERE ID = '{id}';
"""
    }
]
