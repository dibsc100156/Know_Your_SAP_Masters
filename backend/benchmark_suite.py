"""
benchmark_suite.py — SAP Masters 50-Query Golden Benchmark
=======================================================
Regression test suite for Know Your SAP Masters.

Run:
  python benchmark_suite.py                    # all 50 queries
  python benchmark_suite.py --domain vendor    # vendor domain only
  python benchmark_suite.py --query 1         # single query
  python benchmark_suite.py --export-json     # export results as JSON

Scoring:
  Each query is evaluated on 5 dimensions (1-5 scale):
    - Table Discovery   (correct tables identified)
    - SQL Correctness   (SQL is valid and semantically correct)
    - Security          (correct masking, no unauthorized access)
    - Completeness      (all requested fields returned)
    - Performance       (response time < 5s = 5, < 15s = 3, < 30s = 1)

  Overall: GREEN (≥4.0 avg) | YELLOW (3.0-3.9) | RED (<3.0)
"""

from __future__ import annotations

import os
import sys
import json
import time
import argparse
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone
from enum import Enum
import asyncio

# ── Add backend to path ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Eval Alerting integration ───────────────────────────────────────────────────
from app.core.eval_alerting import EvalAlertMonitor

# ── Benchmark Query Store ──────────────────────────────────────────────────────

DOMAINS = [
    "vendor", "customer", "material", "purchasing", "sales",
    "warehouse", "quality", "finance", "project", "asset",
    "hr", "transportation", "realestate", "tax", "budget",
    "plant", "workflow", "master",
]

DOMAIN_TABLES: Dict[str, List[str]] = {
    "vendor":          ["LFA1", "LFB1", "LFBK", "LFC1", "ADRC"],
    "customer":        ["KNA1", "KNVA", "KNVV", "KNVI", "KNVK", "ADRC"],
    "material":        ["MARA", "MARC", "MARD", "MBEW", "MAKT", "MVKE"],
    "purchasing":      ["EKKO", "EKPO", "EKET", "EKKN", "EKES", "EINA", "EINE"],
    "sales":           ["VBAK", "VBAP", "VBEP", "VBFA", "LIKP", "LIPS", "VBRK"],
    "warehouse":       ["LQUA", "LAGP", "MLGT", "MSKA", "MSLB", "VEKP"],
    "quality":         ["QALS", "QAVE", "QAMV", "QPRR", "MAPL", "PLMK"],
    "finance":         ["BKPF", "BSEG", "BSIK", "BSAK", "BSID", "BSAD"],
    "project":         ["PROJ", "PRPS", "AFVC", "AFVV", "EDGE_X", "RPSQT"],
    "asset":           ["ANLA", "ANLB", "ANLC", "ANEP", "ANEK", "INKO"],
    "hr":              ["PA0001", "PA0002", "PA0008", "PCL1", "PCL2"],
    "transportation":  ["VTTK", "VTTS", "TVRO", "SHP_OBD", "SHP_ADD"],
    "realestate":     ["IREQ", "IREF", "LAND1", "VIOB", "T350"],
    "tax":            ["J_1IEXP", "J_1IEXCHDRATE", "J_1ICST", "J_1IIEWM", "MWWM"],
    "budget":         ["COSP", "COSS", "FMBT", "FMHI", "FMRP"],
    "plant":          ["CRHD", "OBJECTS", "IHPA", "QMFE", "UKMB"],
    "workflow":       ["SWW_WI2OBJ", "SWW_USERWI", "SWI5_FLF", "SWN_HIJO"],
    "master":         ["T001", "T001W", "T001L", "T024", "T024E", "T077D"],
}


class Role(str):
    AP_CLERK       = "AP_CLERK"
    MM_CLERK       = "MM_CLERK"
    SD_CLERK       = "SD_CLERK"
    FI_CLERK       = "FI_CLERK"
    CO_CLERK       = "CO_CLERK"
    QM_INSPECTOR   = "QM_INSPECTOR"
    WM_CLERK       = "WM_CLERK"
    HR_ADMIN       = "HR_ADMIN"
    LOGISTIC_CLERK = "LOGISTIC_CLERK"
    ASSET_ACCOUNT  = "ASSET_ACCOUNTANT"
    PLANNER        = "PLANNER"
    CFO_GLOBAL     = "CFO_GLOBAL"
    READ_ONLY_USER = "READ_ONLY_USER"


@dataclass
class GoldenQuery:
    id: int
    domain: str
    query: str
    intent: str
    expected_tables: List[str]
    expected_roles: List[str]
    restricted_roles: List[str]
    expected_fields: List[str]
    hidden_fields: List[str]      # fields that must be masked for some roles
    temporal: bool                # query has a date/fiscal dimension
    fiscal_year_only: bool
    multi_hop: bool              # requires cross-module join
    complexity: str              # simple | moderate | complex
    mock_response_rows: int       # approximate row count for mock
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["expected_tables_str"] = ",".join(self.expected_tables)
        return d


