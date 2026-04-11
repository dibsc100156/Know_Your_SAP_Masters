"""
Meta-Path Auto-Generator v2 — Full Graph Traversal
==================================================
Discovers ALL cross-module paths from the real graph and generates
properly structured MetaPath objects for each module pair.

Fixes v1: uses actual module labels from graph nodes as keys.
"""

import os
import sys
from collections import defaultdict
from typing import Dict, List, Set, Tuple

backend_path = os.path.join(os.path.dirname(__file__), 'backend')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.graph_store import GraphRAGManager


# ─── Business Intent Templates ─────────────────────────────────────────────────

INTENT_TEMPLATES = {
    # MM cross-module
    ("MM", "BP"): [
        ("material_vendor_source", "Material to Vendor Sourcing Link",
         "Approved vendor sources and info records for a material",
         ["vendor", "source", "EINA", "EINE", "LFA1", "purchasing info record"]),
        ("material_vendor_consumption", "Material Vendor Consumption Analysis",
         "Historical consumption of a material grouped by vendor",
         ["material", "consumption", "vendor", "MSEG", "EKKO", "spent"]),
    ],
    ("MM", "CO"): [
        ("material_cost_allocation", "Material to Cost Center Allocation",
         "Material consumption routed to cost centers",
         ["material", "cost center", "CSKS", "MSEG", "allocation"]),
    ],
    ("MM", "SD"): [
        ("material_sales_data", "Material Sales Data Analysis",
         "Material sold through different sales orgs and pricing",
         ["sales", "material", "VBAP", "KONV", "MVKE", "pricing"]),
    ],
    ("MM", "QM"): [
        ("material_inspection_link", "Material QM Inspection History",
         "Quality inspection results for a material across plants",
         ["material", "quality", "inspection", "QALS", "QMEL", "MAPL"]),
        ("material_batch_quality", "Batch Quality History",
         "Quality results by batch for a material",
         ["batch", "quality", "QALS", "MCH1", "defect"]),
    ],
    ("MM", "WM"): [
        ("material_stock_position", "Material Stock Across All Storage",
         "Full stock picture across plants, storage types, and bins",
         ["stock", "warehouse", "inventory", "LQUA", "LAGP", "MLGT"]),
    ],
    ("MM", "PS"): [
        ("material_project_reservation", "Material Project Reservations",
         "Materials reserved for or consumed by project WBS",
         ["material", "project", "WBS", "RESB", "PRPS", "reservation"]),
    ],
    # BP cross-module
    ("BP", "SD"): [
        ("customer_sales_history", "Customer Sales History",
         "All sales orders, deliveries and billing for a customer",
         ["customer", "sales", "VBAK", "LIKP", "VBRK", "KNA1"]),
        ("customer_credit_analysis", "Customer Credit Limit Analysis",
         "Open items vs credit limit for a customer",
         ["customer", "credit", "limit", "KNKK", "BSID", "overdue"]),
    ],
    ("BP", "MM-PUR"): [
        ("vendor_purchase_history", "Vendor Purchase Order History",
         "All POs and goods receipts for a vendor",
         ["vendor", "purchase", "EKKO", "EKPO", "MSEG", "LFA1"]),
        ("vendor_payment_terms", "Vendor Payment Terms and History",
         "Payment terms and historical payment behavior",
         ["vendor", "payment", "terms", "LFB1", "ZTERM", "BSIK"]),
    ],
    ("BP", "FI"): [
        ("vendor_financial_exposure", "Vendor Financial Exposure",
         "Open and cleared items, payment history, and G/L exposure",
         ["vendor", "financial", "exposure", "BSIK", "BSAK", "BSEG"]),
    ],
    # SD → FI
    ("SD", "FI"): [
        ("order_to_cash_full", "Order-to-Cash Full Cycle",
         "Sales order → delivery → billing → accounting chain",
         ["O2C", "order", "cash", "VBAK", "LIKP", "VBRK", "BKPF", "BSEG"]),
        ("sales_revenue_by_gl", "Sales Revenue by G/L Account",
         "Billing mapped to G/L account postings",
         ["sales", "revenue", "GL", "VBRK", "BSEG", "KONV"]),
    ],
    # MM-PUR → FI
    ("MM-PUR", "FI"): [
        ("procure_to_pay_full", "Procure-to-Pay Full Cycle",
         "PO → goods receipt → invoice → accounting",
         ["P2P", "procure", "EKKO", "MSEG", "MKPF", "BKPF", "BSEG", "GR/IR"]),
        ("vendor_open_items", "Vendor Open Items Analysis",
         "Open and cleared vendor invoices",
         ["vendor", "open items", "BSIK", "BSAK", "payment", "overdue"]),
    ],
    # FI → CO
    ("FI", "CO"): [
        ("cost_center_actual_plan", "Cost Center Actual vs Plan",
         "Actual posted costs against plan for a cost center",
         ["cost center", "actual", "plan", "COSP", "COSS", "variance"]),
        ("profit_center_reporting", "Profit Center Financials",
         "Profit center revenue, costs, and contribution",
         ["profit center", "revenue", "cost", "CEPC", "COEP"]),
    ],
    # FI → PS
    ("FI", "PS"): [
        ("project_financials", "Project WBS Financials",
         "Actual costs and commitments against a WBS project",
         ["project", "WBS", "financials", "PRPS", "COSP", "commitments"]),
    ],
    # FI → RE
    ("FI", "RE"): [
        ("asset_register_financials", "Asset to FI Financials",
         "Asset depreciation and book value linked to FI postings",
         ["asset", "depreciation", "ANLA", "ANLB", "BSEG", "book value"]),
    ],
    # QM → SD
    ("QM", "SD"): [
        ("delivery_quality_hold", "Delivery Quality Hold",
         "QM results for outbound deliveries",
         ["delivery", "quality", "hold", "LIKP", "QALS", "LIPS"]),
    ],
    # WM → MM
    ("WM", "MM"): [
        ("transfer_order_movement", "Transfer Order Movement History",
         "WM transfer orders linked to material movements",
         ["transfer", "stock transfer", "LTBP", "LQUA", "MSEG"]),
    ],
    # TM → SD
    ("TM", "SD"): [
        ("shipment_delivery", "Shipment to Delivery Link",
         "Transportation shipments linked to outbound deliveries",
         ["shipment", "delivery", "VTTK", "LIKP", "VTFL"]),
    ],
    # CS → SD
    ("CS", "SD"): [
        ("service_order_billing", "Service Order to Sales Billing",
         "Field service orders linked to billing documents",
         ["service", "billing", "ASMD", "VBRK", "warranty"]),
    ],
    # PM → FI
    ("PM", "FI"): [
        ("equipment_depreciation", "Equipment Depreciation",
         "Equipment asset depreciation linked to FI",
         ["equipment", "asset", "depreciation", "EQUI", "ANLA", "BSEG"]),
    ],
    # HR → CO
    ("HR", "CO"): [
        ("employee_cost_allocation", "Employee Cost to Cost Center",
         "Personnel costs routed to cost centers",
         ["employee", "cost", "HR", "CSKS", "PA0001", "payroll"]),
        ("headcount_cost_center", "Headcount by Cost Center",
         "Employee distribution across cost organizations",
         ["headcount", "cost center", "HC", "PA0001", "CSKS"]),
    ],
    # IS-OIL → MM-PUR
    ("IS-OIL", "MM-PUR"): [
        ("oil_tank_material_procurement", "Oil Tank Material Procurement",
         "Tank / installation data linked to procurement for hydrocarbon materials",
         ["oil", "tank", "procurement", "OIB_A04", "EKKO", "MSEG"]),
    ],
    # IS-OIL → FI
    ("IS-OIL", "FI"): [
        ("jv_cost_sharing", "Joint Venture Cost Sharing",
         "JVA partner cost allocation via FI postings",
         ["JVA", "joint venture", "T8JV", "BSEG", "cost share"]),
    ],
    # IS-UTILITY → FI
    ("IS-UTILITY", "FI"): [
        ("utility_device_financials", "Utility Device Installation Financials",
         "Device costs linked to FI for utilities",
         ["utility", "device", "installation", "EVBS", "EANL", "BSEG"]),
    ],
    # IS-RETAIL → MM
    ("IS-RETAIL", "MM"): [
        ("retail_article_assortment", "Retail Article to Assortment",
         "Merchandise article linked to retail assortment",
         ["retail", "article", "assortment", "WRS1", "MARA", "SETY"]),
    ],
    # RE → FI
    ("RE", "FI"): [
        ("lease_payment_financials", "RE Lease Payment to FI",
         "Real estate lease payments linked to FI",
         ["lease", "rental", "VIMONI", "BSEG", "FI"]),
    ],
    # GTS → MM-PUR
    ("GTS", "MM-PUR"): [
        ("trade_compliance_screening", "Trade Compliance Screening",
         "Vendor/material screened in GTS for procurement",
         ["GTS", "compliance", "screened", "/SAPSLL/PNTPR", "LFA1"]),
    ],
    # GTS → SD
    ("GTS", "SD"): [
        ("export_control_delivery", "Export Control for Deliveries",
         "Customs and export control for outbound deliveries",
         ["export", "customs", "GTS", "/SAPSLL/POD", "LIKP", "VTFL"]),
    ],
    # TAX → FI
    ("TAX", "FI"): [
        ("tax_code_gl_posting", "Tax Code to G/L Posting",
         "Tax codes (GST, MWST) mapped to G/L account postings",
         ["tax", "GST", "MWST", "A003", "BSEG", "KONP"]),
    ],
    # LO-VC → MM
    ("LO-VC", "MM"): [
        ("variant_config_validation", "Variant Configuration Validation",
         "Configured material validated against characteristics",
         ["configuration", "variant", "CUOBJ", "CABN", "KLAH", "MARA"]),
    ],
}


