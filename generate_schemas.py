import os

domains = {
    "sales_distribution": {"name": "SALES_DISTRIBUTION", "module": "SD", "tables": ["KONP", "KNMT", "TVRO"]},
    "warehouse_management": {"name": "WAREHOUSE_MANAGEMENT", "module": "WM", "tables": ["LAGP", "LQUA", "VEKP"]},
    "quality_management": {"name": "QUALITY_MANAGEMENT", "module": "QM", "tables": ["MAPL", "PLMK", "QINF"]},
    "project_system": {"name": "PROJECT_SYSTEM", "module": "PS", "tables": ["PRPS", "PROJ", "AFVC"]},
    "transportation": {"name": "TRANSPORTATION", "module": "TM", "tables": ["VTTK"]},
    "customer_service": {"name": "CUSTOMER_SERVICE", "module": "CS", "tables": ["ASMD", "BGMK", "VBAK"]},
    "ehs": {"name": "EHS", "module": "EHS", "tables": ["ESTRH", "ESTVH", "DGTMD"]},
    "variant_configuration": {"name": "VARIANT_CONFIGURATION", "module": "LO-VC", "tables": ["CABN", "KLAH", "CUOBJ"]},
    "real_estate": {"name": "REAL_ESTATE", "module": "RE-FX", "tables": ["VICNCN", "VIBDAO", "VIBDRO"]},
    "gts": {"name": "GTS", "module": "GTS", "tables": ["SAPSLL_PNTPR"]},
    "is_oil": {"name": "IS_OIL", "module": "IS-OIL", "tables": ["OIB_A04", "OIG_V", "T8JV"]},
    "is_retail": {"name": "IS_RETAIL", "module": "IS-R", "tables": ["WRS1", "T001W"]},
    "is_utilities": {"name": "IS_UTILITIES", "module": "IS-U", "tables": ["EGERR", "EANL", "EVBS"]},
    "is_health": {"name": "IS_HEALTH", "module": "IS-H", "tables": ["NPAT", "NBEW", "NPNZ"]},
    "taxation_india": {"name": "TAXATION_INDIA", "module": "CIN", "tables": ["J_1IG_HSN_SAC", "J_1BBRANCH"]},
    "purchasing": {"name": "PURCHASING", "module": "MM-PUR", "tables": ["EINA", "EINE", "EORD", "EQUK"]}
}

template = '''from typing import Dict, List

{name}_TABLES = {{
    "{table}": {{
        "description": "Master data table for {module} module.",
        "columns": [
            {{"name": "ID", "type": "NVARCHAR(40)", "desc": "Primary Identifier"}},
        ],
        "primary_keys": ["ID"],
        "module": "{module}"
    }}
}}

{name}_SQL_PATTERNS = [
    {{
        "intent": "Get basic details from {table}.",
        "sql": """
SELECT * FROM {table} WHERE ID = '{{id}}';
"""
    }}
]
'''

base_path = r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\domain"

for file_name, config in domains.items():
    if file_name == "purchasing": continue
    content = template.format(
        name=config["name"],
        module=config["module"],
        table=config["tables"][0]
    )
    with open(os.path.join(base_path, f"{file_name}_schema.py"), "w") as f:
        f.write(content)

print("Created schema files successfully!")
