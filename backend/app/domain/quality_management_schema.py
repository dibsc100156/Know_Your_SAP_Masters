from typing import Dict, List

QUALITY_MANAGEMENT_TABLES = {
    "MAPL": {
        "description": "Master data table for QM module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "QM"
    }
}

QUALITY_MANAGEMENT_SQL_PATTERNS = [
    {
        "intent": "Get basic details from MAPL.",
        "sql": """
SELECT * FROM MAPL WHERE ID = '{id}';
"""
    }
]
