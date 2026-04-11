import re

vector_store_path = r"C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend\app\core\vector_store.py"
with open(vector_store_path, 'r', encoding='utf-8') as f:
    content = f.read()

import_str = '''
from app.domain.sales_distribution_schema import SALES_DISTRIBUTION_TABLES, SALES_DISTRIBUTION_SQL_PATTERNS
from app.domain.warehouse_management_schema import WAREHOUSE_MANAGEMENT_TABLES, WAREHOUSE_MANAGEMENT_SQL_PATTERNS
from app.domain.quality_management_schema import QUALITY_MANAGEMENT_TABLES, QUALITY_MANAGEMENT_SQL_PATTERNS
from app.domain.project_system_schema import PROJECT_SYSTEM_TABLES, PROJECT_SYSTEM_SQL_PATTERNS
from app.domain.transportation_schema import TRANSPORTATION_TABLES, TRANSPORTATION_SQL_PATTERNS
from app.domain.customer_service_schema import CUSTOMER_SERVICE_TABLES, CUSTOMER_SERVICE_SQL_PATTERNS
from app.domain.ehs_schema import EHS_TABLES, EHS_SQL_PATTERNS
from app.domain.variant_configuration_schema import VARIANT_CONFIGURATION_TABLES, VARIANT_CONFIGURATION_SQL_PATTERNS
from app.domain.real_estate_schema import REAL_ESTATE_TABLES, REAL_ESTATE_SQL_PATTERNS
from app.domain.gts_schema import GTS_TABLES, GTS_SQL_PATTERNS
from app.domain.is_oil_schema import IS_OIL_TABLES, IS_OIL_SQL_PATTERNS
from app.domain.is_retail_schema import IS_RETAIL_TABLES, IS_RETAIL_SQL_PATTERNS
from app.domain.is_utilities_schema import IS_UTILITIES_TABLES, IS_UTILITIES_SQL_PATTERNS
from app.domain.is_health_schema import IS_HEALTH_TABLES, IS_HEALTH_SQL_PATTERNS
from app.domain.taxation_india_schema import TAXATION_INDIA_TABLES, TAXATION_INDIA_SQL_PATTERNS
'''

load_str = '''
    def load_all_domains(self):
        \"\"\"Loads all baseline and new Master Data Domains.\"\"\"
        self.load_domain("business_partner", BUSINESS_PARTNER_TABLES, BUSINESS_PARTNER_SQL_PATTERNS)
        self.load_domain("material_master", MATERIAL_MASTER_TABLES, MATERIAL_MASTER_SQL_PATTERNS)
        self.load_domain("purchasing", PURCHASING_TABLES, PURCHASING_SQL_PATTERNS)
        self.load_domain("sales_distribution", SALES_DISTRIBUTION_TABLES, SALES_DISTRIBUTION_SQL_PATTERNS)
        self.load_domain("warehouse_management", WAREHOUSE_MANAGEMENT_TABLES, WAREHOUSE_MANAGEMENT_SQL_PATTERNS)
        self.load_domain("quality_management", QUALITY_MANAGEMENT_TABLES, QUALITY_MANAGEMENT_SQL_PATTERNS)
        self.load_domain("project_system", PROJECT_SYSTEM_TABLES, PROJECT_SYSTEM_SQL_PATTERNS)
        self.load_domain("transportation", TRANSPORTATION_TABLES, TRANSPORTATION_SQL_PATTERNS)
        self.load_domain("customer_service", CUSTOMER_SERVICE_TABLES, CUSTOMER_SERVICE_SQL_PATTERNS)
        self.load_domain("ehs", EHS_TABLES, EHS_SQL_PATTERNS)
        self.load_domain("variant_configuration", VARIANT_CONFIGURATION_TABLES, VARIANT_CONFIGURATION_SQL_PATTERNS)
        self.load_domain("real_estate", REAL_ESTATE_TABLES, REAL_ESTATE_SQL_PATTERNS)
        self.load_domain("gts", GTS_TABLES, GTS_SQL_PATTERNS)
        self.load_domain("is_oil", IS_OIL_TABLES, IS_OIL_SQL_PATTERNS)
        self.load_domain("is_retail", IS_RETAIL_TABLES, IS_RETAIL_SQL_PATTERNS)
        self.load_domain("is_utilities", IS_UTILITIES_TABLES, IS_UTILITIES_SQL_PATTERNS)
        self.load_domain("is_health", IS_HEALTH_TABLES, IS_HEALTH_SQL_PATTERNS)
        self.load_domain("taxation_india", TAXATION_INDIA_TABLES, TAXATION_INDIA_SQL_PATTERNS)
'''

# insert imports
content = content.replace("from app.domain.purchasing_schema import PURCHASING_TABLES, PURCHASING_SQL_PATTERNS", 
                          "from app.domain.purchasing_schema import PURCHASING_TABLES, PURCHASING_SQL_PATTERNS" + import_str)

# insert load_all_domains method (replacing the old one if it exists or adding it)
if "def load_all_domains(self):" in content:
    content = re.sub(r"def load_all_domains\(self\):.*?(\n\s+def|\Z)", load_str.strip() + r"\1", content, flags=re.DOTALL)
else:
    content += "\n" + load_str

with open(vector_store_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Vector store updated.")