# ─── SELECT Column Rules ───────────────────────────────────────────────────────

SELECT_COLS = {
    "LFA1":  ["LIFNR", "NAME1", "ORT01", "LAND1", "KTOKK", "STCD1"],
    "KNA1":  ["KUNNR", "NAME1", "ORT01", "LAND1", "KDKG1"],
    "MARA":  ["MATNR", "MTART", "MBRSH", "MATKL", "MEINS"],
    "MARC":  ["MATNR", "WERKS", "DISPO", "PRCTR", "EKGRP"],
    "MARD":  ["MATNR", "WERKS", "LGORT", "LABST", "UMLME"],
    "MBEW":  ["MATNR", "BWKEY", "BWPGS", "LBKUM", "STPRS", "PEPR"],
    "MAKT":  ["MATNR", "MAKTX"],
    "MVKE":  ["MATNR", "VKORG", "VTWEG", "VERWE", "KTGRM"],
    "EKKO":  ["EBELN", "LIFNR", "BEDAT", "BSART", "NETWR", "WAERS", "EKGRP"],
    "EKPO":  ["EBELN", "EBELP", "MATNR", "TXZ01", "MENGE", "NETWR", "ELIKZ"],
    "EINA":  ["INFNR", "LIFNR", "MATNR", "DATAB", "DATBI", "NORBM"],
    "EINE":  ["INFNR", "EKORG", "ESOKZ", "WERTB", "PEINH"],
    "EORD":  ["LIFNR", "MATNR", "WERKS", "ERNAM", "VDATU"],
    "VBAK":  ["VBELN", "KUNNR", "VKORG", "AUART", "NETWR", "WAERS", "AUDAT"],
    "VBAP":  ["VBELN", "POSNR", "MATNR", "KWERT", "NETWR", "VRKME"],
    "VBEP":  ["VBELN", "POSNR", "ETENR", "BMENG", "EINDT"],
    "VBFA":  ["VBELV", "POSNV", "VBELN", "POSNN", "RFMNG"],
    "LIKP":  ["VBELN", "KUNNR", "WADAT", "LTIAK", "WERKS", "LFART"],
    "LIPS":  ["VBELN", "POSNR", "MATNR", "LFIMG", "VRKME", "WERKS"],
    "VBRK":  ["VBELN", "FKDAT", "KUNNR", "NETWR", "WAERS", "FKURG"],
    "VBRP":  ["VBELN", "POSNR", "MATNR", "FKIMG", "NETWR"],
    "KONV":  ["KNUMV", "KPOSN", "STUNR", "KWERT", "KRECH", "WAERS"],
    "KNVV":  ["KUNNR", "VKORG", "VTWEG", "SPART", "AWAHR", "KALKS"],
    "KNKK":  ["KUNNR", "KLIMK", "GRUIC", "CRBLB", "LDGRU"],
    "BKPF":  ["BELNR", "BUKRS", "GJAHR", "BLDAT", "BKTXT", "AWKEY"],
    "BSEG":  ["BELNR", "BUZEI", "BUKRS", "HKONT", "DMBTR", "WAERS", "ZUONR"],
    "BSIK":  ["LIFNR", "BUKRS", "BELNR", "BUZEI", "DMBTR", "ZBD1T", "ZBD2T", "WAERS"],
    "BSAK":  ["LIFNR", "BUKRS", "BELNR", "BUZEI", "DMBTR", "WAERS"],
    "BSID":  ["KUNNR", "BUKRS", "BELNR", "BUZEI", "DMBTR", "ZBD1T", "WAERS"],
    "BSAD":  ["KUNNR", "BUKRS", "BELNR", "BUZEI", "DMBTR"],
    "SKA1":  ["SAKNR", "KTOPL", "KTOKS", "XBILK", "WAERS"],
    "SKB1":  ["SAKNR", "BUKRS", "XINTB"],
    "T001":  ["BUKRS", "BUTXT", "ORT01", "LAND1", "WAERS"],
    "T001W": ["WERKS", "NAME1", "BWKEY", "STRAS"],
    "CSKS":  ["KOSTL", "KOKRS", "DATAB", "DATBI", "KOSGR", "VERAK", "KHINR"],
    "COSS":  ["OBJNR", "GJAHR", "PERBL", "PLANS", "WOG001"],
    "COSP":  ["OBJNR", "GJAHR", "PERBL", "WTGES", "WOG001"],
    "CEPC":  ["PRCTR", "KOKRS", "DATAB", "DATBI", "KHINR", "PERIV"],
    "QALS":  ["QALS", "ART", "WERKS", "MATNR", "QNDAT", "STTTXT", "VDATU"],
    "QAVE":  ["QALS", "QUNUM", "QUPOS", "MBLNR", "QMENA"],
    "QMEL":  ["QMNUM", "QMTXT", "QMDAT", "STRMN", "QMART", "IEQUNR"],
    "MAPL":  ["WERKS", "PLNTY", "PLNNR", "MATNR", "APLFL"],
    "PLMK":  ["PLNTY", "PLNNR", "PLNKN", "KNNUM", "ATTYP"],
    "PRPS":  ["PSPNR", "POSKI", "POST1", "PBUKR", "PSPID", "PRART"],
    "AFVC":  ["NPLNR", "POSNR", "VORNR", "LTXA1", "ARBID", "ARBID"],
    "AFVV":  ["NPLNR", "POSNR", "VORNR", "DAUSO", "BUEGA"],
    "RESB":  ["RSNUM", "RSPOS", "MATNR", "BDMNG", "ENMNG", "WERKS"],
    "ANLA":  ["ANLN1", "ANLN2", "BUKRS", "AKTIV", "NDJAR", "NAFAK"],
    "ANLB":  ["ANLN1", "BUKRS", "BDATJ", "PERAF", "AFABG", "NDAFA"],
    "LQUA":  ["LENUM", "MATNR", "WERKS", "LGORT", "KLEND", "LETYP"],
    "LAGP":  ["LGTYP", "WERKS", "LTYP", "LABST", "LNAME"],
    "MLGN":  ["MATNR", "WERKS", "LGORT", "LGTYP"],
    "MLGT":  ["MATNR", "WERKS", "LGTYP", "LTGVAL"],
    "LEU4":  ["TONUM", "TOLNR", "QNAME", "BWLVS"],
    "LTBP":  ["TONUM", "TQLFD", "MATNR", "LENUM"],
    "VTTK":  ["TKNUM", "TDLNR", "TOTYP", "TSDAT"],
    "VTLP":  ["TKNUM", "TPLNR", "TPNNR"],
    "VTFA":  ["TKNUM", "TDFORMAT", "TDID"],
    "ASMD":  ["QMNUM", "ITAMC", "QMTXT", "STRMN", "EDATU", "ITEAM"],
    "IHPA":  ["OBJNR", "PARVW", "PARNR", "PAIST"],
    "DRAD":  ["RADBNR", "DOKNR", "DOKAR"],
    "PA0001":["PERNR", "ORGEH", "PLANS", "STELL", "BUKRS", "WERKS"],
    "PA0008":["PERNR", "FPFAS", "BETRG", "WAERS"],
    "IHK6":  ["EQUNR", "TPLNR", "EQTYP", "INGRP"],
    "EQUI":  ["EQUNR", "EQTYP", "TPLNR", "INGRP", "HERNR"],
    "IFLOT": ["OBJNR", "ILOAN", "EQUNR"],
    "VIMONI":["VKONT", "VTRMN", "VTDAT", "VAMNG", "VAKEY"],
    "VIBDT": ["KUNNR", "LAND1", "STCEG", "VTREF"],
    "/SAPSLL/POD": ["PODHANDLE", "VBELN", "PODDT"],
    "/SAPSLL/PNTPR": ["PARNR", "PARKZ", "LAND1", "STCDT"],
    "OIB_A04":["TPLNR", "TATYP", "OBJNR"],
    "OIG_V": ["OIBNR", "VPRGSNR", "VOLNR"],
    "T8JV":  ["JVCD", "BUKRS", "DATBI"],
    "EVBS":  ["GERNR", "ANLAGE", "SOLLN"],
    "EANL":  ["ANLAGE", "EQUNR", "SPERB"],
    "EGERR": ["FEGRP", "FETYP", "FENUM", "STICH"],
    "WRS1":  ["BWONNR", "EPOID", "MATNR", "WONNR"],
    "SETY":  ["SRTID", "SETID", "KTXTS"],
    "NPAT":  ["PATNR", "SUBJNR", "NAMZA"],
    "NBEW":  ["PATNR", "VKONT", "SUBJNR"],
    "NPNZ":  ["NPANR", "PPNVP", "NPNR1"],
    "CABN":  ["ATINN", "ATZHL", "ATNAM", "ATTLP"],
    "KLAH":  ["CLINT", "KLART", "CLSNM"],
    "CUOBJ": ["CUOBJ", "CLINT", "CADZEIZU"],
    "INOB":  ["OBJEK", "OBTYP", "KLART"],
    "J_1IG_HSN_SAC": ["STEGR", "SUBSTCODE", "KSCHL_WST"],
    "J_1BBRANCH": ["BUKRS", "BRANCH", "GSTIN"],
    "A003":  ["KAPPL", "KSCHL", "VKORG", "VTWEG", "MATNR", "LAND1"],
    "MCH1":  ["MATNR", "CHARG", "WERKS", "CLABS", "CINSM"],
    "MCHA":  ["MATNR", "CHARG", "BWTYP"],
    "BUT000": ["PARTNER", "BU_GROUP", "NAME_ORG1"],
    "BUT020": ["PARTNER", "ADDRNUMBER", "PERSNUMBER"],
}


