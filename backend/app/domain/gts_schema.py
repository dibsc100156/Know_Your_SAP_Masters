from typing import Dict, List

GTS_TABLES = {
    "SAPSLL_PNTPR": {
        "description": "Master data table for GTS module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "GTS"
    }
}

GTS_SQL_PATTERNS = [
    {
        "intent": "Get basic details from SAPSLL_PNTPR.",
        "sql": """
SELECT * FROM SAPSLL_PNTPR WHERE ID = '{id}';
"""
    }
]
