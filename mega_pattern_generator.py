"""
Mega Pattern Generator — From 424 Meta-Paths to 2,000+ SQL Patterns
===================================================================
Generates 5 pattern variants per meta-path:
  1. BASE      — Plain SELECT with MANDT filter
  2. FILTERED — With dynamic WHERE parameters (date, org, status)
  3. AGGREGATED — GROUP BY with SUM/COUNT/AVG
  4. TEMPORAL  — Historical slice with fiscal year / date range
  5. CROSS-MODULE — Multi-hop with full JOIN chain (for paths > 1 table)

Outputs to: backend/app/core/sql_patterns/mega_generated_patterns.py
"""

import os
import sys
from collections import defaultdict

backend_path = os.path.join(os.path.dirname(__file__), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.meta_path_library import meta_path_library
from app.core.sql_patterns.auto_meta_paths_v2 import AUTO_META_PATHS_V2


# ─── Filter Param Library ─────────────────────────────────────────────────────

FILTER_PARAMS = {
    # (table, column): (param_name, filter_label, operator)
    ("LFA1",   "LAND1"):   ("country_code",   "Country (LAND1)",            "= :country"),
    ("LFA1",   "KTOKK"):   ("vendor_group",   "Vendor Account Group",        "= :vendor_group"),
    ("LFA1",   "LIFNR"):   ("vendor_id",     "Vendor Code",                 "= :vendor_id"),
    ("KNA1",   "LAND1"):   ("country_code",   "Country",                     "= :country"),
    ("KNA1",   "KDKG1"):   ("cust_group",    "Customer Group",              "= :cust_group"),
    ("KNA1",   "KUNNR"):   ("customer_id",   "Customer Code",                "= :customer_id"),
    ("MARA",   "MTART"):   ("mat_type",      "Material Type",                "= :mat_type"),
    ("MARA",   "MBRSH"):   ("industry",      "Industry Sector",               "= :industry"),
    ("MARA",   "MATKL"):   ("mat_group",     "Material Group",                "= :mat_group"),
    ("MARC",   "WERKS"):   ("plant",         "Plant (WERKS)",                "= :plant"),
    ("MARC",   "DISPO"):   ("mrp_controller","MRP Controller",               "= :mrp_ctrl"),
    ("MARD",   "LGORT"):   ("stor_loc",      "Storage Location",             "= :stor_loc"),
    ("MBEW",   "BWKEY"):   ("valuation_area","Valuation Area",                 "= :val_area"),
    ("EKKO",   "BSART"):   ("po_type",       "PO Type (NB/FO/CO)",           "= :po_type"),
    ("EKKO",   "EKGRP"):   ("pur_group",     "Purchasing Group",              "= :pur_group"),
    ("EKKO",   "BEDAT"):   ("po_date",       "PO Date",                       "BETWEEN :d1 AND :d2"),
    ("EKKO",   "LIFNR"):   ("vendor_id",     "Vendor Code",                   "= :vendor_id"),
    ("VBAK",   "VKORG"):  ("sales_org",     "Sales Organization",            "= :sales_org"),
    ("VBAK",   "AUART"):  ("order_type",    "Order Type (OR/DR/CR)",        "= :order_type"),
    ("VBAK",   "AUDAT"):  ("order_date",    "Order Date",                    "BETWEEN :d1 AND :d2"),
    ("VBAK",   "KUNNR"):  ("customer_id",   "Customer Code",                  "= :customer_id"),
    ("LIKP",   "WADAT"):  ("deliv_date",    "Delivery Date",                  "BETWEEN :d1 AND :d2"),
    ("LIKP",   "LFART"):  ("deliv_type",    "Delivery Type",                  "= :deliv_type"),
    ("VBRK",   "FKDAT"):  ("billing_date",  "Billing Date",                  "BETWEEN :d1 AND :d2"),
    ("VBRK",   "FKURG"):  ("billing_type",   "Billing Type (F2/RE)",          "= :bill_type"),
    ("BKPF",   "BUKRS"):  ("company_code",   "Company Code",                   "= :company_code"),
    ("BKPF",   "BLDAT"):  ("doc_date",      "Document Date",                  "BETWEEN :d1 AND :d2"),
    ("BKPF",   "BKTXT"):  ("doc_text",      "Document Header Text",           "LIKE :doc_text"),
    ("BSEG",   "HKONT"):  ("gl_account",    "G/L Account",                   "= :gl_account"),
    ("BSEG",   "DMBTR"):  ("amount",        "Amount in LC",                   "BETWEEN :amt1 AND :amt2"),
    ("BSIK",   "ZBD1T"):  ("due_days",      "Days Overdue",                   ">= :due_days"),
    ("BSID",   "ZBD1T"):  ("due_days",      "Days Overdue",                   ">= :due_days"),
    ("CSKS",   "KOSTL"):  ("cost_center",   "Cost Center",                    "= :cost_center"),
    ("CSKS",   "KOKRS"):  ("ctrl_area",     "Controlling Area",               "= :ctrl_area"),
    ("QALS",   "WERKS"):  ("plant",         "Plant",                          "= :plant"),
    ("QALS",   "ART"):    ("insp_type",     "Inspection Type",                "= :insp_type"),
    ("QALS",   "QNDAT"):  ("insp_date",     "Inspection Date",                "BETWEEN :d1 AND :d2"),
    ("PRPS",   "PSPID"):  ("project_id",    "Project Definition",             "= :project_id"),
    ("PRPS",   "POSKI"):  ("wbs_name",      "WBS Element",                    "LIKE :wbs_name"),
    ("EQUI",   "TPLNR"):  ("func_loc",      "Functional Location",             "= :func_loc"),
    ("EQUI",   "EQTYP"):  ("equip_type",    "Equipment Type",                  "= :equip_type"),
    ("VTTK",   "TDLNR"):  ("transport",     "Transportation Planner",         "= :transport_id"),
    ("VTTK",   "TSDAT"):  ("ship_date",     "Shipment Date",                   "BETWEEN :d1 AND :d2"),
    ("PA0001", "BUKRS"):  ("company_code",   "Company Code",                   "= :company_code"),
    ("PA0001", "ORGEH"):  ("org_unit",      "Organizational Unit",             "= :org_unit"),
    ("ASMD",   "EDATU"):  ("service_date",  "Service Due Date",               "BETWEEN :d1 AND :d2"),
}


def get_filters_for_table(table: str) -> list:
    """Return applicable filters for a table."""
    return [
        (col, params[0], params[1], params[2])
        for (t, col), params in FILTER_PARAMS.items()
        if t == table
    ]


def get_primary_key_or_col(table: str) -> str:
    """Return a meaningful display column for a table."""
    pk_map = {
        "LFA1":    "LIFNR",    "KNA1":    "KUNNR",    "MARA":    "MATNR",
        "MARC":    "MATNR",    "MARD":    "MATNR",    "MBEW":    "MATNR",
        "EKKO":    "EBELN",    "EKPO":    "EBELN",    "EINA":    "INFNR",
        "VBAK":    "VBELN",    "VBAP":    "VBELN",    "LIKP":    "VBELN",
        "LIPS":    "VBELN",    "VBRK":    "VBELN",    "VBRP":    "VBELN",
        "BKPF":    "BELNR",    "BSEG":    "BELNR",    "BSIK":    "BELNR",
        "BSAK":    "BELNR",    "BSID":    "BELNR",    "SKA1":    "SAKNR",
        "CSKS":    "KOSTL",    "COSP":    "OBJNR",    "COSS":    "OBJNR",
        "QALS":    "QALS",     "QMEL":    "QMNUM",    "PRPS":    "PSPNR",
        "AFVC":    "NPLNR",    "RESB":    "RSNUM",    "EQUI":    "EQUNR",
        "LQUA":    "LENUM",    "LAGP":    "LGTYP",    "VTTK":    "TKNUM",
        "ASMD":    "QMNUM",    "PA0001":  "PERNR",    "ANLA":    "ANLN1",
        "BUT000":  "PARTNER",  "ADRC":    "ADDRNUMBER","T001":    "BUKRS",
        "T001W":   "WERKS",    "T024":    "EKORG",    "KNVV":    "KUNNR",
        "KONV":    "KNUMV",    "A003":    "KAPPL",
    }
    return pk_map.get(table, table.split('_')[0] + '_ID')


# ─── Pattern Variant Generators ────────────────────────────────────────────────

def generate_base_pattern(meta_path: dict) -> dict:
    """Variant 1: Simple SELECT with MANDT filter."""
    tables = meta_path['tables']
    primary = tables[0]
    pk = get_primary_key_or_col(primary)

    if len(tables) == 1:
        sql = f"SELECT *\nFROM {primary}\nWHERE MANDT = :P_MANDT\nLIMIT 100;"
    else:
        joins = []
        for i in range(1, len(tables)):
            t2 = tables[i]
            cond = meta_path.get('join_conditions', [])
            if i-1 < len(cond) and isinstance(cond[i-1], (list, tuple)):
                _, _, c = cond[i-1]
                alias_c = c.replace(f"{tables[0]}.", "a.").replace(f"{tables[i]}.", "b.")
                joins.append(f"LEFT JOIN {t2} ON {alias_c}")
            else:
                joins.append(f"LEFT JOIN {t2} ON {tables[0]}.{pk} = {t2}.{pk}")
        sql = f"SELECT a.*\nFROM {primary} a\n" + "\n".join(joins) + f"\nWHERE a.MANDT = :P_MANDT\nLIMIT 100;"

    return {
        "intent": f"Get {primary} master data",
        "business_use_case": f"Retrieve {primary} records with standard filters",
        "tables": tables,
        "sql": sql,
        "variant": "BASE",
        "module": meta_path.get('module_pair', meta_path.get('module', 'AUTO')),
    }


def generate_filtered_pattern(meta_path: dict) -> dict:
    """Variant 2: SELECT with dynamic filter parameters."""
    tables = meta_path['tables']
    primary = tables[0]
    filters = get_filters_for_table(primary)

    if not filters:
        return None  # Skip if no filter params known

    filter_lines = [f"    {primary}.MANDT = :P_MANDT"]
    for _, param, label, op in filters[:4]:
        filter_lines.append(f"    -- AND {primary}.{param.replace('_','.').upper()} {op.replace(':',' :')}  -- {label}")

    if len(tables) == 1:
        sql = f"SELECT *\nFROM {primary}\nWHERE\n" + "\n".join(filter_lines) + "\nLIMIT 100;"
    else:
        joins = []
        for i in range(1, len(tables)):
            t2 = tables[i]
            cond = meta_path.get('join_conditions', [])
            if i-1 < len(cond) and isinstance(cond[i-1], (list, tuple)):
                _, _, c = cond[i-1]
                alias_c = c.replace(f"{tables[0]}.", "a.").replace(f"{tables[i]}.", "b.")
                joins.append(f"LEFT JOIN {t2} ON {alias_c}")
            else:
                pk = get_primary_key_or_col(primary)
                joins.append(f"LEFT JOIN {t2} ON {primary}.{pk} = {t2}.{pk}")
        sql = f"SELECT a.*\nFROM {primary} a\n" + "\n".join(joins) + "\nWHERE\n" + "\n".join(filter_lines) + "\nLIMIT 100;"

    return {
        "intent": f"Get filtered {primary} data",
        "business_use_case": f"Retrieve {primary} with dynamic filters — {primary} + applicable parameters",
        "tables": tables,
        "sql": sql,
        "variant": "FILTERED",
        "module": meta_path.get('module_pair', meta_path.get('module', 'AUTO')),
    }


def generate_aggregated_pattern(meta_path: dict) -> dict:
    """Variant 3: GROUP BY with COUNT/SUM/AVG."""
    tables = meta_path['tables']
    primary = tables[0]
    pk = get_primary_key_or_col(primary)

    # Pick an aggregation dimension based on primary table
    agg_dimensions = {
        "LFA1":   [("LAND1", "Country"), ("KTOKK", "Vendor Group")],
        "KNA1":   [("LAND1", "Country"), ("KDKG1", "Customer Group")],
        "MARA":   [("MTART", "Material Type"), ("MBRSH", "Industry"), ("MATKL", "Material Group")],
        "MARC":   [("WERKS", "Plant"), ("DISPO", "MRP Controller")],
        "EKKO":   [("LIFNR", "Vendor"), ("EKGRP", "Purchasing Group"), ("BSART", "PO Type")],
        "VBAK":   [("VKORG", "Sales Org"), ("AUART", "Order Type"), ("KUNNR", "Customer")],
        "LIKP":   [("WERKS", "Plant"), ("LFART", "Delivery Type")],
        "VBRK":   [("VKORG", "Sales Org"), ("FKURG", "Billing Type")],
        "BKPF":   [("BUKRS", "Company Code"), ("BLDAT", "Posting Date")],
        "BSEG":   [("HKONT", "G/L Account"), ("BUKRS", "Company Code")],
        "BSIK":   [("LIFNR", "Vendor"), ("BUKRS", "Company Code")],
        "CSKS":   [("KOKRS", "Ctrl Area"), ("DATBI", "Valid To")],
        "QALS":   [("WERKS", "Plant"), ("ART", "Insp Type")],
        "PRPS":   [("PBUKR", "Project Owner")],
        "EQUI":   [("TPLNR", "Functional Loc"), ("EQTYP", "Equip Type")],
    }

    dims = agg_dimensions.get(primary, [(pk, primary)])
    dim_col, dim_label = dims[0]

    agg_sql = f"""SELECT
    {primary}.{dim_col}          AS {dim_label.lower().replace(' ', '_')},
    COUNT(*)                       AS record_count,
    COUNT(DISTINCT {primary}.{pk}) AS unique_records
FROM {primary}
WHERE {primary}.MANDT = :P_MANDT
GROUP BY {primary}.{dim_col}
HAVING COUNT(*) > 0
ORDER BY record_count DESC
LIMIT 100;"""

    return {
        "intent": f"Aggregate {primary} by {dim_label}",
        "business_use_case": f"Count and summarize {primary} records grouped by {dim_label} — for analytics and dashboards",
        "tables": [primary],
        "sql": agg_sql,
        "variant": "AGGREGATED",
        "module": meta_path.get('module_pair', meta_path.get('module', 'AUTO')),
    }


def generate_temporal_pattern(meta_path: dict) -> dict:
    """Variant 4: Time-series with fiscal year / date range."""
    tables = meta_path['tables']
    primary = tables[0]

    # Common date columns by table
    date_cols = {
        "LFA1": "ERSDA",  "KNA1": "ERSDA",  "MARA": "ERSDA",
        "EKKO": "BEDAT",  "EKPO": "BEDAT",
        "VBAK": "AUDAT",  "LIKP": "WADAT",  "VBRK": "FKDAT",
        "BKPF": "BLDAT",  "BSEG": "BLDAT",
        "QALS": "QNDAT",  "PRPS": "ERDAT",
        "ASMD": "EDATU",  "VTTK": "TSDAT",
        "PA0001": "BEGDA",
    }

    date_col = date_cols.get(primary, "ERSDA")

    temporal_sql = f"""SELECT
    {primary}.{date_col}          AS record_date,
    YEAR({primary}.{date_col})    AS fiscal_year,
    MONTH({primary}.{date_col})    AS month,
    COUNT(*)                       AS record_count
FROM {primary}
WHERE {primary}.MANDT = :P_MANDT
  AND {primary}.{date_col} BETWEEN :DATE_FROM AND :DATE_TO
GROUP BY
    YEAR({primary}.{date_col}),
    MONTH({primary}.{date_col}),
    {primary}.{date_col}
ORDER BY fiscal_year DESC, month DESC
LIMIT 200;"""

    return {
        "intent": f"Historical {primary} trends over time",
        "business_use_case": f"Time-series aggregation of {primary} by month and fiscal year — for trend analysis",
        "tables": [primary],
        "sql": temporal_sql,
        "variant": "TEMPORAL",
        "module": meta_path.get('module_pair', meta_path.get('module', 'AUTO')),
    }


def generate_full_join_pattern(meta_path: dict) -> dict:
    """Variant 5: Full multi-hop JOIN with all tables and optional filters."""
    tables = meta_path['tables']
    if len(tables) <= 1:
        return None  # Skip single-table paths

    joins = []
    for i in range(1, len(tables)):
        t2 = tables[i]
        cond = meta_path.get('join_conditions', [])
        if i-1 < len(cond) and isinstance(cond[i-1], (list, tuple)):
            _, _, c = cond[i-1]
            # Replace table names with aliases
            alias_a = 'a'
            alias_b = chr(ord('a') + i)
            c2 = c
            for ti, talias in [(tables[0], 'a')] + [(tables[j], chr(ord('a')+j)) for j in range(1, i+1)]:
                c2 = c2.replace(f"{ti}.", f"{talias}.")
            joins.append(f"LEFT JOIN {t2} ON {c2}")
        else:
            pk = get_primary_key_or_col(tables[0])
            joins.append(f"LEFT JOIN {t2} ON a.{pk} = {chr(ord('a')+i)}.{pk}")

    primary = tables[0]
    select_cols = [f"a.{primary}.{get_primary_key_or_col(primary)}"] + \
                  [f"{chr(ord('a')+i)}.{get_primary_key_or_col(t)}" for i, t in enumerate(tables[1:], 1)]

    full_sql = f"""SELECT
    a.*,
    -- Add selected columns from joined tables:
    b.{get_primary_key_or_col(tables[1])} AS {tables[1].lower()}_key
FROM {primary} a
{chr(10).join(joins)}
WHERE a.MANDT = :P_MANDT
  -- Add filters here based on business context:
  -- AND a.{{filter_col}} {{operator}} :{{param}}
ORDER BY a.{get_primary_key_or_col(primary)} DESC
LIMIT 100;"""

    return {
        "intent": f"Full cross-module view: {primary} with all related data",
        "business_use_case": f"Complete JOIN across {len(tables)} tables: {' -> '.join(tables)} — for comprehensive cross-module analysis",
        "tables": tables,
        "sql": full_sql,
        "variant": "FULL_JOIN",
        "module": meta_path.get('module_pair', meta_path.get('module', 'AUTO')),
    }


# ─── Main Generator ────────────────────────────────────────────────────────────

def generate_all_variants():
    """Generate all 5 pattern variants for all meta-paths."""
    all_patterns = []
    variant_counts = defaultdict(int)

    # Combine manual meta-paths and auto-generated ones
    auto_paths = AUTO_META_PATHS_V2
    print(f"Processing {len(auto_paths)} meta-paths...")

    for i, meta_path in enumerate(auto_paths):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(auto_paths)} meta-paths processed...")

        # 1. Base pattern
        p = generate_base_pattern(meta_path)
        all_patterns.append(p)
        variant_counts["BASE"] += 1

        # 2. Filtered pattern
        p2 = generate_filtered_pattern(meta_path)
        if p2:
            all_patterns.append(p2)
            variant_counts["FILTERED"] += 1

        # 3. Aggregated pattern
        p3 = generate_aggregated_pattern(meta_path)
        all_patterns.append(p3)
        variant_counts["AGGREGATED"] += 1

        # 4. Temporal pattern
        p4 = generate_temporal_pattern(meta_path)
        all_patterns.append(p4)
        variant_counts["TEMPORAL"] += 1

        # 5. Full join pattern (only for multi-table paths)
        p5 = generate_full_join_pattern(meta_path)
        if p5:
            all_patterns.append(p5)
            variant_counts["FULL_JOIN"] += 1

    return all_patterns, variant_counts


