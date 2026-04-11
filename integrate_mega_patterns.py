"""Integrate mega patterns into the SQL Pattern Library and re-seed ChromaDB."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.core.sql_patterns.library import PATTERNS_BY_DOMAIN
from app.core.sql_patterns.mega_generated_patterns import MEGA_PATTERNS

# Map module names to domain keys
MODULE_TO_DOMAIN = {
    "MM":       "material_master",
    "MM-PUR":   "purchasing",
    "BP":       "business_partner",
    "SD":       "sales_distribution",
    "FI":       "business_partner",
    "CO":       "project_system",
    "QM":       "quality_management",
    "WM":       "warehouse_management",
    "PM":       "customer_service",
    "PS":       "project_system",
    "TM":       "transportation",
    "CS":       "customer_service",
    "HR":       "business_partner",
    "RE":       "real_estate",
    "GTS":      "gts",
    "IS-OIL":   "is_oil",
    "IS-UTILITY": "is_utilities",
    "IS-RETAIL": "is_retail",
    "IS-HEALTH": "is_health",
    "TAX":      "taxation_india",
    "LO-VC":    "variant_configuration",
    "AUTO":     "business_partner",
}

added = 0
for p in MEGA_PATTERNS:
    module = p.get("module", "AUTO")
    domain = MODULE_TO_DOMAIN.get(module, "business_partner")
    if domain in PATTERNS_BY_DOMAIN:
        PATTERNS_BY_DOMAIN[domain].append(p)
        added += 1
    else:
        # Fallback to first domain
        for d in PATTERNS_BY_DOMAIN:
            PATTERNS_BY_DOMAIN[d].append(p)
            added += 1
            break

print(f"Added {added} mega patterns to library.")
total = sum(len(v) for v in PATTERNS_BY_DOMAIN.values())
print(f"New total: {total} patterns across {len(PATTERNS_BY_DOMAIN)} domains")

# Save updated count
import json
stats_path = os.path.join(os.path.dirname(__file__),
    'backend', 'app', 'core', 'sql_patterns', 'mega_stats.json')
with open(stats_path, 'w') as f:
    json.dump({
        "total_patterns": total,
        "mega_added": added,
        "domains": {k: len(v) for k, v in PATTERNS_BY_DOMAIN.items()}
    }, f, indent=2)
print(f"Stats saved to {stats_path}")