# ─── Filter Rules ─────────────────────────────────────────────────────────────

FILTER_COLS = {
    "LFA1":  ["LIFNR", "LAND1", "KTOKK"],
    "KNA1":  ["KUNNR", "LAND1", "KDKG1"],
    "MARA":  ["MATNR", "MTART", "MBRSH", "MATKL"],
    "MARC":  ["MATNR", "WERKS", "DISPO"],
    "MARD":  ["MATNR", "WERKS", "LGORT"],
    "MBEW":  ["MATNR", "BWKEY"],
    "EKKO":  ["EBELN", "LIFNR", "BEDAT", "BSART", "EKGRP"],
    "EKPO":  ["EBELN", "MATNR", "WERKS"],
    "EINA":  ["LIFNR", "MATNR", "DATBI"],
    "VBAK":  ["VBELN", "KUNNR", "VKORG", "AUART", "AUDAT"],
    "VBAP":  ["VBELN", "MATNR"],
    "LIKP":  ["VBELN", "KUNNR", "WADAT"],
    "VBRK":  ["VBELN", "KUNNR", "FKDAT"],
    "BKPF":  ["BELNR", "BUKRS", "BLDAT"],
    "BSEG":  ["BELNR", "BUKRS", "HKONT"],
    "BSIK":  ["LIFNR", "BUKRS", "ZBD1T"],
    "BSID":  ["KUNNR", "BUKRS", "ZBD1T"],
    "CSKS":  ["KOSTL", "KOKRS", "DATBI"],
    "COSP":  ["OBJNR", "GJAHR"],
    "QALS":  ["QALS", "WERKS", "MATNR"],
    "PRPS":  ["PSPNR", "PSPID"],
    "EQUI":  ["EQUNR", "TPLNR"],
    "LQUA":  ["MATNR", "WERKS", "LGORT"],
    "VTTK":  ["TKNUM", "TDLNR"],
    "PA0001":["PERNR", "ORGEH", "BUKRS"],
}


