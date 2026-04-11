"""
Meta-Path Auto-Generator — Extends from 14 → 100+ Meta-Paths
================================================================
Uses GraphRAGManager to algorithmically discover cross-module JOIN paths
and auto-generate MetaPath objects for ALL SAP modules.

Each auto-generated meta-path includes:
  - Business name and description (derived from table cluster)
  - All valid path variants from the graph
  - Parameterized SQL template with proper JOIN syntax
  - Required + optional filters (derived from graph node metadata)
  - Example NL queries
  - Confidence boost

Usage:
    python meta_path_auto_generator.py          # Generate and print summary
    python meta_path_auto_generator.py --write  # Append to meta_path_library.py
"""

import os
import sys
from collections import defaultdict
from typing import Dict, List, Set, Tuple

backend_path = os.path.join(os.path.dirname(__file__), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.graph_store import GraphRAGManager


# ─── Business Template Library ───────────────────────────────────────────────

# Intent templates for each module pair
MODULE_INTENT_TEMPLATES = {
    # (from_module, to_module): [list of business intent templates]
    ("MM", "BP"): [
        ("material_vendor_linkage", "Material to Vendor Linkage",
         "Connects a material to its approved vendors and purchasing info records.",
         ["material", "vendor", "source", "approved", "EINA", "EINE", "LFA1"]),
        ("material_consumption_vendor", "Material Consumption by Vendor",
         "Tracks which vendors have supplied a specific material and at what cost.",
         ["material", "consumption", "vendor", "spent", "MSEG", "LFA1", "EKKO"]),
    ],
    ("MM", "CO"): [
        ("material_cost_center", "Material to Cost Center",
         "Maps material movements to cost centers for spend visibility.",
         ["material", "cost center", "CSKS", "MSEG", " spend", "allocation"]),
    ],
    ("MM", "SD"): [
        ("material_sales_data", "Material Sales Analysis",
         "Links material master to sales data for revenue and pricing analysis.",
         ["material", "sales", "revenue", "VBAP", "KONV", "pricing", "MVKE"]),
    ],
    ("MM", "QM"): [
        ("material_quality_link", "Material to QM Inspection",
         "Connects material master to inspection lots and quality history.",
         ["material", "quality", "inspection", "QALS", "QMEL", "defect", "MAPL"]),
        ("material_batch_quality", "Batch Quality History",
         "Tracks quality results by batch for a material.",
         ["batch", "quality", "QALS", "MCH1", "QMEL", "defect"]),
    ],
    ("MM", "WM"): [
        ("material_warehouse_stock", "Material Warehouse Stock Position",
         "Full stock picture across storage types and bins for a material.",
         ["material", "stock", "warehouse", "LQUA", "LAGP", "MLGT", "inventory"]),
    ],
    ("MM", "PS"): [
        ("material_project_reservation", "Material Project Reservation",
         "Shows materials reserved for or consumed by a project WBS element.",
         ["material", "project", "WBS", "RESB", "PRPS", "PROJ", "reservation"]),
    ],
    ("MM", "FI"): [
        ("material_valuation_analysis", "Material Valuation Analysis",
         "Connects material valuation to accounting document line items.",
         ["material", "valuation", "MBEW", "BSEG", "accounting", "value", "cost"]),
    ],
    ("SD", "FI"): [
        ("order_to_cash_full", "Order-to-Cash (O2C) Full Cycle",
         "Complete sales order → delivery → billing → accounting chain.",
         ["order", "cash", "O2C", "VBAK", "LIKP", "VBRK", "BKPF", "BSEG", "invoice"]),
        ("customer_credit_exposure", "Customer Credit Exposure",
         "Customer open items + credit limit analysis.",
         ["customer", "credit", "open items", "BSID", "KNKK", "limit", "overdue"]),
        ("sales_revenue_gl", "Sales Revenue by G/L Account",
         "Maps billing documents to G/L account postings.",
         ["sales", "revenue", "VBRK", "BSEG", "KONV", "GL", "posting"]),
    ],
    ("MM-PUR", "FI"): [
        ("procure_to_pay_full", "Procure-to-Pay (P2P) Full Cycle",
         "Complete PO → goods receipt → invoice → accounting cycle.",
         ["procure", "PO", "P2P", "EKKO", "MSEG", "BKPF", "BSEG", "GR/IR", "lifecycle"]),
        ("vendor_open_items", "Vendor Open Items Analysis",
         "Shows open/cleared vendor invoices and payment status.",
         ["vendor", "open items", "BSIK", "BSAK", "LFA1", "payment", "overdue"]),
    ],
    ("FI", "CO"): [
        ("cost_center_actual_vs_plan", "Cost Center Actual vs. Plan",
         "Compares actual costs posted to cost center against plan.",
         ["cost center", "actual", "plan", "COSP", "COSS", "CSKS", "variance"]),
        ("profit_center_reporting", "Profit Center Financials",
         "Profit center revenue, costs, and contribution.",
         ["profit center", "CEPC", "COEP", "revenue", "cost", "contribution"]),
    ],
    ("FI", "PS"): [
        ("project_financials", "Project Financials (WBS)",
         "Actual costs and commitments against a project WBS element.",
         ["project", "WBS", "financials", "PRPS", "COSP", "COSS", "commitments"]),
    ],
    ("FI", "PM"): [
        ("equipment_depreciation", "Asset Depreciation Schedule",
         "Fixed asset depreciation posting to FI.",
         ["asset", "depreciation", "ANLA", "ANLB", "ANEP", "BKPF", "book value"]),
    ],
    ("QM", "SD"): [
        ("delivery_quality_hold", "Delivery Quality Hold",
         "QM inspection results linked to outbound deliveries.",
         ["delivery", "quality", "hold", "LIKP", "QALS", "LIPS", "inspection"]),
    ],
    ("WM", "MM"): [
        ("transfer_order_flow", "Transfer Order Movement History",
         "WM transfer orders linked to material movements.",
         ["transfer", "LTBP", "LQUA", "MSEG", "movement", "stock transfer"]),
    ],
    ("TM", "SD"): [
        ("shipment_delivery_link", "Shipment to Delivery Link",
         "Connects transportation shipments to outbound deliveries.",
         ["shipment", "delivery", "VTTK", "VTTS", "LIKP", "VTFL", "transportation"]),
    ],
    ("CS", "SD"): [
        ("service_order_sales", "Service Order to Sales Order",
         "Links field service orders to sales/process orders.",
         ["service", "order", "ASMD", "VBAK", "AFVC", "notification"]),
        ("warranty_claim_billing", "Warranty Claim to Billing",
         "Warranty claims linked to billing documents.",
         ["warranty", "claim", "QMEL", "VBRK", "ASMD", "service"]),
    ],
    ("HR", "CO"): [
        ("employee_cost_allocation", "Employee Cost to Cost Center",
         "Routes payroll/personnel costs to cost centers.",
         ["employee", "HR", "cost", "CSKS", "PA0001", "PAYROLL", "allocation"]),
        ("headcount_cost_center", "Headcount by Cost Center",
         "Employee distribution across cost centers.",
         ["headcount", "cost center", "PA0001", "CSKS", "ORGUnit", "HC"]),
    ],
    ("IS-OIL", "MM"): [
        ("oil_tank_material", "Oil Tank to Material Link",
         "Maps tank/installation data to material (hydrocarbon) records.",
         ["tank", "material", "OIB_A04", "MARA", "hydrocarbon", "oil", "storage"]),
        ("jv_cost_allocation", "Joint Venture Cost Allocation",
         "JVA partner cost sharing across cost objects.",
         ["JVA", "joint venture", "T8JV", "EKKO", "MSEG", "cost share", "partner"]),
    ],
    ("IS-UTILITY", "FI"): [
        ("utility_installation_financials", "Installation Financial History",
         "Device/installation costs linked to FI postings.",
         ["installation", "device", "EVBS", "EANL", "BSEG", "billing", "utility"]),
    ],
    ("IS-RETAIL", "MM"): [
        ("retail_article_planning", "Article (Material) to Assortment",
         "Merchandise article linked to assortment and buying data.",
         ["article", "assortment", "WRS1", "MARA", "SETY", "retail", "merchandise"]),
    ],
    ("RE", "FI"): [
        ("lease_payment_schedule", "Lease Payment Schedule",
         "Real estate lease rental income/expense linked to FI.",
         ["lease", "rent", "VIMONI", "BSEG", "FI", "rental", "contract"]),
        ("property_asset_financials", "Property Asset Register",
         "Real estate asset linked to FI asset accounting.",
         ["property", "asset", "ANLA", "VIBDT", "BSEG", "depreciation"]),
    ],
    ("GTS", "MM-PUR"): [
        ("trade_compliance_screening", "Trade Compliance for Procurement",
         "Vendor/material screened against sanctioned party lists in GTS.",
         ["GTS", "sanctioned", "screening", "LFA1", "/SAPSLL/PNTPR", "compliance"]),
        ("export_control_customs", "Export Control and Customs",
         "Customs data linked to delivery/shipment for export control.",
         ["export", "customs", "GTS", "/SAPSLL/POD", "LIKP", "VTFL", "export control"]),
    ],
    ("TAX", "FI"): [
        ("tax_code_posting", "Tax Code to G/L Posting",
         "Maps tax codes (MWSt, GST) to G/L account postings.",
         ["tax", "MWST", "GST", "A003", "BSEG", "KONP", "tax code", "posting"]),
    ],
    ("LO-VC", "MM"): [
        ("variant_configuration_validate", "Variant Configuration Validation",
         "Validates configured material against characteristics/classes.",
         ["configuration", "variant", "CUOBJ", "CABN", "KLAH", "MARA", "class"]),
    ],
}


# ─── Module → Primary Tables Mapping ──────────────────────────────────────────

MODULE_ANCHOR_TABLES = {
    "MM":       ["MARA", "MARC", "MARD", "MBEW"],
    "MM-PUR":   ["EKKO", "EKPO", "EINA", "EINE", "EORD"],
    "BP":       ["LFA1", "KNA1", "BUT000", "ADRC"],
    "SD":       ["VBAK", "VBAP", "LIKP", "LIPS", "VBRK", "VBRP", "KONV", "KNVV"],
    "FI":       ["BKPF", "BSEG", "BSIK", "BSAK", "BSID", "BSAD", "SKA1", "SKB1"],
    "CO":       ["CSKS", "COSS", "COSP", "CEPC"],
    "QM":       ["QALS", "QAVE", "QMEL", "MAPL", "PLMK", "PLPO"],
    "WM":       ["LQUA", "LAGP", "LDCP", "MLGN", "MLGT", "LEU4", "LTBP"],
    "PM":       ["EQUI", "IHK6", "IFLOT", "ILOA"],
    "PS":       ["PROJ", "PRPS", "AFVC", "AFVV"],
    "TM":       ["VTTK", "VTLP", "VTFA", "VTFL"],
    "CS":       ["ASMD", "IHPA", "QMEL", "DRAD"],
    "HR":       ["PA0001", "PA0008", "HRP1000"],
    "RE":       ["VIMONI", "VIBDT", "ANLA"],
    "GTS":      ["/SAPSLL/POD", "/SAPSLL/PNTPR"],
    "IS-OIL":   ["OIB_A04", "OIG_V", "T8JV"],
    "IS-UTILITY": ["EVBS", "EANL", "EGERR"],
    "IS-RETAIL": ["WRS1", "SETY", "MARA"],
    "IS-HEALTH": ["NPAT", "NBEW", "NPNZ"],
    "TAX":      ["J_1IG_HSN_SAC", "J_1BBRANCH"],
    "LO-VC":    ["CABN", "KLAH", "CUOBJ", "INOB"],
}


# ─── Filter Rule Library ──────────────────────────────────────────────────────

FILTER_TEMPLATES = {
    "LFA1":  ["LFA1.LIFNR = :LIFNR", "LFA1.LAND1 = :LAND1", "LFA1.KTOKK = :KTOKK"],
    "KNA1":  ["KNA1.KUNNR = :KUNNR", "KNA1.LAND1 = :LAND1", "KNA1.KDKG1 = :KDGRP"],
    "MARA":  ["MARA.MATNR = :MATNR", "MARA.MTART = :MTART", "MARA.MBRSH = :MBRSH"],
    "MARC":  ["MARC.WERKS = :WERKS", "MARC.DISPO = :DISPO"],
    "MARD":  ["MARD.WERKS = :WERKS", "MARD.LGORT = :LGORT"],
    "MBEW":  ["MBEW.BWKEY = :BWKEY"],
    "EKKO":  ["EKKO.EBELN = :EBELN", "EKKO.LIFNR = :LIFNR", "EKKO.BEDAT BETWEEN :DF AND :DT",
              "EKKO.BSART = :BSART", "EKKO.EKGRP = :EKGRP"],
    "EKPO":  ["EKPO.EBELN = :EBELN", "EKPO.MATNR = :MATNR", "EKPO.WERKS = :WERKS"],
    "VBAK":  ["VBAK.VBELN = :VBELN", "VBAK.KUNNR = :KUNNR", "VBAK.VKORG = :VKORG",
              "VBAK.AUART = :AUART"],
    "VBAP":  ["VBAP.VBELN = :VBELN", "VBAP.MATNR = :MATNR"],
    "LIKP":  ["LIKP.VBELN = :VBELN", "LIKP.KUNNR = :KUNNR", "LIKP.WERKS = :WERKS"],
    "VBRK":  ["VBRK.VBELN = :VBELN", "VBRK.FKURG = :FKURG"],
    "BKPF":  ["BKPF.BELNR = :BELNR", "BKPF.BUKRS = :BUKRS",
              "BKPF.BLDAT BETWEEN :DF AND :DT", "BKPF.BKTXT = :BKTXT"],
    "BSEG":  ["BSEG.BELNR = :BELNR", "BSEG.BUKRS = :BUKRS", "BSEG.HKONT = :HKONT"],
    "BSIK":  ["BSIK.LIFNR = :LIFNR", "BSIK.BUKRS = :BUKRS", "BSIK.ZBD1T = :ZBD1T"],
    "BSID":  ["BSID.KUNNR = :KUNNR", "BSID.BUKRS = :BUKRS"],
    "CSKS":  ["CSKS.KOSTL = :KOSTL", "CSKS.KOKRS = :KOKRS",
              "CSKS.DATAB = :DATAB", "CSKS.DATBI = :DATBI"],
    "QALS":  ["QALS.QALS = :QALS", "QALS.WERKS = :WERKS", "QALS.MATNR = :MATNR"],
    "PRPS":  ["PRPS.PSPNR = :PSPNR", "PRPS.POSKI = :POSKI"],
    "COSP":  ["COSP.OBJNR = :OBJNR", "COSP.GJAHR = :GJAHR"],
    "EINA":  ["EINA.LIFNR = :LIFNR", "EINA.MATNR = :MATNR"],
    "KNVV":  ["KNVV.KUNNR = :KUNNR", "KNVV.VKORG = :VKORG"],
    "KNKK":  ["KNKK.KUNNR = :KUNNR"],
    "ANLA":  ["ANLA.ANLN1 = :ANLN1", "ANLA.BUKRS = :BUKRS"],
}


def _build_select_for_tables(tables: List[str]) -> Dict[str, List[str]]:
    """Build a default SELECT column dict for a list of tables."""
    selects = {
        "LFA1":  ["LIFNR", "NAME1", "ORT01", "LAND1", "KTOKK"],
        "KNA1":  ["KUNNR", "NAME1", "ORT01", "LAND1", "KDKG1"],
        "MARA":  ["MATNR", "MTART", "MBRSH", "MATKL", "MEINS"],
        "MARC":  ["MATNR", "WERKS", "DISPO", "PRCTR"],
        "MARD":  ["MATNR", "WERKS", "LGORT", "LABST", "UMLME"],
        "MBEW":  ["MATNR", "BWKEY", "BWPGS", "LBKUM", "STPRS"],
        "EKKO":  ["EBELN", "LIFNR", "BEDAT", "BSART", "NETWR", "WAERS"],
        "EKPO":  ["EBELN", "EBELP", "MATNR", "TXZ01", "MENGE", "NETWR"],
        "EINA":  ["INFNR", "LIFNR", "MATNR", "DATAB", "DATBI"],
        "VBAK":  ["VBELN", "KUNNR", "VKORG", "AUART", "NETWR", "WAERS"],
        "VBAP":  ["VBELN", "POSNR", "MATNR", "KWERT", "NETWR"],
        "LIKP":  ["VBELN", "KUNNR", "WADAT", "LTIAK", "WERKS"],
        "LIPS":  ["VBELN", "POSNR", "MATNR", "LFIMG", "VRKME"],
        "VBRK":  ["VBELN", "FKDAT", "KUNNR", "NETWR", "WAERS"],
        "VBRP":  ["VBELN", "POSNR", "MATNR", "FKIMG", "NETWR"],
        "BKPF":  ["BELNR", "BUKRS", "GJAHR", "BLDAT", "BKTXT", "AWKEY"],
        "BSEG":  ["BELNR", "BUZEI", "BUKRS", "HKONT", "DMBTR", "WAERS", "ZUONR"],
        "BSIK":  ["LIFNR", "BUKRS", "BELNR", "BUZEI", "DMBTR", "ZBD1T", "ZBD2T"],
        "BSID":  ["KUNNR", "BUKRS", "BELNR", "BUZEI", "DMBTR", "ZBD1T"],
        "SKA1":  ["SAKNR", "KTOPL", "KTOKS", "XBILK"],
        "CSKS":  ["KOSTL", "KOKRS", "DATAB", "DATBI", "KOSGR", "VERAK"],
        "COSP":  ["OBJNR", "GJAHR", "PERBL", "WTGES"],
        "COSS":  ["OBJNR", "GJAHR", "PERBL", "PLANS"],
        "CEPC":  ["PRCTR", "KOKRS", "DATAB", "DATBI", "KHINR"],
        "QALS":  ["QALS", "ART", "WERKS", "MATNR", "QNDAT", "STTTXT"],
        "PRPS":  ["PSPNR", "POSKI", "POST1", "PBUKR", "PSPID"],
        "AFVC":  ["NPLNR", "POSNR", "VORNR", "LTXA1", "ARBID"],
        "LQUA":  ["LENUM", "MATNR", "WERKS", "LGORT", "KLEND", "LETYP"],
        "LAGP":  ["LGTYP", "WERKS", "LTYP", "LABST"],
        "EQUI":  ["EQUNR", "EQTYP", "TPLNR", "INGRP"],
        "ASMD":  ["QMNUM", "ITAMC", "QMTXT", "STRMN", "EDATU"],
        "PA0001":["PERNR", "ORGEH", "PLANS", "STELL", "BUKRS"],
        "VIMONI":["VKONT", "VTRMN", "VTDAT", "VAMNG", "VAKEY"],
        "MCH1":  ["MATNR", "CHARG", "WERKS", "CLABS"],
        "KONV":  ["KNUMV", "KPOSN", "STUNR", "KWERT", "KRECH"],
        "KNVV":  ["KUNNR", "VKORG", "VTWEG", "SPART", "AWAHR"],
        "KNKK":  ["KUNNR", "KLIMK", "GRUIC", "CRBLB"],
        "ANLA":  ["ANLN1", "ANLN2", "BUKRS", "AKTIV", "NDJAR"],
        "A003":  ["KAPPL", "KSCHL", "VKORG", "VTWEG", "MATNR", "LAND1"],
    }
    return {t: selects.get(t, ["*"]) for t in tables}


def _build_join_from_path(tables: List[str], edge_data: Dict) -> List[Tuple[str, str, str]]:
    """Build join conditions from ordered table list using edge metadata."""
    joins = []
    # We pair adjacent tables and look up the FK condition
    for i in range(len(tables) - 1):
        t1, t2 = tables[i], tables[i + 1]
        # Try to find edge between these tables
        if (t1, t2) in edge_data:
            cond = edge_data[(t1, t2)].get('condition', '')
        elif (t2, t1) in edge_data:
            cond = edge_data[(t2, t1)].get('condition', '')
            # Reverse it
            parts = cond.split(' = ')
            if len(parts) == 2:
                cond = f"{parts[1]} = {parts[0]}"
        else:
            # Auto-generate a plausible JOIN key
            # Try common FK naming patterns
            for col in [f"{t1[:4]}_NR", f"{t1}_NR", "MATNR", "LIFNR", "KUNNR"]:
                if col.upper() in [t2.upper(), t1.upper()]:
                    cond = f"{t1}.{col} = {t2}.{col}"
                    break
            else:
                cond = f"{t1}.MANDT = {t2}.MANDT"
        joins.append((t1, t2, cond))
    return joins


def _generate_sql_template(tables: List[str], joins: List[Tuple], 
                           filters: List[str], select_dict: Dict) -> str:
    """Generate a parameterized SQL template string."""
    # Build SELECT clause
    select_parts = []
    for t in tables:
        cols = select_dict.get(t, ["*"])
        if cols == ["*"]:
            select_parts.append(f"    a.*" if t == tables[0] else f"    b.*")
        else:
            col_str = ", ".join([f"{t}.{c}" for c in cols[:6]])
            select_parts.append(f"    {col_str}")

    # Build FROM + JOIN clauses
    from_clause = f"    {tables[0]}"
    join_clauses = []
    alias_map = {tables[0]: "a"}
    for i, t in enumerate(tables[1:], 1):
        alias_map[t] = chr(ord('a') + i)
    alias = lambda t: alias_map.get(t, t)

    for t1, t2, cond in joins:
        join_clauses.append(f"LEFT JOIN {t2} ON {cond.replace(t1, alias(t1)).replace(t2, alias(t2))}")

    # Assemble
    template = f"""
SELECT
{chr(10).join(select_parts)}
FROM {tables[0]}
{chr(10).join(join_clauses)}
WHERE
    {tables[0]}.MANDT = :P_MANDT
    AND {{filters}}
ORDER BY {tables[0]}.{select_dict.get(tables[0], ['*'])[0] if select_dict.get(tables[0], ['*']) != ['*'] else tables[0].split('_')[0]+'_ID'} DESC
LIMIT 100;""".strip()

    return template


def discover_paths_between_modules(G, module_a: str, module_b: str, 
                                   anchor_a: List[str], anchor_b: List[str]) -> List[List[str]]:
    """Use BFS to find all simple paths between module anchor tables."""
    all_paths = []
    for src in anchor_a:
        for dst in anchor_b:
            if src not in G or dst not in G:
                continue
            try:
                paths = list(G.simple_paths(src, dst, cutoff=4))
                all_paths.extend(paths)
            except Exception:
                pass
    # Deduplicate
    seen = set()
    unique = []
    for p in all_paths:
        key = tuple(p)
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def generate_auto_meta_paths() -> List[Dict]:
    """Main generator — discovers paths and builds MetaPath dicts."""
    print("Loading GraphRAGManager...")
    G = GraphRAGManager().G
    print(f"  Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges\n")

    # Build edge lookup dict
    edge_data = {}
    for u, v, d in G.edges(data=True):
        edge_data[(u, v)] = d
        edge_data[(v, u)] = d  # undirected

    auto_paths = []
    path_id_counter = 1

    # 1. Discover paths for each module pair
    all_modules = list(MODULE_ANCHOR_TABLES.keys())
    for i, mod_a in enumerate(all_modules):
        for mod_b in all_modules[i+1:]:
            key = (mod_a, mod_b)
            if key in MODULE_INTENT_TEMPLATES:
                templates = MODULE_INTENT_TEMPLATES[key]
            else:
                key_rev = (mod_b, mod_a)
                templates = MODULE_INTENT_TEMPLATES.get(key_rev, [])

            anchors_a = MODULE_ANCHOR_TABLES[mod_a]
            anchors_b = MODULE_ANCHOR_TABLES[mod_b]

            paths = discover_paths_between_modules(G, mod_a, mod_b, anchors_a, anchors_b)
            if not paths:
                continue

            for path in paths[:3]:  # Max 3 path variants per pair
                # Find which template matches best
                path_str = "_".join(path)
                matched_template = None
                for t in templates:
                    keywords = t[3]  # bloom_filter
                    if any(kw.lower() in path_str.lower() for kw in keywords):
                        matched_template = t
                        break

                if matched_template:
                    pid, name, desc, blooms = matched_template
                else:
                    pid = f"auto_{path_id_counter:03d}"
                    name = f"{mod_a}-{mod_b} Cross-Module Path"
                    desc = f"Auto-discovered JOIN path between {mod_a} and {mod_b} modules."
                    blooms = []

                joins = _build_join_from_path(path, edge_data)
                sel_dict = _build_select_for_tables(path)
                filters = FILTER_TEMPLATES.get(path[0], [])
                template_sql = _generate_sql_template(path, joins, filters, sel_dict)

                auto_paths.append({
                    "id": pid,
                    "name": name,
                    "desc": desc,
                    "module_pair": (mod_a, mod_b),
                    "tables": path,
                    "joins": joins,
                    "bloom_filter": blooms,
                    "filters": filters,
                    "sql_template": template_sql,
                })
                path_id_counter += 1

    # 2. Also generate single-module anchor paths (base views per module)
    for mod, anchors in MODULE_ANCHOR_TABLES.items():
        for table in anchors[:2]:  # Max 2 per module
            if table in G.nodes:
                joins = []
                sel_dict = _build_select_for_tables([table])
                template_sql = f"""
SELECT {sel_dict.get(table, ['*'])}
FROM {table}
WHERE MANDT = :P_MANDT
  AND {{filters}}
LIMIT 100;""".strip()
                auto_paths.append({
                    "id": f"auto_{path_id_counter:03d}",
                    "name": f"{mod} Base View — {table}",
                    "desc": f"Base data retrieval for {table} ({mod} module).",
                    "module_pair": (mod, mod),
                    "tables": [table],
                    "joins": [],
                    "bloom_filter": [mod.lower(), table.lower()],
                    "filters": FILTER_TEMPLATES.get(table, []),
                    "sql_template": template_sql,
                })
                path_id_counter += 1

    return auto_paths


def write_to_meta_path_library(auto_paths: List[Dict], output_path: str = None):
    """Write auto-generated paths as Python code appendable to meta_path_library.py."""
    if output_path is None:
        output_path = os.path.join(
            os.path.dirname(__file__),
            'backend', 'app', 'core', 'sql_patterns',
            'auto_meta_paths.py'
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(
            '"""\n'
            'AUTO-GENERATED META-PATHS — Extended v2\n'
            f'Total: {len(auto_paths)} paths\n'
            'Generated by: meta_path_auto_generator.py\n'
            'Merge with existing SAP_META_PATHS in meta_path_library.py\n'
            '"""\n\n'
            'from collections import defaultdict\n'
            'from dataclasses import dataclass, field\n'
            'from typing import Dict, List, Tuple\n\n'
            'AUTO_META_PATHS = [\n'
        )

        for p in auto_paths:
            mod_pair = p['module_pair']
            tables_str = str(p['tables'])
            joins_str = str(p['joins'])
            blooms_str = str(p['bloom_filter'])
            filters_str = str(p['filters'])
            example_queries = [
                f"show me {p['tables'][0]} data with {p['tables'][-1]}",
                f"list {p['tables'][0]} records",
                f"get {mod_pair[0]} to {mod_pair[1]} information",
            ]
            sql_t = p['sql_template'].replace('"', '\\"').replace('\n', '\\n')

            f.write(f"""    {{
        "id": "{p['id']}",
        "name": "{p['name']}",
        "business_description": "{p['desc']}",
        "domain": "auto_generated",
        "module": "{mod_pair[0]}-{mod_pair[1]}",
        "tags": {blooms_str},
        "tables": {tables_str},
        "join_conditions": {joins_str},
        "required_filters": ["{p['tables'][0]}.MANDT = :P_MANDT"],
        "optional_filters": {filters_str},
        "sql_template": "{sql_t}",
        "example_queries": {str(example_queries)},
        "confidence_boost": 0.15,
    }},
""")

        f.write("]\n")
        f.write(
            '\n# Merge into SAP_META_PATHS:\n'
            '# from app.core.sql_patterns.auto_meta_paths import AUTO_META_PATHS\n'
            '# SAP_META_PATHS.extend(AUTO_META_PATHS)\n'
        )

    print(f"Written {len(auto_paths)} auto-meta-paths to: {output_path}")
    return output_path


def main():
    auto_paths = generate_auto_meta_paths()

    # Print summary
    print(f"\n{'='*60}")
    print(f"  AUTO-GENERATED META-PATHS SUMMARY")
    print(f"{'='*60}")
    print(f"  Total paths discovered: {len(auto_paths)}")

    by_module = defaultdict(int)
    for p in auto_paths:
        by_module[p['module_pair'][0]] += 1
        by_module[p['module_pair'][1]] += 1

    print(f"\n  Paths per module:")
    for mod, count in sorted(by_module.items(), key=lambda x: -x[1]):
        print(f"    {mod:20s}: {count:3d} paths")

    print(f"\n  Top 10 paths:")
    for p in auto_paths[:10]:
        mp = p['module_pair']
        print(f"    [{p['id']}] {p['name']}")
        print(f"       Tables: {' → '.join(p['tables'])}")

    # Write file
    output = write_to_meta_path_library(auto_paths)

    print(f"\n  File: {output}")
    print(f"\n  To use: add to meta_path_library.py:")
    print(f"    from app.core.sql_patterns.auto_meta_paths import AUTO_META_PATHS")
    print(f"    SAP_META_PATHS.extend(AUTO_META_PATHS)")
    print(f"\n{'='*60}")


if __name__ == "__main__":
    main()