def write_pattern_file(all_patterns: list, output_path: str = None):
    """Write all patterns to a Python file."""
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(__file__),
            'backend', 'app', 'core', 'sql_patterns',
            'mega_generated_patterns.py'
        )

    import json as _json

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(
            '"""\n'
            'MEGA-GENERATED SQL PATTERNS — From Meta-Paths\n'
            f'Total: {len(all_patterns)} patterns across 5 variants\n'
            'Variants: BASE | FILTERED | AGGREGATED | TEMPORAL | FULL_JOIN\n'
            'Generated by: mega_pattern_generator.py\n'
            '"""\n\n'
            'MEGA_PATTERNS = [\n\n'
        )

        for p in all_patterns:
            intent_s  = _json.dumps(p['intent'])
            bus_s     = _json.dumps(p['business_use_case'])
            tables_s  = _json.dumps(p['tables'])
            sql_s     = _json.dumps(p['sql'])
            variant_s = _json.dumps(p['variant'])
            module_s  = _json.dumps(p['module'])

            f.write(f"    # -- {p['variant']} -- {p['tables'][0]} --\n")
            f.write(f"    {{\n")
            f.write(f"        'intent': {intent_s},\n")
            f.write(f"        'business_use_case': {bus_s},\n")
            f.write(f"        'tables': {tables_s},\n")
            f.write(f"        'sql': {sql_s},\n")
            f.write(f"        'variant': {variant_s},\n")
            f.write(f"        'module': {module_s},\n")
            f.write(f"    }},\n\n")

        f.write("]\n")
        f.write(
            '\n# To merge into library.py:\n'
            '# from app.core.sql_patterns.mega_generated_patterns import MEGA_PATTERNS\n'
            '# from app.core.sql_patterns.library import PATTERNS_BY_DOMAIN\n'
            '# for p in MEGA_PATTERNS:\n'
            '#     domain = p["module"].split("-")[0].lower().replace("_","")\n'
            '#     if domain in PATTERNS_BY_DOMAIN:\n'
            '#         PATTERNS_BY_DOMAIN[domain].append(p)\n'
        )

    return output_path


def main():
    all_patterns, variant_counts = generate_all_variants()

    print(f"\n{'='*60}")
    print(f"  MEGA PATTERN GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Total patterns: {len(all_patterns)}")
    print(f"\n  By variant:")
    for variant, count in sorted(variant_counts.items(), key=lambda x: -x[1]):
        print(f"    {variant:15s}: {count:5d}")

    output = write_pattern_file(all_patterns)

    print(f"\n  Output: {output}")
    print(f"\n  Original patterns:   470")
    print(f"  Mega patterns added: {len(all_patterns)}")
    print(f"  Projected total:    {470 + len(all_patterns)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