def _build_filter_str(table: str) -> List[str]:
    """Return optional filter fields for a table."""
    cols = FILTER_COLS.get(table, [])
    return [f"{table}.{c} = :{c}" for c in cols]


def _build_select_str(tables: List[str], primary_table: str) -> str:
    """Build a nice SELECT clause showing columns from all tables."""
    parts = []
    for t in tables:
        cols = SELECT_COLS.get(t, [])
        if not cols:
            parts.append(f"    -- {t} (no column mapping)")
        else:
            display_cols = [f"{t}.{c}" for c in cols[:5]]
            parts.append(f"    {', '.join(display_cols)}")
    return ",\n".join(parts)


def _alias_key(cond: str, aliases: Dict[str, str]) -> str:
    """Replace table names in a condition with aliases."""
    result = cond
    for t, a in aliases.items():
        result = result.replace(f"{t}.", f"{a}.")
    return result


def generate_sql_template(tables: List[str], joins: List[Tuple], 
                         primary_table: str, template_id: str) -> str:
    """Generate a full parameterized SQL template."""
    # Assign aliases
    aliases = {t: chr(ord('a') + i) for i, t in enumerate(tables)}
    ptable = primary_table or tables[0]
    palias = aliases.get(ptable, 'a')

    # Build JOIN clauses
    join_parts = []
    for t1, t2, cond in joins:
        a1 = aliases.get(t1, t1)
        a2 = aliases.get(t2, t2)
        rev_cond = _alias_key(cond, {t1: a1, t2: a2})
        join_parts.append(f"LEFT JOIN {t2} ON {rev_cond}")

    # Build WHERE
    filter_parts = [f"{palias}.MANDT = :P_MANDT"]
    opt_filters = _build_filter_str(ptable)
    filter_parts.extend([f"    -- AND {f} = :{f.upper()}" if ":" not in f else f"    -- AND {f}" for f in opt_filters[:4]])
    filter_parts.append("    -- AND {{additional_filters}}")

    select = _build_select_str(tables, ptable)
    join_sql = "\n".join(join_parts)

    order_col = SELECT_COLS.get(ptable, ['*'])[0]
    if order_col == '*':
        order_col = tables[0].split('_')[0] + '_ID'

    sql = f"""
SELECT
{select}
FROM {ptable}  -- module anchor: {template_id}
{join_sql}
WHERE
{chr(10).join(filter_parts)}
ORDER BY {palias}.{order_col} DESC
LIMIT 100;""".strip()

    return sql


