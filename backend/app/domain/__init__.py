"""
SAP Master Data Domain Schemas — 18 domains.
Each module exports its table definitions and SQL patterns.

Note: Only domains with real table definitions (not stubs) are exported here.
Stub domains (WM, QM, PS, TM, CS, EHS, LO-VC, RE-FX, GTS, IS-OIL, IS-Retail,
IS-Utilities, IS-Health, Taxation India) have minimal data — do NOT import
their TABLES constants unless you specifically need the single-stub table.
"""

# Fully-populated domain schemas
from app.domain.business_partner_schema import (
    BUSINESS_PARTNER_TABLES,
    BUSINESS_PARTNER_SQL_PATTERNS,
)
from app.domain.material_master_schema import (
    MATERIAL_MASTER_TABLES,
    MATERIAL_MASTER_SQL_PATTERNS,
)
from app.domain.purchasing_schema import (
    PURCHASING_TABLES,
    PURCHASING_SQL_PATTERNS,
)

# Stub domains — import individually if needed
from app.domain import (
    sales_distribution_schema,
    warehouse_management_schema,
    quality_management_schema,
    project_system_schema,
    transportation_schema,
    customer_service_schema,
    ehs_schema,
    variant_configuration_schema,
    real_estate_schema,
    gts_schema,
    is_oil_schema,
    is_retail_schema,
    is_utilities_schema,
    is_health_schema,
    taxation_india_schema,
)

__all__ = [
    # Real domains
    "BUSINESS_PARTNER_TABLES",
    "BUSINESS_PARTNER_SQL_PATTERNS",
    "MATERIAL_MASTER_TABLES",
    "MATERIAL_MASTER_SQL_PATTERNS",
    "PURCHASING_TABLES",
    "PURCHASING_SQL_PATTERNS",
    # Stub domains (available via module import)
    "sales_distribution_schema",
    "warehouse_management_schema",
    "quality_management_schema",
    "project_system_schema",
    "transportation_schema",
    "customer_service_schema",
    "ehs_schema",
    "variant_configuration_schema",
    "real_estate_schema",
    "gts_schema",
    "is_oil_schema",
    "is_retail_schema",
    "is_utilities_schema",
    "is_health_schema",
    "taxation_india_schema",
]
