from typing import Dict, List

IS_RETAIL_TABLES = {
    "WRS1": {
        "description": "Master data table for IS-R module.",
        "columns": [
            {"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"},
        ],
        "primary_keys": ["ID"],
        "module": "IS-R"
    }
}

IS_RETAIL_SQL_PATTERNS = [
    {
        "intent": "Get basic details from WRS1.",
        "sql": """
SELECT * FROM WRS1 WHERE ID = '{id}';
"""
    }
]