def discover_all_paths(G, max_depth: int = 5) -> Dict[Tuple[str, str], List[List[str]]]:
    """Find cross-module paths between every module pair using BFS shortest path."""
    import heapq
    from collections import deque

    # Build module → tables mapping from graph
    module_tables: Dict[str, List[str]] = defaultdict(list)
    for node, data in G.nodes(data=True):
        module_tables[data.get('module', '?')].append(node)

    # Build edge lookup (undirected)
    edge_map: Dict[Tuple, dict] = {}
    adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)  # node -> [(neighbor, condition)]
    for u, v, d in G.edges(data=True):
        cond = d.get('condition', f'{u}.MANDT = {v}.MANDT')
        edge_map[(u, v)] = d
        edge_map[(v, u)] = d
        adj[u].append((v, cond))
        adj[v].append((u, cond))

    def bfs_shortest_paths(src: str, dst: str, max_d: int = 5) -> List[List[str]]:
        """Find up to 3 shortest paths (by hop count) using BFS."""
        if src == dst or src not in adj or dst not in adj:
            return []
        
        # BFS — store (path, cost) tuples
        queue = deque([([src], 0)])
        found = []
        visited = {src: 0}
        max_cost = max_d
        
        while queue and len(found) < 3:
            path, cost = queue.popleft()
            node = path[-1]
            
            if cost > max_cost:
                continue
            
            if node == dst:
                found.append(path)
                continue
            
            for neighbor, _ in adj[node]:
                new_cost = cost + 1
                if new_cost <= max_cost:
                    if neighbor not in visited or visited[neighbor] >= new_cost:
                        visited[neighbor] = new_cost
                        queue.append((path + [neighbor], new_cost))
        
        return found

    modules = list(module_tables.keys())
    pair_paths: Dict[Tuple[str, str], List[List[str]]] = {}

    for i, ma in enumerate(modules):
        for mb in modules[i+1:]:
            tables_a = module_tables[ma]
            tables_b = module_tables[mb]
            all_paths = []

            for src in tables_a:
                for dst in tables_b:
                    paths = bfs_shortest_paths(src, dst, max_d=max_depth)
                    all_paths.extend(paths)

            if all_paths:
                # Deduplicate by tuple
                seen = set()
                unique = []
                for p in all_paths:
                    key = tuple(p)
                    if key not in seen:
                        seen.add(key)
                        unique.append(p)
                # Sort by length (shorter = better)
                unique.sort(key=len)
                pair_paths[(ma, mb)] = unique[:3]  # max 3 variants

    return pair_paths, edge_map, module_tables


