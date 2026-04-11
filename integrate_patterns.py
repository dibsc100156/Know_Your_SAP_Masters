"""
Integrate the 406 auto-generated patterns into the main SQL library
"""

import sys
import os

# Add backend to path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
if backend_path not in sys.path:
    sys.path.append(backend_path)

from app.core.sql_patterns.library import PATTERNS_BY_DOMAIN
from app.core.sql_patterns.auto_generated_patterns import (
    AUTO_BP_PATTERNS, AUTO_MM_PATTERNS, AUTO_SD_PATTERNS, 
    AUTO_FI_PATTERNS, AUTO_QM_PATTERNS, AUTO_PS_PATTERNS,
    AUTO_WM_PATTERNS, AUTO_PM_PATTERNS, AUTO_MM_PUR_PATTERNS,
    AUTO_CS_PATTERNS, AUTO_TM_PATTERNS, AUTO_RE_PATTERNS,
    AUTO_GTS_PATTERNS, AUTO_IS_OIL_PATTERNS, AUTO_IS_UTILITY_PATTERNS,
    AUTO_IS_RETAIL_PATTERNS, AUTO_IS_HEALTH_PATTERNS, AUTO_TAX_PATTERNS,
    AUTO_LO_VC_PATTERNS, AUTO_CO_PATTERNS, AUTO_HR_PATTERNS
)

# Map the auto-generated modules to our Domain keys
DOMAIN_MAPPING = {
    "business_partner": AUTO_BP_PATTERNS,
    "material_master": AUTO_MM_PATTERNS,
    "sales_distribution": AUTO_SD_PATTERNS,
    "purchasing": AUTO_MM_PUR_PATTERNS,
    "warehouse_management": AUTO_WM_PATTERNS,
    "quality_management": AUTO_QM_PATTERNS,
    "project_system": AUTO_PS_PATTERNS + AUTO_CO_PATTERNS,
    "transportation": AUTO_TM_PATTERNS,
    "customer_service": AUTO_CS_PATTERNS + AUTO_PM_PATTERNS,
    "variant_configuration": AUTO_LO_VC_PATTERNS,
    "real_estate": AUTO_RE_PATTERNS,
    "gts": AUTO_GTS_PATTERNS,
    "is_oil": AUTO_IS_OIL_PATTERNS,
    "is_retail": AUTO_IS_RETAIL_PATTERNS,
    "is_utilities": AUTO_IS_UTILITY_PATTERNS,
    "is_health": AUTO_IS_HEALTH_PATTERNS,
    "taxation_india": AUTO_TAX_PATTERNS,
    # Map FI to business_partner for now since we don't have a pure FI domain file yet
    "business_partner": AUTO_BP_PATTERNS + AUTO_FI_PATTERNS,
}

print("Starting Pattern Integration...")
original_count = sum(len(p) for p in PATTERNS_BY_DOMAIN.values())
print(f"Original manual patterns: {original_count}")

# Merge them
added = 0
for domain_key, auto_patterns in DOMAIN_MAPPING.items():
    if domain_key in PATTERNS_BY_DOMAIN:
        PATTERNS_BY_DOMAIN[domain_key].extend(auto_patterns)
        added += len(auto_patterns)

new_count = sum(len(p) for p in PATTERNS_BY_DOMAIN.values())
print(f"Successfully integrated {added} auto-generated patterns.")
print(f"New total pattern count: {new_count}")

# Patch the library.py file to import the auto_patterns permanently
library_path = os.path.join(backend_path, 'app', 'core', 'sql_patterns', 'library.py')
with open(library_path, 'r', encoding='utf-8') as f:
    content = f.read()

if 'from .auto_generated_patterns import' not in content:
    print("Patching library.py to include auto-generated patterns permanently...")
    # Add import at the top
    import_stmt = """
# Auto-Generated Pattern Integration
try:
    from .auto_generated_patterns import *
except ImportError:
    pass
"""
    content = content.replace("from typing import Dict, List", f"from typing import Dict, List\n{import_stmt}")
    
    # Append the merge logic at the bottom
    merge_logic = """
# Merge Auto-Generated Patterns if they exist
try:
    _auto_map = {
        "business_partner": globals().get('AUTO_BP_PATTERNS', []) + globals().get('AUTO_FI_PATTERNS', []),
        "material_master": globals().get('AUTO_MM_PATTERNS', []),
        "sales_distribution": globals().get('AUTO_SD_PATTERNS', []),
        "purchasing": globals().get('AUTO_MM_PUR_PATTERNS', []),
        "warehouse_management": globals().get('AUTO_WM_PATTERNS', []),
        "quality_management": globals().get('AUTO_QM_PATTERNS', []),
        "project_system": globals().get('AUTO_PS_PATTERNS', []) + globals().get('AUTO_CO_PATTERNS', []),
        "transportation": globals().get('AUTO_TM_PATTERNS', []),
        "customer_service": globals().get('AUTO_CS_PATTERNS', []) + globals().get('AUTO_PM_PATTERNS', []),
        "variant_configuration": globals().get('AUTO_LO_VC_PATTERNS', []),
        "real_estate": globals().get('AUTO_RE_PATTERNS', []),
        "gts": globals().get('AUTO_GTS_PATTERNS', []),
        "is_oil": globals().get('AUTO_IS_OIL_PATTERNS', []),
        "is_retail": globals().get('AUTO_IS_RETAIL_PATTERNS', []),
        "is_utilities": globals().get('AUTO_IS_UTILITY_PATTERNS', []),
        "is_health": globals().get('AUTO_IS_HEALTH_PATTERNS', []),
        "taxation_india": globals().get('AUTO_TAX_PATTERNS', []),
    }
    for _domain, _patterns in _auto_map.items():
        if _domain in PATTERNS_BY_DOMAIN:
            PATTERNS_BY_DOMAIN[_domain].extend(_patterns)
except Exception as e:
    print(f"Warning: Could not merge auto-generated patterns: {e}")
"""
    content += f"\n{merge_logic}\n"
    
    with open(library_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("library.py patched successfully.")
else:
    print("library.py is already patched.")
