import sys
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')

domain_modules = [
    "business_partner_schema",
    "customer_service_schema",
    "ehs_schema",
    "gts_schema",
    "is_health_schema",
    "is_oil_schema",
    "is_retail_schema",
    "is_utilities_schema",
    "material_master_schema",
    "project_system_schema",
    "purchasing_schema",
    "quality_management_schema",
    "real_estate_schema",
    "sales_distribution_schema",
    "taxation_india_schema",
    "transportation_schema",
    "variant_configuration_schema",
    "warehouse_management_schema",
]

total = 0
for mod_name in domain_modules:
    mod = __import__(f'app.domain.{mod_name}', fromlist=['X'])
    all_attrs = [x for x in dir(mod) if not x.startswith('_')]
    tables_var = next((x for x in all_attrs if x.endswith('_TABLES')), None)
    patterns_var = next((x for x in all_attrs if x.endswith('_SQL_PATTERNS')), None)
    tables = getattr(mod, tables_var, {}) if tables_var else {}
    patterns = getattr(mod, patterns_var, []) if patterns_var else []
    print(f'{mod_name}: {len(tables)} tables, {len(patterns)} patterns')
    total += len(patterns)
print(f'\nTotal patterns across all domains: {total}')