def main():
    print("Loading Graph...")
    G = GraphRAGManager().G
    print(f"  {G.number_of_nodes()} nodes, {G.number_of_edges()} edges\n")

    pair_paths, edge_map, module_tables = discover_all_paths(G)

    all_meta_paths = []
    path_id = 1

    # ── Cross-module meta-paths ───────────────────────────────────────────────
    for (ma, mb), paths in sorted(pair_paths.items()):
        key = (ma, mb)
        intents = INTENT_TEMPLATES.get(key, [])

        for variant_idx, path in enumerate(paths):
            # Pick intent template
            if intents:
                intent = intents[variant_idx % len(intents)]
                pid, name, desc, blooms = intent
                pid = f"{pid}_v{variant_idx+1}"
            else:
                pid = f"auto_{path_id:04d}"
                name = f"{ma} → {mb} Cross-Module Path"
                desc = f"Auto-discovered JOIN path from {ma} module to {mb} module ({len(path)} tables)."
                blooms = [ma.lower(), mb.lower()]

            # Build joins from path
            joins = []
            for i in range(len(path) - 1):
                t1, t2 = path[i], path[i+1]
                cond = edge_map.get((t1, t2), {}).get('condition', '')
                if not cond:
                    cond = edge_map.get((t2, t1), {}).get('condition', '')
                if not cond:
                    cond = f"{t1}.MANDT = {t2}.MANDT"
                joins.append((t1, t2, cond))

            # Build SQL template
            primary = path[0]
            sql = generate_sql_template(path, joins, primary, pid)

            # Example NL queries
            examples = [
                f"show me {ma} to {mb} data for this record",
                f"get {path[0]} with related {path[-1]} information",
                f"what is the {mb.lower()} impact for {path[0]}?",
            ]

            # Required + optional filters
            req_filters = [f"{path[0]}.MANDT = :P_MANDT"]
            opt_filters = _build_filter_str(path[0])

            all_meta_paths.append({
                "id": pid,
                "name": name,
                "desc": desc,
                "domain": "auto_generated",
                "module_pair": (ma, mb),
                "tables": path,
                "joins": joins,
                "blooms": blooms,
                "req_filters": req_filters,
                "opt_filters": opt_filters,
                "sql": sql,
                "examples": examples,
                "variant_idx": variant_idx,
            })
            path_id += 1

    # ── Per-module base view meta-paths ──────────────────────────────────────
    for module, tables in sorted(module_tables.items()):
        # Pick the 3 most important anchor tables per module
        anchors = {
            "MM": ["MARA", "MARC", "MARD"],
            "MM-PUR": ["EKKO", "EKPO", "EINA"],
            "BP": ["LFA1", "KNA1", "BUT000"],
            "SD": ["VBAK", "VBAP", "LIKP"],
            "FI": ["BKPF", "BSEG", "BSIK"],
            "CO": ["CSKS", "COSP", "CEPC"],
            "QM": ["QALS", "QAVE", "QMEL"],
            "WM": ["LQUA", "LAGP", "MLGN"],
            "PM": ["EQUI", "IHK6", "IFLOT"],
            "PS": ["PRPS", "AFVC", "RESB"],
            "TM": ["VTTK", "VTLP", "VTFA"],
            "CS": ["ASMD", "IHPA", "QMEL"],
            "HR": ["PA0001", "PA0008"],
            "RE": ["VIMONI", "VIBDT", "ANLA"],
            "GTS": ["/SAPSLL/PNTPR", "/SAPSLL/POD"],
            "IS-OIL": ["OIB_A04", "OIG_V"],
            "IS-UTILITY": ["EVBS", "EANL"],
            "IS-RETAIL": ["WRS1", "SETY"],
            "IS-HEALTH": ["NPAT", "NBEW"],
            "TAX": ["J_1IG_HSN_SAC", "J_1BBRANCH"],
            "LO-VC": ["CABN", "KLAH", "CUOBJ"],
        }.get(module, tables[:2])

        for table in anchors:
            if table not in G:
                continue
            cols = SELECT_COLS.get(table, ["*"])
            select_sql = ",\n    ".join([f"{table}.{c}" for c in cols[:6]])
            opt_filters = _build_filter_str(table)

            sql = f"""
SELECT
    {select_sql}
FROM {table}
WHERE
    {table}.MANDT = :P_MANDT
    -- AND {{additional_filters}}
LIMIT 100;""".strip()

            all_meta_paths.append({
                "id": f"base_{module.lower().replace('-','_')}_{table.lower()}",
                "name": f"{module} Base View: {table}",
                "desc": f"Base data retrieval for {table} ({module} module).",
                "domain": module.lower().replace('-', '_'),
                "module_pair": (module, module),
                "tables": [table],
                "joins": [],
                "blooms": [module.lower(), table.lower()],
                "req_filters": [f"{table}.MANDT = :P_MANDT"],
                "opt_filters": opt_filters,
                "sql": sql,
                "examples": [
                    f"show me all {table} records",
                    f"list {module} {table} data",
                    f"get {table} overview",
                ],
                "variant_idx": 0,
            })
            path_id += 1

    # ── Write output ──────────────────────────────────────────────────────────
    out_dir = os.path.join(os.path.dirname(__file__), 'backend', 'app', 'core', 'sql_patterns')
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'auto_meta_paths_v2.py')

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(
            f'"""\n'
            f'AUTO-GENERATED META-PATHS v2 — Full Graph Traversal\n'
            f'Total: {len(all_meta_paths)} meta-paths\n'
            f'Generated: auto_meta_path_generator_v2.py\n'
            f'"""\n\n'
        )

        import json as _json

        def _d(v):
            return _json.dumps(str(v), ensure_ascii=False)

        f.write("AUTO_META_PATHS_V2 = [\n\n")
        for p in all_meta_paths:
            ma, mb = p["module_pair"]
            blooms_s = _json.dumps(p["blooms"])
            req_s    = _json.dumps(p["req_filters"])
            opt_s    = _json.dumps(p["opt_filters"])
            ex_s     = _json.dumps(p["examples"])
            tables_s = _json.dumps(p["tables"])
            joins_s  = _json.dumps(p["joins"])
            sql_s    = _json.dumps(p["sql"])

            f.write(f'    # -- {p["id"]} --\n')
            f.write(f'    {{\n')
            f.write(f'        "id": {_d(p["id"])},\n')
            f.write(f'        "name": {_d(p["name"])},\n')
            f.write(f'        "business_description": {_d(p["desc"])},\n')
            f.write(f'        "domain": {_d(p["domain"])},\n')
            f.write(f'        "module_pair": {_d(f"{ma}-{mb}")},\n')
            f.write(f'        "tags": {blooms_s},\n')
            f.write(f'        "tables": {tables_s},\n')
            f.write(f'        "join_conditions": {joins_s},\n')
            f.write(f'        "required_filters": {req_s},\n')
            f.write(f'        "optional_filters": {opt_s},\n')
            f.write(f'        "sql_template": {sql_s},\n')
            f.write(f'        "example_queries": {ex_s},\n')
            f.write(f'        "confidence_boost": 0.15,\n')
            f.write(f'        "row_count_warning": "",\n')
            f.write(f'    }},\n\n')

        f.write("]\n")
        f.write(
            '\n# To merge into meta_path_library.py:\n'
            '# from app.core.sql_patterns.auto_meta_paths_v2 import AUTO_META_PATHS_V2\n'
            '# SAP_META_PATHS.extend(AUTO_META_PATHS_V2)\n'
        )

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"{'='*60}")
    print(f"  META-PATH GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Total meta-paths generated: {len(all_meta_paths)}")
    print(f"  Cross-module paths: {sum(1 for p in all_meta_paths if p['module_pair'][0] != p['module_pair'][1])}")
    print(f"  Base view paths: {sum(1 for p in all_meta_paths if p['module_pair'][0] == p['module_pair'][1])}")

    by_module = defaultdict(int)
    for p in all_meta_paths:
        by_module[p['module_pair'][0]] += 1
        by_module[p['module_pair'][1]] += 1

    print(f"\n  Paths by module involvement:")
    for mod, cnt in sorted(by_module.items(), key=lambda x: -x[1]):
        print(f"    {mod:20s}: {cnt:3d}")

    print(f"\n  Output: {out_path}")
    print(f"\n  Existing SAP_META_PATHS: 14")
    print(f"  Auto paths to add: {len(all_meta_paths)}")
    print(f"  Projected total: {14 + len(all_meta_paths)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