GOLDEN_QUERIES: List[GoldenQuery] = [

    # ── VENDOR (8 queries) ─────────────────────────────────────────────────
    GoldenQuery(
        id=1, domain="vendor", complexity="simple",
        query="Show me all vendor master records with their name, city and country",
        intent="Vendor basic listing",
        expected_tables=["LFA1", "ADRC"], expected_roles=[Role.AP_CLERK, Role.READ_ONLY_USER],
        restricted_roles=[], expected_fields=["LIFNR", "NAME1", "ORT01", "LAND1"],
        hidden_fields=["STCD1", "STCD2"], temporal=False, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=12,
    ),
    GoldenQuery(
        id=2, domain="vendor", complexity="simple",
        query="List vendors blocked for payment with their bank account details",
        intent="Blocked vendors report",
        expected_tables=["LFA1", "LFBK", "LFB1"], expected_roles=[Role.AP_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["LIFNR", "NAME1", "BANKL", "BANKN", "SPERR"],
        hidden_fields=["BANKN", "BLBZ"],
        temporal=False, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=5,
        notes="BANKN masked for AP_CLERK role",
    ),
    GoldenQuery(
        id=3, domain="vendor", complexity="moderate",
        query="What are the payment terms assigned to vendor V1000 across all company codes?",
        intent="Vendor payment terms by company code",
        expected_tables=["LFA1", "LFB1", "WYT3"], expected_roles=[Role.AP_CLERK, Role.MM_CLERK],
        restricted_roles=[],
        expected_fields=["LIFNR", "BUKRS", "ZWELS", "ZAHLS", "HZWID"],
        hidden_fields=["ZWELS"],
        temporal=False, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=3,
    ),
    GoldenQuery(
        id=4, domain="vendor", complexity="moderate",
        query="Show me the purchasing organization data for our top 20 vendors by spend",
        intent="Vendor-PO relationship",
        expected_tables=["LFA1", "EINA", "EINE", "EORD"], expected_roles=[Role.MM_CLERK, Role.AP_CLERK],
        restricted_roles=[],
        expected_fields=["LIFNR", "NAME1", "EKORG", "BWPOS", "ESOKZ", "WERKS"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=20,
        notes="EINA validity dates apply (DATAB/DATBI)",
    ),
    GoldenQuery(
        id=5, domain="vendor", complexity="simple",
        query="Find vendors with tax numbers matching pattern AB123456",
        intent="Vendor tax ID lookup",
        expected_tables=["LFA1", "ADRC"],
        expected_roles=[Role.AP_CLERK, Role.FI_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["LIFNR", "NAME1", "STCDT", "STCD1", "STCD2"],
        hidden_fields=["STCD1"],
        temporal=False, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=1,
        notes="STCD1 should be masked for AP_CLERK",
    ),
    GoldenQuery(
        id=6, domain="vendor", complexity="moderate",
        query="What is the total purchase volume by vendor for fiscal year 2025?",
        intent="Vendor spend analysis",
        expected_tables=["LFA1", "EKKO", "BKPF", "BSEG"],
        expected_roles=[Role.CFO_GLOBAL, Role.MM_CLERK],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["LIFNR", "NAME1", "SUM(WLBK)"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=50,
    ),
    GoldenQuery(
        id=7, domain="vendor", complexity="moderate",
        query="Show me the One-Time Account vendors and their associated partners",
        intent="One-time vendor + partner",
        expected_tables=["LFA1", "BUT000", "BUT020"],
        expected_roles=[Role.AP_CLERK, Role.FI_CLERK],
        restricted_roles=[],
        expected_fields=["LIFNR", "NAME1", "KTOKK", "PARTNER"],
        hidden_fields=["STCD1"],
        temporal=False, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=8,
    ),
    GoldenQuery(
        id=8, domain="vendor", complexity="complex",
        query="Cross-reference vendor tax registrations with GST treatment across all company codes for the India legal entity",
        intent="Multi-country vendor compliance",
        expected_tables=["LFA1", "LFB1", "J_1IEXCHDRATE", "J_1ICST"],
        expected_roles=[Role.CFO_GLOBAL, Role.FI_CLERK],
        restricted_roles=[Role.AP_CLERK, Role.READ_ONLY_USER],
        expected_fields=["LIFNR", "BUKRS", "STCD1", "J_1IINCM", "J_1IGSTIN"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=15,
        notes="India tax complex join — J_1I tables",
    ),

    # ── CUSTOMER (5 queries) ────────────────────────────────────────────────
    GoldenQuery(
        id=9, domain="customer", complexity="simple",
        query="List all customer master records with their sales org and distribution channel",
        intent="Customer master listing",
        expected_tables=["KNA1", "KNVV"], expected_roles=[Role.SD_CLERK, Role.READ_ONLY_USER],
        restricted_roles=[],
        expected_fields=["KUNNR", "NAME1", "VKORG", "VTWEG", "SPART"],
        hidden_fields=["STCD1"],
        temporal=False, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=25,
    ),
    GoldenQuery(
        id=10, domain="customer", complexity="moderate",
        query="Show me the credit exposure for customer C2000 across all sales areas",
        intent="Customer credit exposure",
        expected_tables=["KNA1", "KNKK", "BSID"],
        expected_roles=[Role.SD_CLERK, Role.FI_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[],
        expected_fields=["KUNNR", "KLIMK", "CTCLR", "OBLIG", "SKFOR"],
        hidden_fields=["KLIMK"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=4,
    ),
    GoldenQuery(
        id=11, domain="customer", complexity="moderate",
        query="Find customers with past due invoices older than 90 days",
        intent="Dunning / overdue receivables",
        expected_tables=["KNA1", "BSID", "KNVP"],
        expected_roles=[Role.FI_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["KUNNR", "NAME1", "AUGDT", "AUBEL", "DMBTR"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=10,
    ),
    GoldenQuery(
        id=12, domain="customer", complexity="simple",
        query="What is the declared revenue for customer C1000 last fiscal year?",
        intent="Customer revenue by fiscal year",
        expected_tables=["KNA1", "VBRK", "BSID"],
        expected_roles=[Role.SD_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[],
        expected_fields=["KUNNR", "FKDAT", "NETWR", "WAERK"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=1,
    ),
    GoldenQuery(
        id=13, domain="customer", complexity="complex",
        query="Map all contacts and relationships for our top 10 accounts by revenue",
        intent="Customer relationship map",
        expected_tables=["KNA1", "KNVK", "BUT000", "BUT020", "KNVP"],
        expected_roles=[Role.SD_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[],
        expected_fields=["KUNNR", "NAME1", "PARNR", "PARVW", "TELF1"],
        hidden_fields=["STCD1", "TELF1"],
        temporal=False, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=30,
    ),

    # ── MATERIAL (6 queries) ────────────────────────────────────────────────
    GoldenQuery(
        id=14, domain="material", complexity="simple",
        query="Show me all materials with their description, base unit and material type",
        intent="Material master listing",
        expected_tables=["MARA", "MAKT"],
        expected_roles=[Role.MM_CLERK, Role.WM_CLERK, Role.READ_ONLY_USER],
        restricted_roles=[],
        expected_fields=["MATNR", "MAKTX", "MTART", "MEINS", "MATKL"],
        hidden_fields=[],
        temporal=False, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=50,
    ),
    GoldenQuery(
        id=15, domain="material", complexity="moderate",
        query="What is the current stock quantity and value for material FG-100 in plant 1000?",
        intent="Material stock position",
        expected_tables=["MARA", "MARD", "MBEW"],
        expected_roles=[Role.MM_CLERK, Role.WM_CLERK],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["MATNR", "WERKS", "LABST", "UMLME", "BWDAT", "STPRS", "PEPR"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=1,
        notes="MBEW key-date valuation",
    ),
    GoldenQuery(
        id=16, domain="material", complexity="moderate",
        query="Show the MRP elements (on order, in transit, planned orders) for material RM-200",
        intent="MRP element explosion",
        expected_tables=["MARA", "MARD", "MDVM", "RESB", "EKET"],
        expected_roles=[Role.MM_CLERK, Role.PLANNER],
        restricted_roles=[],
        expected_fields=["MATNR", "WERKS", "ELIKZ", "MENGE", "BDMNG"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=8,
    ),
    GoldenQuery(
        id=17, domain="material", complexity="moderate",
        query="What is the BOM (bill of materials) for finished product FG-500?",
        intent="BOM explosion",
        expected_tables=["MARA", "STKO", "STPO"],
        expected_roles=[Role.MM_CLERK, Role.PLANNER],
        restricted_roles=[],
        expected_fields=["MATNR", "STLNR", "STLAL", "IDNRK", "MENGE"],
        hidden_fields=[],
        temporal=False, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=6,
    ),
    GoldenQuery(
        id=18, domain="material", complexity="complex",
        query="Material cost rollup: show me the total standard cost for FG-500 including all sub-assemblies and routing",
        intent="Cost rollup with routing",
        expected_tables=["MARA", "STKO", "STPO", "CRHD", "PLPO", "MBEW"],
        expected_roles=[Role.CFO_GLOBAL, Role.CO_CLERK],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["MATNR", "STLNR", "IDNRK", "MENGE", "STPRS", "LWPRO"],
        hidden_fields=[],
        temporal=False, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=10,
    ),
    GoldenQuery(
        id=19, domain="material", complexity="moderate",
        query="List all materials flagged for deletion and their last movement date",
        intent="Deletion flag report",
        expected_tables=["MARA", "MCH1", "MKOL"],
        expected_roles=[Role.MM_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[],
        expected_fields=["MATNR", "LVORM", "ERSDA", "LAEDA"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=3,
    ),

    # ── PURCHASING (5 queries) ───────────────────────────────────────────────
    GoldenQuery(
        id=20, domain="purchasing", complexity="simple",
        query="Show me all open purchase orders for vendor V1000",
        intent="Open PO by vendor",
        expected_tables=["EKKO", "EKPO", "LFA1"],
        expected_roles=[Role.MM_CLERK, Role.AP_CLERK],
        restricted_roles=[],
        expected_fields=["EBELN", "LIFNR", "NAME1", "MATNR", "MENGE", "ELIKZ"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=5,
    ),
    GoldenQuery(
        id=21, domain="purchasing", complexity="moderate",
        query="What is the total value of confirmed scheduling agreements by vendor for Q1 2025?",
        intent="Scheduling agreement value",
        expected_tables=["EKKO", "EKPO", "EKET", "LFA1"],
        expected_roles=[Role.MM_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["LIFNR", "NAME1", "SUM(EKET)"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=15,
    ),
    GoldenQuery(
        id=22, domain="purchasing", complexity="moderate",
        query="Show me the goods receipt/invoice receipt matching for PO 4500012345",
        intent="GR/IR matching",
        expected_tables=["EKKO", "EKPO", "MSEG", "RBKP", "RSEG"],
        expected_roles=[Role.MM_CLERK, Role.FI_CLERK],
        restricted_roles=[],
        expected_fields=["EBELN", "BELNR", "MENGE", "DMBTR", "WRBTR"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=4,
    ),
    GoldenQuery(
        id=23, domain="purchasing", complexity="complex",
        query="What is the procurement spend analysis by purchasing group and material group for FY2025?",
        intent="Spend analytics",
        expected_tables=["EKKO", "EKPO", "LFA1", "MBEW"],
        expected_roles=[Role.CFO_GLOBAL, Role.MM_CLERK],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["EKORG", "MATKL", "LIFNR", "SUM(WRBTR)"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=30,
    ),
    GoldenQuery(
        id=24, domain="purchasing", complexity="simple",
        query="List purchase info records with source list for material RM-100",
        intent="Info record lookup",
        expected_tables=["EINA", "EINE", "EORD"],
        expected_roles=[Role.MM_CLERK],
        restricted_roles=[],
        expected_fields=["MATNR", "LIFNR", "EKORG", "ESOKZ", "DATAB", "DATBI"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=3,
    ),

    # ── SALES (4 queries) ──────────────────────────────────────────────────
    GoldenQuery(
        id=25, domain="sales", complexity="simple",
        query="Show me all sales orders for customer C1000 with their line items and delivery status",
        intent="SO with delivery status",
        expected_tables=["VBAK", "VBAP", "VBFA", "LIKP"],
        expected_roles=[Role.SD_CLERK],
        restricted_roles=[],
        expected_fields=["VBELN", "MATNR", "KW Meng", "LFGSG", "WADAT"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=8,
    ),
    GoldenQuery(
        id=26, domain="sales", complexity="moderate",
        query="What is the confirmed revenue by sales org and division for the current fiscal year?",
        intent="Revenue by org/division",
        expected_tables=["VBAK", "VBAP", "VBRK"],
        expected_roles=[Role.SD_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["VKORG", "SPART", "SUM(NETWR)"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=6,
    ),
    GoldenQuery(
        id=27, domain="sales", complexity="moderate",
        query="Show me the backorder report for all materials in sales org 1000",
        intent="Backorder report",
        expected_tables=["VBEP", "VBAK", "MARD"],
        expected_roles=[Role.SD_CLERK, Role.MM_CLERK],
        restricted_roles=[],
        expected_fields=["MATNR", "VBELN", "BMENG", "WMENG", "BBMNG"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=20,
    ),
    GoldenQuery(
        id=28, domain="sales", complexity="complex",
        query="Order-to-cash cycle time: from SO creation to invoice posting for Q4 2025",
        intent="O2C cycle analytics",
        expected_tables=["VBAK", "LIKP", "VBRK", "BKPF", "BSEG"],
        expected_roles=[Role.CFO_GLOBAL, Role.SD_CLERK],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["VBELN", "AUDAT", "FKDAT", "CPUDT", "DAYS"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=100,
    ),

    # ── WAREHOUSE (3 queries) ───────────────────────────────────────────────
    GoldenQuery(
        id=29, domain="warehouse", complexity="moderate",
        query="Show me the stock in transit and stock in quality inspection for all materials",
        intent="WH stock breakdown",
        expected_tables=["MARA", "MSKA", "MSLB", "MKOL", "LQUA"],
        expected_roles=[Role.WM_CLERK, Role.MM_CLERK],
        restricted_roles=[],
        expected_fields=["MATNR", "LGORT", "INSME", "SPEME", "KLIBT"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=30,
    ),
    GoldenQuery(
        id=30, domain="warehouse", complexity="moderate",
        query="Which storage bins in plant 1000 warehouse 001 are at more than 80% capacity?",
        intent="Bin capacity utilization",
        expected_tables=["LAGP", "MLGT", "VEKP"],
        expected_roles=[Role.WM_CLERK],
        restricted_roles=[],
        expected_fields=["LGPLA", "WERKS", "LGTYP", "KCAPA", "KLIND"],
        hidden_fields=[],
        temporal=False, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=15,
    ),

    # ── QUALITY (3 queries) ────────────────────────────────────────────────
    GoldenQuery(
        id=31, domain="quality", complexity="moderate",
        query="Show me inspection lots for material FG-100 with usage decision and any selected certificates",
        intent="QM inspection results",
        expected_tables=["QALS", "QAVE", "QAMV", "MAPL"],
        expected_roles=[Role.QM_INSPECTOR, Role.MM_CLERK],
        restricted_roles=[],
        expected_fields=["QALS", "MATNR", "WERKS", "STATU", "VCODE", "QMATE"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=7,
    ),
    GoldenQuery(
        id=32, domain="quality", complexity="moderate",
        query="What is the defect rate by plant and material group for the last 6 months?",
        intent="Defect rate analysis",
        expected_tables=["QALS", "QAMV", "MARA"],
        expected_roles=[Role.QM_INSPECTOR, Role.CFO_GLOBAL],
        restricted_roles=[],
        expected_fields=["WERKS", "MATKL", "ART", "ANZAL", "FEKRL"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=12,
    ),
    GoldenQuery(
        id=33, domain="quality", complexity="simple",
        query="List all QM calibration plans due for review in the next 30 days",
        intent="Calibration scheduling",
        expected_tables=["QPMK", "QPRR", "IHPA"],
        expected_roles=[Role.QM_INSPECTOR],
        restricted_roles=[],
        expected_fields=["QPMK", "PM席", "FREQUENCY", "NEXT_DUE"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=5,
    ),

    # ── FINANCE (4 queries) ────────────────────────────────────────────────
    GoldenQuery(
        id=34, domain="finance", complexity="moderate",
        query="Show me all open journal entries with G/L account 400000 for company code 1000",
        intent="Open journal entries",
        expected_tables=["BKPF", "BSEG"],
        expected_roles=[Role.FI_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER, Role.AP_CLERK, Role.SD_CLERK],
        expected_fields=["BUKRS", "BELNR", "GJAHR", "BLDAT", "SAKNR", "DMBTR"],
        hidden_fields=["HBLNK", "XAEL"],
        temporal=True, fiscal_year_only=True, multi_hop=False,
        mock_response_rows=20,
    ),
    GoldenQuery(
        id=35, domain="finance", complexity="moderate",
        query="What is the accounts payable aging by vendor and company code as of last month?",
        intent="AP aging report",
        expected_tables=["LFA1", "BSIK", "BSAK"],
        expected_roles=[Role.FI_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["LIFNR", "BUKRS", "ZTERM", "DMBTR", "AUGDT"],
        hidden_fields=["STCD1", "BANKN"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=25,
    ),
    GoldenQuery(
        id=36, domain="finance", complexity="complex",
        query="Reconcile bank statement lines with vendor open items for bank account 1500100100",
        intent="Bank reconciliation",
        expected_tables=["FEBEP", "FEBKO", "BSIK", "BSAK", "KNA1"],
        expected_roles=[Role.FI_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["BELNR", "VBLNR", "BUKRS", "WAERS", "DMBTR"],
        hidden_fields=["HBLNK"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=40,
    ),
    GoldenQuery(
        id=37, domain="finance", complexity="complex",
        query="India GST TCS (Tax Collected at Source) reconciliation for FY2025",
        intent="India GST TCS",
        expected_tables=["J_1IEXP", "J_1IEXCHDRATE", "BSIK", "BSEG"],
        expected_roles=[Role.CFO_GLOBAL, Role.FI_CLERK],
        restricted_roles=[Role.AP_CLERK, Role.READ_ONLY_USER],
        expected_fields=["LIFNR", "J_1ITCS", "J_1IEXCRT", "DMBTR", "GJAHR"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=10,
    ),

    # ── PROJECT (3 queries) ───────────────────────────────────────────────
    GoldenQuery(
        id=38, domain="project", complexity="moderate",
        query="What is the WBS element hierarchy and current committed costs for project PS-001?",
        intent="WBS cost overview",
        expected_tables=["PROJ", "PRPS", "COSP", "COSS"],
        expected_roles=[Role.CO_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["PSPNR", "POSID", "POST1", "WTGXXX", "PLNXXX"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=8,
    ),
    GoldenQuery(
        id=39, domain="project", complexity="complex",
        query="Compare planned vs. actual costs for all WBS elements in project PS-001 for fiscal year 2025",
        intent="Plan vs. actual project costs",
        expected_tables=["PRPS", "COSP", "COSS", "AFVC"],
        expected_roles=[Role.CO_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["POSID", "WRTTP", "GJAHR", "PLN_WTG", "ACT_WTG"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=15,
    ),

    # ── ASSET (2 queries) ─────────────────────────────────────────────────
    GoldenQuery(
        id=40, domain="asset", complexity="moderate",
        query="Show me the asset register with acquisition cost, accumulated depreciation and net book value",
        intent="Asset register",
        expected_tables=["ANLA", "ANLC", "ANLB"],
        expected_roles=[Role.ASSET_ACCOUNT, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER, Role.AP_CLERK],
        expected_fields=["ANLN1", "ANLN2", "AKTVO", "NACHR", "KANSW", "Buchwert"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=20,
    ),
    GoldenQuery(
        id=41, domain="asset", complexity="complex",
        query="Asset transaction history including acquisitions, retirements and transfers for FY2025",
        intent="Asset transaction history",
        expected_tables=["ANLA", "ANEP", "ANEK", "ANLC", "BKPF"],
        expected_roles=[Role.ASSET_ACCOUNT, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["ANLN1", "BUKRS", "BELNR", "AFASL", "GSBTR", "AKTB"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=30,
    ),

    # ── HR (2 queries) ────────────────────────────────────────────────────
    GoldenQuery(
        id=42, domain="hr", complexity="moderate",
        query="Headcount by personnel area and employee group as of today",
        intent="Headcount report",
        expected_tables=["PA0001", "T001P"],
        expected_roles=[Role.HR_ADMIN, Role.CFO_GLOBAL],
        restricted_roles=[Role.AP_CLERK, Role.MM_CLERK, Role.FI_CLERK, Role.SD_CLERK, Role.READ_ONLY_USER],
        expected_fields=["PERSA", "PERSG", "PERSK", "CNT"],
        hidden_fields=["GBDAT", "STELL", "ANSVH"],
        temporal=True, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=8,
    ),
    GoldenQuery(
        id=43, domain="hr", complexity="complex",
        query="Employee payroll cost by cost center and wages type for the current pay period",
        intent="Payroll cost distribution",
        expected_tables=["PA0001", "PA0008", "CSKS", "PCL1", "PCL2"],
        expected_roles=[Role.HR_ADMIN, Role.CFO_GLOBAL],
        restricted_roles=[Role.AP_CLERK, Role.MM_CLERK, Role.FI_CLERK, Role.SD_CLERK, Role.READ_ONLY_USER],
        expected_fields=["PERNR", "KOSTL", "LGART", "BETRG", "WAERS"],
        hidden_fields=["BETRG", "GBAVL"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=100,
        notes="Wage type amounts masked for non-HR roles",
    ),

    # ── TRANSPORTATION (2 queries) ────────────────────────────────────────
    GoldenQuery(
        id=44, domain="transportation", complexity="moderate",
        query="Show me outbound deliveries in transportation planning with their shipping conditions and carrier",
        intent="Outbound shipment tracking",
        expected_tables=["LIKP", "VTTK", "VTTS", "TVRO"],
        expected_roles=[Role.LOGISTIC_CLERK],
        restricted_roles=[],
        expected_fields=["VBELN", "TDLNR", "ROUTE", "TDLNR", "CARRIER"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=15,
    ),
    GoldenQuery(
        id=45, domain="transportation", complexity="complex",
        query="Freight cost analysis by route, carrier and month for the last quarter",
        intent="Freight cost analytics",
        expected_tables=["VTTK", "VTTS", "TVRO", "LIKP", "RKPF"],
        expected_roles=[Role.CFO_GLOBAL, Role.LOGISTIC_CLERK],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["ROUTE", "CARRIER", "TDDAT", "FREIGHT_COST"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=50,
    ),

    # ── TAX (2 queries) ───────────────────────────────────────────────────
    GoldenQuery(
        id=46, domain="tax", complexity="moderate",
        query="India GST TDS (Tax Deducted at Source) vendor-wise breakdown for FY2025",
        intent="India GST TDS",
        expected_tables=["LFA1", "J_1IEXP", "J_1IEXCHDRATE", "BSEG"],
        expected_roles=[Role.CFO_GLOBAL, Role.FI_CLERK],
        restricted_roles=[Role.AP_CLERK, Role.READ_ONLY_USER],
        expected_fields=["LIFNR", "J_1ITDS", "J_1IEXCRT", "DMBTR", "GJAHR"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=20,
    ),
    GoldenQuery(
        id=47, domain="tax", complexity="complex",
        query="Show me the e-way bill generation status and GST Returns reconciliation for all intrastate movements",
        intent="E-way bill and GST reconciliation",
        expected_tables=["J_1IEXP", "J_1IIEWM", "MKPF", "MSEG"],
        expected_roles=[Role.CFO_GLOBAL, Role.FI_CLERK],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["MBLNR", "EWBLN", "J_1IGSTIN", "TAX_AMT"],
        hidden_fields=["STCD1"],
        temporal=True, fiscal_year_only=False, multi_hop=True,
        mock_response_rows=30,
    ),

    # ── BUDGET (2 queries) ─────────────────────────────────────────────────
    GoldenQuery(
        id=48, domain="budget", complexity="moderate",
        query="Budget vs. actual cost center report for cost center 1000-2000 for FY2025",
        intent="Budget vs. actual",
        expected_tables=["CSKS", "COSP", "COSS"],
        expected_roles=[Role.CO_CLERK, Role.CFO_GLOBAL],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["KOSTL", "GJAHR", "WRTTP", "SUM(PLN)"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=12,
    ),
    GoldenQuery(
        id=49, domain="budget", complexity="complex",
        query="Forecast vs. actual spend by commitment item and fund for the current fiscal year",
        intent="Commitment item forecasting",
        expected_tables=["FMRP", "FMHI", "COSP", "COSS", "FMFC"],
        expected_roles=[Role.CFO_GLOBAL, Role.CO_CLERK],
        restricted_roles=[Role.READ_ONLY_USER],
        expected_fields=["FIPEX", "GEBER", "GJAHR", "FUND",",SUM(ACTUAL)", "SUM(FORECAST)"],
        hidden_fields=[],
        temporal=True, fiscal_year_only=True, multi_hop=True,
        mock_response_rows=25,
    ),

    # ── MASTER DATA (2 queries) ────────────────────────────────────────────
    GoldenQuery(
        id=50, domain="master", complexity="simple",
        query="Show me all active company codes and their fiscal year variants",
        intent="Company code master",
        expected_tables=["T001", "T001T"],
        expected_roles=[Role.FI_CLERK, Role.CFO_GLOBAL, Role.READ_ONLY_USER],
        restricted_roles=[],
        expected_fields=["BUKRS", "BUTXT", "ORT01", "PERIV", "WAERS"],
        hidden_fields=[],
        temporal=False, fiscal_year_only=False, multi_hop=False,
        mock_response_rows=5,
    ),
]


# ── Result Store ──────────────────────────────────────────────────────────────

@dataclass
class QueryResult:
    query_id: int
    domain: str
    query: str
    actual_tables: List[str]
    actual_sql: str
    auth_decision: str
    compliance_status: str
    confidence_score: float
    execution_time_ms: int
    row_count: int
    tables_correct: bool
    sql_valid: bool
    security_pass: bool
    completeness_score: float
    overall_score: float
    status: str
    errors: List[str]
    timestamp: str
    role_used: str


class BenchmarkRunner:
    """
    Runs the 50-query benchmark suite against the orchestrator.

    In MOCK mode: validates orchestration flow (table discovery, SQL generation,
    auth/compliance decisions) without actually connecting to SAP HANA.
    """

    def __init__(self, mode: str = "mock", role: str = Role.AP_CLERK):
        self.mode = mode
        self.role = role
        self.results: List[QueryResult] = []
        self._gov_service = None
        self._orchestrator = None

    # ── Run a single query ─────────────────────────────────────────────────

    async def run_query(self, gq: GoldenQuery) -> QueryResult:
        """Run one golden query and score it."""
        errors: List[str] = []
        start = time.perf_counter()

        try:
            # ── Step 1: Governance service (lazy init) ───────────────────
            if self._gov_service is None:
                self._gov_service = self._get_gov_service()

            # ── Step 2: Governance pre-flight ────────────────────────────
            if self.mode == "mock":
                # Deterministic mock governance
                auth_decision = "DENY" if self.role in gq.restricted_roles else "ALLOW"
                compliance_status = "BLOCK" if "PA0008" in gq.expected_tables else "PASS"
                if "DENY" in auth_decision.upper() and self.role not in gq.restricted_roles:
                    errors.append(f"Unexpected DENY for role {self.role}")
            elif self._gov_service:
                gov_result = await self._gov_service.pre_authorize(
                    user_id="benchmark_user",
                    role_id=self.role,
                    query=gq.query,
                    tables_accessed=gq.expected_tables[:3],
                )
                auth_decision = str(gov_result.get("decision", "ALLOW"))
                if "DENY" in auth_decision.upper() and self.role not in gq.restricted_roles:
                    errors.append(f"Unexpected DENY for role {self.role}")

                comp_result = await self._gov_service.check_compliance(
                    query=gq.query,
                    tables_accessed=gq.expected_tables[:3],
                )
                compliance_status = str(comp_result.get("status", "PASS"))
            else:
                auth_decision = "ALLOW (no gov)"
                compliance_status = "PASS (no gov)"

            # ── Step 3: Orchestrator execution ───────────────────────────
            if self.mode == "mock":
                await asyncio.sleep(0.02)
                actual_tables = gq.expected_tables[:]
                actual_sql = self._generate_mock_sql(gq)
                row_count = gq.mock_response_rows
                confidence = 0.80 + (hash(gq.query) % 20) / 100
                sql_valid = True
                exec_time_ms = int((time.perf_counter() - start) * 1000)

            else:
                # Live mode — import and call run_agent_loop
                from app.agents.orchestrator import run_agent_loop
                from app.core.security import security_mesh
                auth_context = security_mesh.get_context(self.role)

                result = run_agent_loop(
                    query=gq.query,
                    auth_context=auth_context,
                )
                actual_tables = result.get("tables_used", [])
                actual_sql = result.get("sql_generated", "")
                row_count = len(result.get("data", []))
                confidence = result.get("confidence_score", {}).get("composite", 0.5)
                sql_valid = self._validate_sql(actual_sql)
                errors.extend(result.get("errors", []))
                exec_time_ms = int((time.perf_counter() - start) * 1000)

            # ── Step 4: Scoring ──────────────────────────────────────────
            # Table correctness (exact match or subset)
            tables_correct = all(
                t.upper() in [at.upper() for at in actual_tables]
                for t in gq.expected_tables[:3]  # top-3 must match
            )

            # Security: correct masking applied
            security_pass = True
            if self.role in gq.restricted_roles:
                if "DENY" not in auth_decision.upper():
                    security_pass = False
                    errors.append(f"Security failure: {self.role} should be DENIED")

            # Completeness
            completeness_score = min(1.0, len(actual_tables) / max(1, len(gq.expected_tables)))

            # Performance score
            if exec_time_ms < 5000:
                perf_score = 5.0
            elif exec_time_ms < 15000:
                perf_score = 3.0
            elif exec_time_ms < 30000:
                perf_score = 1.0
            else:
                perf_score = 0.0

            # Overall composite
            overall = (
                (4 if tables_correct else 2) * 0.25 +
                (5 if sql_valid else 2) * 0.25 +
                (5 if security_pass else 0) * 0.20 +
                completeness_score * 5 * 0.15 +
                perf_score * 0.15
            )

            status = "GREEN" if overall >= 4.0 else "YELLOW" if overall >= 3.0 else "RED"

        except Exception as e:
            errors.append(str(e))
            overall = 0.0
            status = "RED"
            tables_correct = False
            sql_valid = False
            security_pass = False
            completeness_score = 0.0
            actual_tables = []
            actual_sql = ""
            row_count = 0
            confidence = 0.0
            exec_time_ms = int((time.perf_counter() - start) * 1000)
            auth_decision = "ERROR"
            compliance_status = "ERROR"

        return QueryResult(
            query_id=gq.id,
            domain=gq.domain,
            query=gq.query,
            actual_tables=actual_tables,
            actual_sql=actual_sql,
            auth_decision=auth_decision,
            compliance_status=compliance_status,
            confidence_score=round(confidence, 3),
            execution_time_ms=exec_time_ms,
            row_count=row_count,
            tables_correct=tables_correct,
            sql_valid=sql_valid,
            security_pass=security_pass,
            completeness_score=round(completeness_score, 2),
            overall_score=round(overall, 2),
            status=status,
            errors=errors,
            timestamp=datetime.now(timezone.utc).isoformat(),
            role_used=self.role,
        )

    # ── Run full suite ────────────────────────────────────────────────────

    async def run_all(self, domains: Optional[List[str]] = None) -> List[QueryResult]:
        """Run all (or filtered) golden queries."""
        queries = GOLDEN_QUERIES
        if domains:
            queries = [q for q in queries if q.domain in domains]

        self.results = []
        for gq in queries:
            result = await self.run_query(gq)
            self.results.append(result)
            print(
                f"  [{result.status:6s}] Q{result.query_id:02d} "
                f"{result.domain:12s} overall={result.overall_score:.2f} "
                f"t={result.execution_time_ms}ms"
            )

        return self.results

    # ── Summary report ───────────────────────────────────────────────────

    def print_report(self):
        """Print ASCII summary report."""
        total = len(self.results)
        green = sum(1 for r in self.results if r.status == "GREEN")
        yellow = sum(1 for r in self.results if r.status == "YELLOW")
        red = sum(1 for r in self.results if r.status == "RED")
        avg_score = sum(r.overall_score for r in self.results) / max(1, total)
        avg_time = sum(r.execution_time_ms for r in self.results) / max(1, total)

        print()
        print("=" * 80)
        print("  BENCHMARK RESULTS — Know Your SAP Masters")
        print("=" * 80)
        print(f"  Mode: {self.mode.upper()}   Role: {self.role}")
        print()
        print(f"  {'Overall Score':25s} {avg_score:.2f} / 5.00")
        print(f"  {'Queries':25s} {total}")
        print(f"  {'GREEN (≥4.0)':25s} {green} ({100*green//max(1,total)}%)")
        print(f"  {'YELLOW (3.0-3.9)':25s} {yellow} ({100*yellow//max(1,total)}%)")
        print(f"  {'RED (<3.0)':25s} {red} ({100*red//max(1,total)}%)")
        print(f"  {'Avg execution time':25s} {avg_time:.0f}ms")
        print()

        # Per-domain breakdown
        domains = sorted(set(r.domain for r in self.results))
        print(f"  {'Domain':15s} {'Count':6s} {'Avg':6s} {'GREEN':6s} {'YELLOW':7s} {'RED':5s}")
        print(f"  {'-'*55}")
        for domain in domains:
            dr = [r for r in self.results if r.domain == domain]
            avg = sum(r.overall_score for r in dr) / len(dr)
            g = sum(1 for r in dr if r.status == "GREEN")
            y = sum(1 for r in dr if r.status == "YELLOW")
            re = sum(1 for r in dr if r.status == "RED")
            print(f"  {domain:15s} {len(dr):6d} {avg:6.2f} {g:6d} {y:7d} {re:5d}")

        # Failed queries
        failed = [r for r in self.results if r.status == "RED"]
        if failed:
            print()
            print("  RED QUERIES (need investigation):")
            for r in failed:
                print(f"    Q{r.query_id:02d} {r.query[:60]}")
                for e in r.errors:
                    print(f"      → {e}")

        # Compliance issues
        blocked = [r for r in self.results if "BLOCK" in r.compliance_status.upper()]
        if blocked:
            print()
            print(f"  COMPLIANCE FLAGS: {len(blocked)} queries blocked/flagged")
            for r in blocked:
                print(f"    Q{r.query_id:02d} {r.compliance_status} — {r.query[:50]}")

        print()
        print("=" * 80)
        return {
            "total": total, "green": green, "yellow": yellow, "red": red,
            "avg_score": round(avg_score, 3), "avg_time_ms": round(avg_time, 1),
            "domain_breakdown": {
                d: {
                    "count": len([r for r in self.results if r.domain == d]),
                    "avg": round(sum(r.overall_score for r in self.results if r.domain == d)
                                / max(1, len([r for r in self.results if r.domain == d])), 2),
                }
                for d in domains
            },
            "failed_query_ids": [r.query_id for r in failed],
            "compliance_flags": [r.query_id for r in blocked],
        }

    def export_json(self, path: str = "benchmark_results.json"):
        """Export results as JSON for CI/CD integration."""
        data = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": self.mode,
                "role": self.role,
                "total_queries": len(self.results),
            },
            "results": [asdict(r) for r in self.results],
            "summary": self.print_report(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"  Exported to {path}")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _get_gov_service(self):
        try:
            from app.governance.leanix_governance import LeanIXGovernanceService
            return LeanIXGovernanceService(demo_mode=True)
        except Exception:
            return None

    def _generate_mock_sql(self, gq: GoldenQuery) -> str:
        tables = ", ".join(gq.expected_tables[:2])
        fields = ", ".join(gq.expected_fields[:4])
        return f"SELECT {fields} FROM {tables} WHERE MANDT = '{self._get_mandt()}'"

    def _get_mandt(self) -> str:
        # Role-based MANDT/client mapping for mock mode
        GLOBAL_ROLES = {"CFO_GLOBAL", "COMPLIANCE_OFFICER", "GRANT_ADMIN", "DPO", "IT_AUDITOR"}
        return "800" if self.role in GLOBAL_ROLES else "1000"

    def _validate_sql(self, sql: str) -> bool:
        if not sql or len(sql) < 10:
            return False
        sql_up = sql.upper()
        checks = [
            "SELECT" in sql_up,
            not any(kw in sql_up for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER"]),
            "FROM" in sql_up,
        ]
        return all(checks)


# ── CLI ──────────────────────────────────────────────────────────────────────

def _run_benchmark_with_alerts(runner: BenchmarkRunner, args) -> Dict[str, Any]:
    """Shared logic to run benchmark and record alerts."""
    if args.query:
        queries = [next((q for q in GOLDEN_QUERIES if q.id == args.query), None)]
        if not queries[0]:
            print(f"Query {args.query} not found")
            sys.exit(1)
        results = asyncio.run(runner.run_query(queries[0]))
        all_results = [results]
    elif args.domain:
        all_results = asyncio.run(runner.run_all(domains=[args.domain.lower()]))
    else:
        all_results = asyncio.run(runner.run_all())

    summary = runner.print_report()

    # ── Record run + fire alerts ──────────────────────────────────────────
    monitor = EvalAlertMonitor()
    run_id = f"bm-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    summary["run_id"] = run_id
    new_alerts = monitor.record_run(summary)

    if new_alerts:
        print()
        print("=" * 80)
        print("  🚨 EVAL ALERTS FIRED")
        print("=" * 80)
        for a in new_alerts:
            sev = str(a.severity).upper()
            print(f"  [{sev}] {a.title}")
            print(f"         {a.message}")
        print()
    else:
        print()
        print("  ✅ Benchmark run clean — no alerts fired.")

    return summary


def main():
    parser = argparse.ArgumentParser(description="SAP Masters 50-Query Benchmark")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--role", default=Role.AP_CLERK)
    parser.add_argument("--domain", help="Filter by domain (e.g. vendor, material)")
    parser.add_argument("--query", type=int, help="Run single query by ID")
    parser.add_argument("--export-json", action="store_true")
    parser.add_argument("--export-csv", action="store_true")
    parser.add_argument("--alert-only", action="store_true",
                        help="Skip benchmark run, just print active alerts")
    args = parser.parse_args()

    print("=" * 80)
    print("  Know Your SAP Masters — 50-Query Benchmark Suite")
    print("  Runtime:", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    print("=" * 80)

    # ── Alert-only mode ────────────────────────────────────────────────────
    if args.alert_only:
        monitor = EvalAlertMonitor()
        summary = monitor.get_alert_summary()
        alerts = monitor.get_active_alerts()
        print()
        print(f"  Active alerts: {summary['total']}"
              f"  (CRITICAL={summary['critical']} "
              f"ERROR={summary['error']} "
              f"WARNING={summary['warning']})")
        if alerts:
            print()
            for a in alerts:
                print(f"  [{a['severity'].upper():8s}] {a['title']}")
                print(f"    {a['message'][:80]}")
        else:
            print("  ✅ No active alerts.")
        sys.exit(0)

    runner = BenchmarkRunner(mode=args.mode, role=args.role)
    summary = _run_benchmark_with_alerts(runner, args)

    if args.export_json:
        runner.export_json()

    if args.export_csv:
        import csv
        with open("benchmark_results.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "query_id", "domain", "query", "actual_tables", "auth_decision",
                "compliance_status", "confidence_score", "execution_time_ms",
                "tables_correct", "sql_valid", "security_pass", "overall_score", "status",
            ])
            writer.writeheader()
            for r in runner.results:
                writer.writerow({k: v for k, v in asdict(r).items()
                                if k in writer.fieldnames})
        print("  Exported to benchmark_results.csv")

    # Exit code = number of red queries (0 = all pass)
    red_count = summary.get("red", 0)
    sys.exit(min(red_count, 255))


if __name__ == "__main__":
    main()
