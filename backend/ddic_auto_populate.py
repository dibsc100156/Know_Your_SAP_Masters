"""
ddic_auto_populate.py — SAP DDIC Auto-Population Script
=========================================================
Auto-builds the enterprise FK graph from SAP DD08L (FK metadata).

Usage:
    # SEED MODE (no real SAP HANA — uses embedded DD08L-like metadata)
    python ddic_auto_populate.py --mode seed

    # HANA MODE (connects to real SAP HANA)
    python ddic_auto_populate.py --mode hana --host <HANA_HOST> --port 30015 \\
        --user SYSTEM --password <pwd> --schema SAPSR3

    # DRY RUN (shows what would be generated without writing files)
    python ddic_auto_populate.py --mode seed --dry-run

    # INCREMENTAL SYNC (writes to init_schema.cql + regenerates graph_store.py method)
    python ddic_auto_populate.py --mode hana --sync

Environment variables (alternative to CLI flags):
    HANA_MODE       = hana | seed  (default: seed)
    HANA_HOST       = SAP HANA host
    HANA_PORT       = 30015
    HANA_USER       = schema user
    HANA_PASSWORD   = password
    HANA_SCHEMA     = schema name (e.g. SAPSR3, SAPECC)
    HANA_USE_SSL    = false

Output files:
    docker/memgraph/init_schema.cql    — full Memgraph schema with MERGE statements
    backend/app/core/ddic_metadata.yaml  — structured DD08L data (nodes + edges)
    backend/app/core/graph_store_ddic.py — generated _populate_graph_from_ddic() method

What it does:
    1. Reads FK relationships from DD08L (+ DD02L table texts, DD03L field texts)
    2. Classifies each FK as internal vs cross-module using module heuristic
    3. Detects cardinality (1:1, 1:N, N:1) from field naming conventions
    4. Generates Memgraph-compatible init_schema.cql with nodes + edges
    5. Generates Python method for NetworkX graph_store.py
    6. On --sync: overwrites the relevant sections in existing files
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ddic_auto_populate")

# ─── Paths ────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent.resolve()
BACKEND_DIR = SCRIPT_DIR          # already points to .../backend/
DOCKER_DIR = SCRIPT_DIR / "docker"
SCHEMA_CQL_PATH = DOCKER_DIR / "memgraph" / "init_schema.cql"
DDIC_YAML_PATH = BACKEND_DIR / "app" / "core" / "ddic_metadata.yaml"
GRAPH_STORE_PATH = BACKEND_DIR / "app" / "core" / "graph_store.py"
DDIC_METHOD_PATH = BACKEND_DIR / "app" / "core" / "graph_store_ddic.py"

# ─── SAP Module → Domain mapping ─────────────────────────────────────────────
MODULE_MAP: Dict[str, str] = {
    "MARA": "MM", "MARC": "MM", "MARD": "MM", "MBEW": "MM", "MAKT": "MM",
    "MLGN": "MM", "MLGT": "MM", "MCHA": "MM", "MCH1": "MM", "MSKA": "MM",
    "MSLB": "MM", "MKOL": "MM", "MVKE": "MM", "MARM": "MM", "MARV": "MM",
    "MSSL": "MM", "MSSL": "MM", "QALS": "QM", "QAVE": "QM", "QAMV": "QM",
    "MAPL": "QM", "PLMK": "QM", "PLPO": "QM", "QMFE": "QM",
    "LFA1": "BP", "LFB1": "FI", "LFBK": "BP", "LFC1": "FI", "LFASS": "MM",
    "LFbw": "MM", "EINA": "MM-PUR", "EINE": "MM-PUR", "EORD": "MM-PUR",
    "EKKO": "MM-PUR", "EKPO": "MM-PUR", "EKKN": "MM-PUR", "EKES": "MM-PUR",
    "EKBE": "MM-PUR", "EBAN": "MM-PUR",
    "KNA1": "SD", "KNB1": "FI", "KNVK": "SD", "KNVV": "SD", "KNBK": "SD",
    "KONV": "SD", "A003": "SD",
    "VBAK": "SD", "VBAP": "SD", "VBEP": "SD", "VBFA": "SD",
    "LIKP": "SD", "LIPS": "SD", "VBRK": "SD", "VBRP": "SD",
    "TVCP": "SD", "TVCPL": "SD", "TVAK": "SD", "T003": "SD",
    "BKPF": "FI", "BSEG": "FI", "BSIK": "FI", "BSAK": "FI",
    "BSID": "FI", "BSAD": "FI", "BSAS": "FI", "SKA1": "FI",
    "SKB1": "FI", "T001": "FI", "T001K": "FI", "T001L": "MM",
    "T001W": "MM", "T024": "MM-PUR", "T024E": "MM-PUR",
    "CSKS": "CO", "CSSL": "CO", "COSP": "CO", "COSS": "CO",
    "COEP": "CO", "COVP": "CO", "PCFC": "CO",
    "PRPS": "PS", "PROJ": "PS", "AFVC": "PS", "AFVV": "PS",
    "ANLA": "FI", "ANLC": "FI", "ANEP": "FI", "ANEA": "FI",
    "LQUA": "WM", "LAGP": "WM", "LDCP": "WM", "LEU4": "WM",
    "LTBP": "WM", "LTAK": "WM",
    "VTTK": "TM", "VTLP": "TM", "VTFA": "TM",
    "BUT000": "BP", "BUT020": "BP", "BUT050": "BP",
    "ADRC": "BP", "ADR6": "BP",
    "ASMD": "CS", "IHPA": "CS", "DRAD": "CS",
    "IHK6": "PM", "EQUI": "PM", "IFLOT": "PM", "ILOA": "PM",
    "PA0001": "HR", "PA0002": "HR", "PA0008": "HR", "PA0021": "HR",
    "J_1BBRANCH": "TAX", "J_1IG_HSN_SAC": "TAX",
    "AFKO": "PS",   # Network Header (for Orders/Networks)
    "IFLO": "PM",   # Functional Location Master
    "J_1BTBCD": "TAX",  # India: Branch Codes for GST
    "PLKO": "QM",   # Task List Header (QM/PP)
    "QMEL": "QM",   # Quality Notification
    "T001O": "LO-VC",  # Object Types for Classification
    "TKA01": "CO",  # Controlling Areas
    "TOA01": "CS",  # Document Type Definitions (GOS)
    "TPAR": "BP",   # Business Partner Relationship Types
    "TVRO": "TM",   # Transportation Route Definition
    "USR01": "HR",  # User Master (Central User Administration)
    "VIQMEL": "QM", # QM Notification (PM)
    "VIMONI": "RE", "VIBDT": "RE",
    "/SAPSLL/POD": "GTS", "/SAPSLL/PNTPR": "GTS",
    "OIB_A04": "IS-OIL", "OIG_V": "IS-OIL", "T8JV": "IS-OIL",
    "EVBS": "IS-UTILITY", "EANL": "IS-UTILITY", "EGERR": "IS-UTILITY",
    "WRS1": "IS-RETAIL", "SETY": "IS-RETAIL",
    "NPAT": "IS-HEALTH", "NBEW": "IS-HEALTH", "NPNZ": "IS-HEALTH",
    "CABN": "LO-VC", "KLAH": "LO-VC", "CUOBJ": "LO-VC", "INOB": "LO-VC",
}

# ─── Field → cardinality heuristic ───────────────────────────────────────────
# Fields ending with these suffixes are likely key/organizational fields
# whose presence tells us about the "many" side of the relationship.
CARDINALITY_KEY_FIELDS = {
    "MANDT": "1:N",   # Client — always N (many company codes per client)
    "MATNR": "1:N",   # Material number — many plants per material
    "WERKS": "1:N",   # Plant — many storage locations per plant
    "LGORT": "1:N",   # Storage location
    "LIFNR": "1:N",   # Vendor number
    "KUNNR": "1:N",   # Customer number
    "BUKRS": "1:N",   # Company code
    "EKORG": "1:N",   # Purchasing org
    "VKORG": "1:N",   # Sales org
    "VTWEG": "1:N",   # Distribution channel
    "SPART": "1:N",   # Division
    "KOKRS": "1:N",   # Controlling area
    "KOSTL": "1:N",   # Cost center
    "PSPNR": "1:N",   # WBS element
    "BELNR": "1:N",   # Accounting document number
    "EBELN": "1:N",   # Purchasing document
    "EBELP": "1:1",   # PO item — composite key with EBELN
    "VBELN": "1:N",   # Sales document
    "POSNR": "1:1",   # Item number — composite
    "ETENR": "1:1",   # Schedule line — composite
    "BUZEI": "1:1",   # Line item — composite
    "GJAHR": "1:1",   # Fiscal year — composite key
    "PERBL": "1:1",   # Period — composite
    "ADDRNUMBER": "1:N",  # Address number
    "PERNR": "1:N",   # Personnel number
}

# ─── Cross-module bridge tables (multi-domain hub tables) ────────────────────
BRIDGE_TABLES: set = {
    "MARA",  # Material — used by MM, SD, QM, WM, PS
    "LFA1",  # Vendor — used by MM-PUR, FI, SD
    "KNA1",  # Customer — used by SD, FI
    "BKPF",  # Accounting doc header — FI + SD + MM
    "BSEG",  # Accounting line items — FI + MM-PUR + SD
    "T001",  # Company code — FI + MM + SD
    "T001W",  # Plant — MM + SD + WM + TM
    "T024",  # Purchasing org — MM-PUR + SD
    "EKKO",  # PO header — MM + FI
    "EINA",  # Info record — MM-PUR
    "EORD",  # Source list — MM-PUR
    "VBAK",  # Sales order — SD + MM
    "ADRC",  # Address — BP (universal)
    "BUT000", # Business partner — BP (universal)
    "PRPS",  # WBS element — PS + CO
    "QALS",  # Inspection lot — QM + MM
    "LQUA",  # WM Quant — WM + MM
    "EQUI",  # Equipment — PM + MM
}


# ─── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class DDICTable:
    tabname: str           # Table name e.g. "MARA"
    ddtext: str           # Description e.g. "General Material Data"
    tabclass: str         # TRANSP, VIEW, APPEND, STRUCTURE
    primary_key: List[str] = field(default_factory=list)
    domain: str = ""
    module: str = ""
    bridge: bool = False


@dataclass
class ForeignKey:
    tabname: str          # Child/source table
    fieldname: str        # FK field in child
    reftable: str         # Parent/target table
    refField: str         # Key field in parent
    cardinality: str       # "1:1" | "1:N" | "N:1" | "?"
    compType: str          # E=table, S=structure, D=data element
    frkType: str           # R=enforced, N=no enforcement
    bridge_type: str       # "internal" | "cross_module"
    condition: str         # Human-readable join condition


# ─── DD08L Seed Data ───────────────────────────────────────────────────────────
# Realistic subset of DD08L FK relationships covering the current 59-table graph.
# Derived from standard SAP DDIC structure. Replace with real HANA query in production.

SEED_DD08L: List[Dict] = [
    # ── Material Master (MM) ──────────────────────────────────────────────
    {"TABNAME":"MARA","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MARC","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MARD","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MBEW","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MAKT","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MARM","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MVKE","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MSKA","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MSLB","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MKOL","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MCH1","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MCHA","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MLGN","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MLGT","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MAPL","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"QALS","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LQUA","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MSSL","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},

    # ── Plant ──────────────────────────────────────────────────────────────
    {"TABNAME":"MARC","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MARD","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MBEW","FIELDNAME":"BWKEY","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MLGN","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MLGT","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MSKA","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MSLB","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MKOL","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LQUA","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LAGP","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LDCP","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MAPL","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"QALS","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EORD","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EQUI","FIELDNAME":"TPLNR","REFTABLE":"IHK6","REFFIELD":"TPLNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"LEU4","FIELDNAME":"TPLNR","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"N"},

    # ── Storage Location ────────────────────────────────────────────────────
    {"TABNAME":"MARD","FIELDNAME":"LGORT","REFTABLE":"T001L","REFFIELD":"LGORT","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MLGN","FIELDNAME":"LGORT","REFTABLE":"T001L","REFFIELD":"LGORT","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MLGT","FIELDNAME":"LGORT","REFTABLE":"T001L","REFFIELD":"LGORT","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MSKA","FIELDNAME":"LGORT","REFTABLE":"T001L","REFFIELD":"LGORT","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MSLB","FIELDNAME":"LGORT","REFTABLE":"T001L","REFFIELD":"LGORT","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MKOL","FIELDNAME":"LGORT","REFTABLE":"T001L","REFFIELD":"LGORT","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LQUA","FIELDNAME":"LGORT","REFTABLE":"T001L","REFFIELD":"LGORT","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LAGP","FIELDNAME":"LGTYP","REFTABLE":"LAGP","REFFIELD":"LGTYP","COMPTYPE":"E","FRKTYPE":"R"},  # Storage type
    {"TABNAME":"LDCP","FIELDNAME":"LGTYP","REFTABLE":"LAGP","REFFIELD":"LGTYP","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LDCP","FIELDNAME":"LGPLA","REFTABLE":"LDCP","REFFIELD":"LGPLA","COMPTYPE":"E","FRKTYPE":"N"},

    # ── Batch ───────────────────────────────────────────────────────────────
    {"TABNAME":"MCH1","FIELDNAME":"CHARG","REFTABLE":"MCHA","REFFIELD":"CHARG","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"QALS","FIELDNAME":"CHARG","REFTABLE":"MCHA","REFFIELD":"CHARG","COMPTYPE":"E","FRKTYPE":"N"},

    # ── Company Code ───────────────────────────────────────────────────────
    {"TABNAME":"LFB1","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSIK","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAK","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSID","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAD","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAS","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BKPF","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSEG","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"SKB1","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"ANLA","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"ANLC","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"KNB1","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKKO","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"T001K","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},

    # ── Vendor Master ───────────────────────────────────────────────────────
    {"TABNAME":"LFB1","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LFBK","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LFC1","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LFASS","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EINA","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EORD","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKKO","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKPO","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKES","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"EKBE","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EBAN","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSIK","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAK","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MSLB","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LFA1","FIELDNAME":"ADRNR","REFTABLE":"ADRC","REFFIELD":"ADDRNUMBER","COMPTYPE":"E","FRKTYPE":"N"},

    # ── Customer Master ──────────────────────────────────────────────────────
    {"TABNAME":"KNB1","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"KNVK","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"KNVV","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"KNBK","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"BSID","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAD","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"VBAK","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LIKP","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"VBRK","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MSKA","FIELDNAME":"KUNNU","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"KNA1","FIELDNAME":"ADRNR","REFTABLE":"ADRC","REFFIELD":"ADDRNUMBER","COMPTYPE":"E","FRKTYPE":"N"},

    # ── Purchasing Info Record ───────────────────────────────────────────────
    {"TABNAME":"EINE","FIELDNAME":"INFNR","REFTABLE":"EINA","REFFIELD":"INFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EORD","FIELDNAME":"INFNR","REFTABLE":"EINA","REFFIELD":"INFNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"EINA","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EORD","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EINE","FIELDNAME":"EKORG","REFTABLE":"T024","REFFIELD":"EKORG","COMPTYPE":"E","FRKTYPE":"R"},

    # ── Purchase Orders ─────────────────────────────────────────────────────
    {"TABNAME":"EKPO","FIELDNAME":"EBELN","REFTABLE":"EKKO","REFFIELD":"EBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKKN","FIELDNAME":"EBELN","REFTABLE":"EKKO","REFFIELD":"EBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKES","FIELDNAME":"EBELN","REFTABLE":"EKKO","REFFIELD":"EBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKBE","FIELDNAME":"EBELN","REFTABLE":"EKKO","REFFIELD":"EBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKPO","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKPO","FIELDNAME":"WERKS","REFTABLE":"T001W","REFFIELD":"WERKS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKPO","FIELDNAME":"EKORG","REFTABLE":"T024","REFFIELD":"EKORG","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EKKO","FIELDNAME":"ERNAM","REFTABLE":"USR01","REFFIELD":"BNAME","COMPTYPE":"E","FRKTYPE":"N"},

    # ── Sales Documents ─────────────────────────────────────────────────────
    {"TABNAME":"VBAP","FIELDNAME":"VBELN","REFTABLE":"VBAK","REFFIELD":"VBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"VBEP","FIELDNAME":"VBELN","REFTABLE":"VBAK","REFFIELD":"VBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"VBFA","FIELDNAME":"VBELV","REFTABLE":"VBAK","REFFIELD":"VBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LIKP","FIELDNAME":"VBELN","REFTABLE":"VBAK","REFFIELD":"VBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"VBAP","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"VBEP","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"LIPS","FIELDNAME":"VBELN","REFTABLE":"LIKP","REFFIELD":"VBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LIPS","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"VBRP","FIELDNAME":"VBELN","REFTABLE":"VBRK","REFFIELD":"VBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"VBRP","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"VBFA","FIELDNAME":"VBELN","REFTABLE":"VBAK","REFFIELD":"VBELN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"KONV","FIELDNAME":"KNUMV","REFTABLE":"VBAK","REFFIELD":"KNUMV","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"A003","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"R"},

    # ── Accounting Documents ────────────────────────────────────────────────
    {"TABNAME":"BSEG","FIELDNAME":"BELNR","REFTABLE":"BKPF","REFFIELD":"BELNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSEG","FIELDNAME":"GJAHR","REFTABLE":"BKPF","REFFIELD":"GJAHR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSIK","FIELDNAME":"BELNR","REFTABLE":"BKPF","REFFIELD":"BELNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAK","FIELDNAME":"BELNR","REFTABLE":"BKPF","REFFIELD":"BELNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSID","FIELDNAME":"BELNR","REFTABLE":"BKPF","REFFIELD":"BELNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAD","FIELDNAME":"BELNR","REFTABLE":"BKPF","REFFIELD":"BELNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAS","FIELDNAME":"BELNR","REFTABLE":"BKPF","REFFIELD":"BELNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSEG","FIELDNAME":"HKONT","REFTABLE":"SKA1","REFFIELD":"SAKNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"SKB1","FIELDNAME":"SAKNR","REFTABLE":"SKA1","REFFIELD":"SAKNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSEG","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"BSEG","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"BSIK","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAK","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSID","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BSAD","FIELDNAME":"KUNNR","REFTABLE":"KNA1","REFFIELD":"KUNNR","COMPTYPE":"E","FRKTYPE":"R"},

    # ── QM ──────────────────────────────────────────────────────────────────
    {"TABNAME":"QAVE","FIELDNAME":"QALS","REFTABLE":"QALS","REFFIELD":"QALS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"QAMV","FIELDNAME":"QALS","REFTABLE":"QALS","REFFIELD":"QALS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"MAPL","FIELDNAME":"PLNTY","REFTABLE":"PLKO","REFFIELD":"PLNTY","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"PLMK","FIELDNAME":"PLNNR","REFTABLE":"PLKO","REFFIELD":"PLNNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"PLPO","FIELDNAME":"PLNNR","REFTABLE":"PLKO","REFFIELD":"PLNNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"QMFE","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"QALS","FIELDNAME":"LIFNR","REFTABLE":"LFA1","REFFIELD":"LIFNR","COMPTYPE":"E","FRKTYPE":"N"},

    # ── PS / CO ─────────────────────────────────────────────────────────────
    {"TABNAME":"AFVC","FIELDNAME":"NPLNR","REFTABLE":"AFKO","REFFIELD":"NPLNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"AFVV","FIELDNAME":"NPLNR","REFTABLE":"AFKO","REFFIELD":"NPLNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"AFVV","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"PRPS","FIELDNAME":"PSPHI","REFTABLE":"PROJ","REFFIELD":"PSPNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"COSP","FIELDNAME":"OBJNR","REFTABLE":"PRPS","REFFIELD":"OBJNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"COSS","FIELDNAME":"OBJNR","REFTABLE":"PRPS","REFFIELD":"OBJNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"COSP","FIELDNAME":"KOSTL","REFTABLE":"CSKS","REFFIELD":"KOSTL","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"COSS","FIELDNAME":"KOSTL","REFTABLE":"CSKS","REFFIELD":"KOSTL","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"CSKS","FIELDNAME":"KOKRS","REFTABLE":"TKA01","REFFIELD":"KOKRS","COMPTYPE":"E","FRKTYPE":"R"},

    # ── WM ──────────────────────────────────────────────────────────────────
    {"TABNAME":"LEU4","FIELDNAME":"TKNUM","REFTABLE":"VTTK","REFFIELD":"TKNUM","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"LTBP","FIELDNAME":"TONUM","REFTABLE":"LEU4","REFFIELD":"TONUM","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"LTAK","FIELDNAME":"TONUM","REFTABLE":"LEU4","REFFIELD":"TONUM","COMPTYPE":"E","FRKTYPE":"R"},

    # ── TM ──────────────────────────────────────────────────────────────────
    {"TABNAME":"VTLP","FIELDNAME":"TKNUM","REFTABLE":"VTTK","REFFIELD":"TKNUM","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"VTLP","FIELDNAME":"TPLNR","REFTABLE":"TVRO","REFFIELD":"TPLNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"VTFA","FIELDNAME":"TKNUM","REFTABLE":"VTTK","REFFIELD":"TKNUM","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"LIKP","FIELDNAME":"TKNUM","REFTABLE":"VTTK","REFFIELD":"TKNUM","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"VBAK","FIELDNAME":"TKNUM","REFTABLE":"VTTK","REFFIELD":"TKNUM","COMPTYPE":"E","FRKTYPE":"N"},

    # ── Business Partner ────────────────────────────────────────────────────
    {"TABNAME":"BUT020","FIELDNAME":"PARTNER","REFTABLE":"BUT000","REFFIELD":"PARTNER","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BUT020","FIELDNAME":"ADDRNUMBER","REFTABLE":"ADRC","REFFIELD":"ADDRNUMBER","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BUT050","FIELDNAME":"PARTNER","REFTABLE":"BUT000","REFFIELD":"PARTNER","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"BUT000","FIELDNAME":"ADDRNUMBER","REFTABLE":"ADRC","REFFIELD":"ADDRNUMBER","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"LFA1","FIELDNAME":"PARTNER","REFTABLE":"BUT000","REFFIELD":"PARTNER","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"KNA1","FIELDNAME":"PARTNER","REFTABLE":"BUT000","REFFIELD":"PARTNER","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"ADR6","FIELDNAME":"ADDRNUMBER","REFTABLE":"ADRC","REFFIELD":"ADDRNUMBER","COMPTYPE":"E","FRKTYPE":"N"},

    # ── CS / PM ─────────────────────────────────────────────────────────────
    {"TABNAME":"ASMD","FIELDNAME":"QMNUM","REFTABLE":"QMEL","REFFIELD":"QMNUM","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"IHPA","FIELDNAME":"OBJNR","REFTABLE":"VIQMEL","REFFIELD":"OBJNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"IHPA","FIELDNAME":"PARVW","REFTABLE":"TPAR","REFFIELD":"PARVW","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"DRAD","FIELDNAME":"DOKOB","REFTABLE":"TOA01","REFFIELD":"DOKOB","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"IHK6","FIELDNAME":"EQUNR","REFTABLE":"EQUI","REFFIELD":"EQUNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"ILOA","FIELDNAME":"ILOAN","REFTABLE":"IFLO","REFFIELD":"ILOAN","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"ILOA","FIELDNAME":"ADRNR","REFTABLE":"ADRC","REFFIELD":"ADDRNUMBER","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"EQUI","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"IFLOT","FIELDNAME":"OBJNR","REFTABLE":"IHPA","REFFIELD":"OBJNR","COMPTYPE":"E","FRKTYPE":"N"},

    # ── HR ──────────────────────────────────────────────────────────────────
    {"TABNAME":"PA0001","FIELDNAME":"PERNR","REFTABLE":"PA0001","REFFIELD":"PERNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"PA0002","FIELDNAME":"PERNR","REFTABLE":"PA0001","REFFIELD":"PERNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"PA0008","FIELDNAME":"PERNR","REFTABLE":"PA0001","REFFIELD":"PERNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"PA0021","FIELDNAME":"PERNR","REFTABLE":"PA0001","REFFIELD":"PERNR","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"CSKS","FIELDNAME":"PERNR","REFTABLE":"PA0001","REFFIELD":"PERNR","COMPTYPE":"E","FRKTYPE":"N"},

    # ── India Tax ───────────────────────────────────────────────────────────
    {"TABNAME":"J_1BBRANCH","FIELDNAME":"BUKRS","REFTABLE":"T001","REFFIELD":"BUKRS","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"J_1BBRANCH","FIELDNAME":"BRANCH","REFTABLE":"J_1BTBCD","REFFIELD":"BRANCH","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"MARA","FIELDNAME":"MATNR","REFTABLE":"J_1IG_HSN_SAC","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"N"},

    # ── Real Estate ─────────────────────────────────────────────────────────
    {"TABNAME":"VIMONI","FIELDNAME":"VKONT","REFTABLE":"VIBDT","REFFIELD":"VKONT","COMPTYPE":"E","FRKTYPE":"N"},

    # ── GTS ──────────────────────────────────────────────────────────────────
    {"TABNAME":"/SAPSLL/POD","FIELDNAME":"PODHANDLE","REFTABLE":"/SAPSLL/POD","REFFIELD":"PODHANDLE","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"/SAPSLL/PNTPR","FIELDNAME":"PARNR","REFTABLE":"/SAPSLL/PNTPR","REFFIELD":"PARNR","COMPTYPE":"E","FRKTYPE":"R"},

    # ── IS-OIL ──────────────────────────────────────────────────────────────
    {"TABNAME":"OIB_A04","FIELDNAME":"TPLNR","REFTABLE":"IHK6","REFFIELD":"TPLNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"OIG_V","FIELDNAME":"OIBNR","REFTABLE":"OIB_A04","REFFIELD":"OIBNR","COMPTYPE":"E","FRKTYPE":"R"},

    # ── IS-Utilities ────────────────────────────────────────────────────────
    {"TABNAME":"EVBS","FIELDNAME":"GERNR","REFTABLE":"EANL","REFFIELD":"ANLAGE","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"EGERR","FIELDNAME":"ANLAGE","REFTABLE":"EANL","REFFIELD":"ANLAGE","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"EANL","FIELDNAME":"EQUNR","REFTABLE":"EQUI","REFFIELD":"EQUNR","COMPTYPE":"E","FRKTYPE":"N"},

    # ── Variant Configuration ───────────────────────────────────────────────
    {"TABNAME":"CUOBJ","FIELDNAME":"MATNR","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"CUOBJ","FIELDNAME":"CLINT","REFTABLE":"KLAH","REFFIELD":"CLINT","COMPTYPE":"E","FRKTYPE":"R"},
    {"TABNAME":"INOB","FIELDNAME":"OBJEK","REFTABLE":"MARA","REFFIELD":"MATNR","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"INOB","FIELDNAME":"OBJEK","REFTABLE":"KLAH","REFFIELD":"CLINT","COMPTYPE":"E","FRKTYPE":"N"},
    {"TABNAME":"INOB","FIELDNAME":"OBTYP","REFTABLE":"T001O","REFFIELD":"OBTYP","COMPTYPE":"E","FRKTYPE":"N"},
]

# ─── DD02L Seed Data (table descriptions) ─────────────────────────────────────
SEED_DD02L: Dict[str, Dict] = {
    "MARA": {"DDTEXT": "General Material Data", "TABCLASS": "TRANSP"},
    "MARC": {"DDTEXT": "Plant Data for Material", "TABCLASS": "TRANSP"},
    "MARD": {"DDTEXT": "Storage Location Data for Material", "TABCLASS": "TRANSP"},
    "MBEW": {"DDTEXT": "Material Valuation", "TABCLASS": "TRANSP"},
    "MAKT": {"DDTEXT": "Material Descriptions", "TABCLASS": "TRANSP"},
    "MLGN": {"DDTEXT": "Material Data for Each Storage Location (WM)", "TABCLASS": "TRANSP"},
    "MLGT": {"DDTEXT": "Material Data for Each Storage Type (WM)", "TABCLASS": "TRANSP"},
    "MCHA": {"DDTEXT": "Batch Master Record", "TABCLASS": "TRANSP"},
    "MCH1": {"DDTEXT": "Batch Stock (Quantities)", "TABCLASS": "TRANSP"},
    "MSKA": {"DDTEXT": "Sales Order Stock", "TABCLASS": "TRANSP"},
    "MSLB": {"DDTEXT": "Special Stock (Vendor-owned)", "TABCLASS": "TRANSP"},
    "MKOL": {"DDTEXT": "Special Stock (Project-owned)", "TABCLASS": "TRANSP"},
    "MVKE": {"DDTEXT": "Sales Data for Material", "TABCLASS": "TRANSP"},
    "MARM": {"DDTEXT": "Unit of Measure Data for Material", "TABCLASS": "TRANSP"},
    "MSSL": {"DDTEXT": "Special Stock (Stock-funded)", "TABCLASS": "TRANSP"},
    "LFA1": {"DDTEXT": "Vendor Master (General Section)", "TABCLASS": "TRANSP"},
    "LFB1": {"DDTEXT": "Vendor Master (Company Code Data)", "TABCLASS": "TRANSP"},
    "LFBK": {"DDTEXT": "Vendor Master (Bank Details)", "TABCLASS": "TRANSP"},
    "LFC1": {"DDTEXT": "Vendor Master (One-Time Vendor)", "TABCLASS": "TRANSP"},
    "LFASS": {"DDTEXT": "Vendor Evaluation Grades", "TABCLASS": "TRANSP"},
    "LFbw": {"DDTEXT": "Vendor Evaluation Grades (Material/Plant)", "TABCLASS": "TRANSP"},
    "EINA": {"DDTEXT": "Purchasing Info Record: General Data", "TABCLASS": "TRANSP"},
    "EINE": {"DDTEXT": "Purchasing Info Record: Purchasing Organization Data", "TABCLASS": "TRANSP"},
    "EORD": {"DDTEXT": "Source List (Vendor-Material-Plant)", "TABCLASS": "TRANSP"},
    "EKKO": {"DDTEXT": "Purchasing Document Header", "TABCLASS": "TRANSP"},
    "EKPO": {"DDTEXT": "Purchasing Document Item", "TABCLASS": "TRANSP"},
    "EKKN": {"DDTEXT": "Account Assignment (Purchasing Document)", "TABCLASS": "TRANSP"},
    "EKES": {"DDTEXT": "Vendor Confirmations (Scheduling Agreements)", "TABCLASS": "TRANSP"},
    "EKBE": {"DDTEXT": "Purchasing Document History", "TABCLASS": "TRANSP"},
    "EBAN": {"DDTEXT": "Purchase Requisition", "TABCLASS": "TRANSP"},
    "KNA1": {"DDTEXT": "Customer Master (General Data)", "TABCLASS": "TRANSP"},
    "KNB1": {"DDTEXT": "Customer Master (Company Code Data)", "TABCLASS": "TRANSP"},
    "KNVK": {"DDTEXT": "Customer Master Contact Relationships", "TABCLASS": "TRANSP"},
    "KNVV": {"DDTEXT": "Customer Master (Sales Area Data)", "TABCLASS": "TRANSP"},
    "KNBK": {"DDTEXT": "Customer Master (Bank Details)", "TABCLASS": "TRANSP"},
    "KONV": {"DDTEXT": "Pricing Conditions (Communication)", "TABCLASS": "TRANSP"},
    "A003": {"DDTEXT": "Condition Records: Tax (Customer-Material-Country)", "TABCLASS": "TRANSP"},
    "VBAK": {"DDTEXT": "Sales Document Header", "TABCLASS": "TRANSP"},
    "VBAP": {"DDTEXT": "Sales Document Item", "TABCLASS": "TRANSP"},
    "VBEP": {"DDTEXT": "Sales Document: Schedule Line", "TABCLASS": "TRANSP"},
    "VBFA": {"DDTEXT": "Sales Document Flow (Document Chain)", "TABCLASS": "TRANSP"},
    "LIKP": {"DDTEXT": "Delivery Document Header", "TABCLASS": "TRANSP"},
    "LIPS": {"DDTEXT": "Delivery Document Item", "TABCLASS": "TRANSP"},
    "VBRK": {"DDTEXT": "Billing Document Header", "TABCLASS": "TRANSP"},
    "VBRP": {"DDTEXT": "Billing Document Item", "TABCLASS": "TRANSP"},
    "TVCP": {"DDTEXT": "Pricing Procedure (Header)", "TABCLASS": "TRANSP"},
    "TVCPL": {"DDTEXT": "Pricing Procedure (Line)", "TABCLASS": "TRANSP"},
    "TVAK": {"DDTEXT": "Sales Document Types (Header)", "TABCLASS": "TRANSP"},
    "T003": {"DDTEXT": "Sales Document Types", "TABCLASS": "TRANSP"},
    "BKPF": {"DDTEXT": "Accounting Document Header", "TABCLASS": "TRANSP"},
    "BSEG": {"DDTEXT": "Accounting Document Segment (Line Items)", "TABCLASS": "TRANSP"},
    "BSIK": {"DDTEXT": "Accounting: Secondary Index for Vendors (Open Items)", "TABCLASS": "TRANSP"},
    "BSAK": {"DDTEXT": "Accounting: Secondary Index for Vendors (Cleared Items)", "TABCLASS": "TRANSP"},
    "BSID": {"DDTEXT": "Accounting: Secondary Index for Customers (Open Items)", "TABCLASS": "TRANSP"},
    "BSAD": {"DDTEXT": "Accounting: Secondary Index for Customers (Cleared Items)", "TABCLASS": "TRANSP"},
    "BSAS": {"DDTEXT": "Accounting: Secondary Index for G/L Accounts (Cleared Items)", "TABCLASS": "TRANSP"},
    "SKA1": {"DDTEXT": "G/L Account Master (Chart of Accounts)", "TABCLASS": "TRANSP"},
    "SKB1": {"DDTEXT": "G/L Account Master (Company Code)", "TABCLASS": "TRANSP"},
    "T001": {"DDTEXT": "Company Codes", "TABCLASS": "TRANSP"},
    "T001K": {"DDTEXT": "Valuation Area (Company Code or Plant Level)", "TABCLASS": "TRANSP"},
    "T001L": {"DDTEXT": "Storage Locations", "TABCLASS": "TRANSP"},
    "T001W": {"DDTEXT": "Plants", "TABCLASS": "TRANSP"},
    "T024": {"DDTEXT": "Purchasing Organizations", "TABCLASS": "TRANSP"},
    "T024E": {"DDTEXT": "Purchasing Groups", "TABCLASS": "TRANSP"},
    "CSKS": {"DDTEXT": "Cost Center Master", "TABCLASS": "TRANSP"},
    "CSSL": {"DDTEXT": "Cost Center Group / Cost Element", "TABCLASS": "TRANSP"},
    "COSP": {"DDTEXT": "CO Object: Cost Totals (Actual)", "TABCLASS": "TRANSP"},
    "COSS": {"DDTEXT": "CO Object: Cost Totals (Plan)", "TABCLASS": "TRANSP"},
    "COEP": {"DDTEXT": "CO Object: Cost Line Items (Actual)", "TABCLASS": "TRANSP"},
    "COVP": {"DDTEXT": "CO Object: Cost Line Items (Plan)", "TABCLASS": "TRANSP"},
    "PCFC": {"DDTEXT": "Profit Center Planning", "TABCLASS": "TRANSP"},
    "PROJ": {"DDTEXT": "Project Definition", "TABCLASS": "TRANSP"},
    "PRPS": {"DDTEXT": "Work Breakdown Structure (WBS) Element", "TABCLASS": "TRANSP"},
    "AFVC": {"DDTEXT": "Activity at Work Center (Network Node)", "TABCLASS": "TRANSP"},
    "AFVV": {"DDTEXT": "Operation/Cost Data for Activities", "TABCLASS": "TRANSP"},
    "AFKO": {"DDTEXT": "Network Header (for Orders/Networks)", "TABCLASS": "TRANSP"},
    "ANLA": {"DDTEXT": "Asset Master Record (Investment Accounting)", "TABCLASS": "TRANSP"},
    "ANLC": {"DDTEXT": "Asset Master: Line Items (Company Code)", "TABCLASS": "TRANSP"},
    "ANEP": {"DDTEXT": "Asset Accounting Document Line Items", "TABCLASS": "TRANSP"},
    "ANEA": {"DDTEXT": "Asset Accounting Document Amounts", "TABCLASS": "TRANSP"},
    "LQUA": {"DDTEXT": "Quant (WM) — Physical Stock Record", "TABCLASS": "TRANSP"},
    "LAGP": {"DDTEXT": "Storage Type (Warehouse Management)", "TABCLASS": "TRANSP"},
    "LDCP": {"DDTEXT": "Storage Bin (Warehouse Management)", "TABCLASS": "TRANSP"},
    "LEU4": {"DDTEXT": "Transfer Order Header", "TABCLASS": "TRANSP"},
    "LTBP": {"DDTEXT": "Transfer Order Item (Batch-managed)", "TABCLASS": "TRANSP"},
    "LTAK": {"DDTEXT": "Transfer Order Header (All Items)", "TABCLASS": "TRANSP"},
    "VTTK": {"DDTEXT": "Transportation Order / Shipment Header", "TABCLASS": "TRANSP"},
    "VTLP": {"DDTEXT": "Transportation Order / Shipment Leg", "TABCLASS": "TRANSP"},
    "VTFA": {"DDTEXT": "Transportation Order / Shipment Stage", "TABCLASS": "TRANSP"},
    "TVRO": {"DDTEXT": "Transportation Route Definition", "TABCLASS": "TRANSP"},
    "BUT000": {"DDTEXT": "Business Partner: General Data I (Central BP Master)", "TABCLASS": "TRANSP"},
    "BUT020": {"DDTEXT": "Business Partner: Address Management", "TABCLASS": "TRANSP"},
    "BUT050": {"DDTEXT": "Business Partner: Customer/Vendor Link (Role Relationships)", "TABCLASS": "TRANSP"},
    "ADRC": {"DDTEXT": "Business Address Services (Central Address Mgmt)", "TABCLASS": "TRANSP"},
    "ADR6": {"DDTEXT": "Business Partner: Email Addresses", "TABCLASS": "TRANSP"},
    "ASMD": {"DDTEXT": "Service Order / Service Notification", "TABCLASS": "TRANSP"},
    "IHPA": {"DDTEXT": "Business Partner Relationships (for Service)", "TABCLASS": "TRANSP"},
    "DRAD": {"DDTEXT": "Document-Item Assignment (GOS attachments)", "TABCLASS": "TRANSP"},
    "IHK6": {"DDTEXT": "Equipment Master Record (Functional Location/Tech Obj)", "TABCLASS": "TRANSP"},
    "EQUI": {"DDTEXT": "Equipment Master Data", "TABCLASS": "TRANSP"},
    "IFLOT": {"DDTEXT": "Fleet / Technical Object Master", "TABCLASS": "TRANSP"},
    "ILOA": {"DDTEXT": "Technical Object Location / Address Assignment", "TABCLASS": "TRANSP"},
    "IFLO": {"DDTEXT": "Functional Location Master", "TABCLASS": "TRANSP"},
    "QMEL": {"DDTEXT": "Quality Notification", "TABCLASS": "TRANSP"},
    "VIQMEL": {"DDTEXT": "QM Notification (PM)", "TABCLASS": "TRANSP"},
    "TPAR": {"DDTEXT": "Business Partner Relationship Types", "TABCLASS": "TRANSP"},
    "TOA01": {"DDTEXT": "Document Type Definitions (GOS)", "TABCLASS": "TRANSP"},
    "T001O": {"DDTEXT": "Object Types for Classification", "TABCLASS": "TRANSP"},
    "PA0001": {"DDTEXT": "HR Master Record: Organization Assignment", "TABCLASS": "TRANSP"},
    "PA0002": {"DDTEXT": "HR Master Record: Personal Data", "TABCLASS": "TRANSP"},
    "PA0008": {"DDTEXT": "HR Master Record: Pay / Wage Type", "TABCLASS": "TRANSP"},
    "PA0021": {"DDTEXT": "HR Master Record: Family Member/Dependents", "TABCLASS": "TRANSP"},
    "USR01": {"DDTEXT": "User Master (Central User Administration)", "TABCLASS": "TRANSP"},
    "TKA01": {"DDTEXT": "Controlling Areas", "TABCLASS": "TRANSP"},
    "PLKO": {"DDTEXT": "Task List Header (QM/PP)", "TABCLASS": "TRANSP"},
    "J_1BBRANCH": {"DDTEXT": "India: Branch/Plant Registration for GST", "TABCLASS": "TRANSP"},
    "J_1BTBCD": {"DDTEXT": "India: Branch Codes for GST", "TABCLASS": "TRANSP"},
    "J_1IG_HSN_SAC": {"DDTEXT": "India: HSN Codes for Materials / SAC Codes for Services", "TABCLASS": "TRANSP"},
    "VIMONI": {"DDTEXT": "Real Estate Contract / Rent Index", "TABCLASS": "TRANSP"},
    "VIBDT": {"DDTEXT": "Real Estate Business Partner Link", "TABCLASS": "TRANSP"},
    "/SAPSLL/POD": {"DDTEXT": "GTS: Proof of Delivery / Export Control", "TABCLASS": "TRANSP"},
    "/SAPSLL/PNTPR": {"DDTEXT": "GTS: Partner Master Data (Trade Compliance)", "TABCLASS": "TRANSP"},
    "OIB_A04": {"DDTEXT": "Oil & Gas: Tank Farm / Storage Location Data", "TABCLASS": "TRANSP"},
    "OIG_V": {"DDTEXT": "Oil & Gas: Volume / Measurement Data", "TABCLASS": "TRANSP"},
    "T8JV": {"DDTEXT": "Oil & Gas: Joint Venture Partner Codes", "TABCLASS": "TRANSP"},
    "EVBS": {"DDTEXT": "Utilities: Device Installation (Field Service)", "TABCLASS": "TRANSP"},
    "EANL": {"DDTEXT": "Utilities: Equipment Master (Installation Point)", "TABCLASS": "TRANSP"},
    "EGERR": {"DDTEXT": "Utilities: Device Register / Error Register", "TABCLASS": "TRANSP"},
    "WRS1": {"DDTEXT": "Retail: Replenishment Proposal / Buying Line", "TABCLASS": "TRANSP"},
    "SETY": {"DDTEXT": "Retail: Assortment Module / Range Planning", "TABCLASS": "TRANSP"},
    "NPAT": {"DDTEXT": "Healthcare: Patient Master / Coverage", "TABCLASS": "TRANSP"},
    "NBEW": {"DDTEXT": "Healthcare: Care Beneficiary (Insurance/Billing)", "TABCLASS": "TRANSP"},
    "NPNZ": {"DDTEXT": "Healthcare: Care Plan / Care Activity Records", "TABCLASS": "TRANSP"},
    "CABN": {"DDTEXT": "Configuration: Characteristic (Feature) Master", "TABCLASS": "TRANSP"},
    "KLAH": {"DDTEXT": "Configuration: Class Master (Product Class)", "TABCLASS": "TRANSP"},
    "CUOBJ": {"DDTEXT": "Configuration: Configuration (Internal Object Key)", "TABCLASS": "TRANSP"},
    "INOB": {"DDTEXT": "Allocation: Material to Configuration (Long Text)", "TABCLASS": "TRANSP"},
}


# ─── Core Logic ───────────────────────────────────────────────────────────────

def get_table_module(tabname: str) -> str:
    """Heuristic: infer SAP module from table name prefix."""
    return MODULE_MAP.get(tabname, "UNKNOWN")


def get_bridge_type(tabname: str) -> bool:
    return tabname.upper() in BRIDGE_TABLES


def infer_cardinality(fk: Dict) -> str:
    """Infer cardinality from field naming conventions in the FK field."""
    fieldname = (fk.get("FIELDNAME") or "").upper()
    reffield = (fk.get("REFFIELD") or "").upper()

    # Composite key fields (usually 1:1 within the context of their parent)
    for suffix in ("P", "Pnr", "Pos", "Posnr", "Buzei", "Etenr", "Gjahr", "Perbl"):
        if fieldname.endswith(suffix):
            return "1:1"

    # Organizational key fields → 1:N
    for suffix in ("Matnr", "Lifnr", "Kunnr", "Werks", "Bukrs", "Ekorg",
                   "Vkorg", "Vtweg", "Spart", "Kokrs", "Kostl", "Pspnr",
                   "Belnr", "Ebeln", "Vbeln", "Addrnumber", "Pernr",
                   "Tonum", "Tknum", "Objnr", "Equnr", "Mandt"):
        if fieldname == suffix or fieldname.endswith(suffix):
            return "1:N"

    # Self-referential → 1:N
    if fk.get("TABNAME") == fk.get("REFTABLE"):
        return "1:N"

    return "1:N"


def build_fk_object(raw: Dict) -> ForeignKey:
    tabname = raw["TABNAME"].strip().upper()
    reftable = raw["REFTABLE"].strip().upper()
    fieldname = raw["FIELDNAME"].strip().upper()
    reffield = raw["REFFIELD"].strip().upper()

    cardinality = infer_cardinality(raw)
    bridge_type = "cross_module" if get_table_module(tabname) != get_table_module(reftable) else "internal"

    # Build condition string
    if fieldname == reffield:
        condition = f"{tabname}.{fieldname} = {reftable}.{reffield}"
    else:
        condition = f"{tabname}.{fieldname} = {reftable}.{reffield}"

    return ForeignKey(
        tabname=tabname,
        fieldname=fieldname,
        reftable=reftable,
        refField=reffield,
        cardinality=cardinality,
        compType=raw.get("COMPTYPE", "E"),
        frkType=raw.get("FRKTYPE", "N"),
        bridge_type=bridge_type,
        condition=condition,
    )


def load_from_hana(args: argparse.Namespace) -> Tuple[List[Dict], Dict[str, Dict]]:
    """Connect to SAP HANA and query DD08L, DD02L."""
    logger.info(f"Connecting to SAP HANA {args.host}:{args.port}/{args.schema}")

    try:
        import hdbcli
    except ImportError:
        logger.error(
            "hdbcli not installed. Install with: pip install hdbcli\n"
            "Then retry: python ddic_auto_populate.py --mode hana ..."
        )
        sys.exit(1)

    from hdbcli import dbapi

    conn = dbapi.connect(
        address=args.host,
        port=int(args.port),
        user=args.user,
        password=args.password,
        database=args.schema,
    )

    cursor = conn.cursor()

    # ── DD08L: FK relationships ─────────────────────────────────────────────
    logger.info("Querying DD08L (foreign key relationships)...")
    cursor.execute(
        """
        SELECT TABNAME, FIELDNAME, REFTABLE, REFFIELD, COMPTYPE, FRKTYPE
        FROM DD08L
        WHERE COMPTYPE = 'E'
          AND FRKTYPE  = 'R'
          AND TABNAME NOT LIKE '/%'
          AND TABNAME NOT LIKE '%~%'
        ORDER BY TABNAME, FIELDNAME
        """
    )
    dd08l_rows = cursor.fetchall()
    dd08l_columns = [d[0] for d in cursor.description]
    dd08l = [dict(zip(dd08l_columns, row)) for row in dd08l_rows]
    logger.info(f"  → {len(dd08l)} FK records from DD08L")

    # ── DD02L: Table descriptions ──────────────────────────────────────────
    logger.info("Querying DD02L (table metadata)...")
    cursor.execute(
        """
        SELECT TABNAME, DDTEXT, TABCLASS
        FROM DD02L
        WHERE TABCLASS IN ('TRANSP', 'VIEW')
          AND TABNAME NOT LIKE '/%'
          AND TABNAME NOT LIKE '%~%'
        ORDER BY TABNAME
        """
    )
    dd02l_rows = cursor.fetchall()
    dd02l_columns = [d[0] for d in cursor.description]
    dd02l = {row[0]: dict(zip(dd02l_columns, row)) for row in dd02l_rows}
    logger.info(f"  → {len(dd02l)} table records from DD02L")

    conn.close()
    return dd08l, dd02l


def load_seed_data() -> Tuple[List[Dict], Dict[str, Dict]]:
    return SEED_DD08L, SEED_DD02L


# ─── Generators ───────────────────────────────────────────────────────────────

def generate_init_cql(
    fks: List[ForeignKey],
    tables: Dict[str, DDICTable],
) -> str:
    """Generate Memgraph init_schema.cql from FK list and table metadata."""

    # ── Sort nodes by module for clean grouping ─────────────────────────────
    def node_sort(t: DDICTable) -> tuple:
        order = {
            "MM": 1, "MM-PUR": 2, "BP": 3, "SD": 4, "FI": 5,
            "CO": 6, "PS": 7, "QM": 8, "WM": 9, "TM": 10,
            "CS": 11, "PM": 12, "HR": 13, "TAX": 14, "RE": 15,
            "GTS": 16, "IS-OIL": 17, "IS-UTILITY": 18, "IS-RETAIL": 19,
            "IS-HEALTH": 20, "LO-VC": 21, "UNKNOWN": 99,
        }
        return (order.get(t.module, 50), t.tabname)

    sections = []

    # ── Header ─────────────────────────────────────────────────────────────
    sections.append("-- init_schema.cql")
    sections.append("-- ============================================================")
    sections.append("-- SAP Enterprise Schema Graph — AUTO-GENERATED by ddic_auto_populate.py")
    sections.append(f"-- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    sections.append("-- ============================================================")
    sections.append("-- Load via docker-compose volume mount:")
    sections.append("--   ./docker/memgraph/init_schema.cql:/docker-entrypoint-initdb.d/01-schema.cql")
    sections.append("")

    # ── 1. Indexes ──────────────────────────────────────────────────────────
    sections.append("-- ── 1. Indexes ──────────────────────────────────────────────────────")
    sections.append("CREATE INDEX ON :SAPTable(table_name);")
    sections.append("CREATE INDEX ON :SAPTable(module);")
    sections.append("CREATE INDEX ON :SAPTable(domain);")
    sections.append("CREATE INDEX ON :SAPTable(bridge);")
    sections.append("")

    # ── 2. Nodes (grouped by module) ────────────────────────────────────────
    sections.append("-- ── 2. SAP Tables (DDIC auto-populated) ─────────────────────────────")
    node_lines = []
    for table in sorted(tables.values(), key=node_sort):
        pk_str = str(table.primary_key).replace("'", '"')
        node_lines.append(
            f'MERGE (m:SAPTable {{table_name:"{table.tabname}"}}) '
            f'SET m.module="{table.module}", m.domain="{table.domain}", '
            f'm.description="{table.ddtext}", m.key_columns={pk_str}, '
            f'm.bridge={str(table.bridge).lower()};'
        )
    sections.extend(node_lines)
    sections.append("")

    # ── 3. Edges (FK relationships) ───────────────────────────────────────────
    sections.append("-- ── 3. FK Relationships (DD08L auto-populated) ─────────────────────")

    # Group by bridge_type for clean sections
    internal_fks = [f for f in fks if f.bridge_type == "internal"]
    cross_fks = [f for f in fks if f.bridge_type == "cross_module"]

    if internal_fks:
        sections.append("-- ── Internal (same module) ───────────────────────────────────────")
        for fk in sorted(internal_fks, key=lambda x: (x.tabname, x.reftable)):
            c = fk.condition.replace('"', '\\"')
            sections.append(
                f'MATCH (a:SAPTable {{table_name:"{fk.tabname}"}}), '
                f'(b:SAPTable {{table_name:"{fk.reftable}"}}) '
                f'MERGE (a)-[:FOREIGN_KEY {{condition:"{c}", '
                f'cardinality:"{fk.cardinality}", '
                f'bridge_type:"internal", '
                f'notes:"DD08L auto: {fk.tabname}.{fk.fieldname} -> {fk.reftable}.{fk.refField}"}}]->(b);'
            )

    if cross_fks:
        sections.append("-- ── Cross-module bridges ─────────────────────────────────────────")
        for fk in sorted(cross_fks, key=lambda x: (x.tabname, x.reftable)):
            c = fk.condition.replace('"', '\\"')
            sections.append(
                f'MATCH (a:SAPTable {{table_name:"{fk.tabname}"}}), '
                f'(b:SAPTable {{table_name:"{fk.reftable}"}}) '
                f'MERGE (a)-[:FOREIGN_KEY {{condition:"{c}", '
                f'cardinality:"{fk.cardinality}", '
                f'bridge_type:"cross_module", '
                f'notes:"DD08L auto: {fk.tabname}.{fk.fieldname} -> {fk.reftable}.{fk.refField}"}}]->(b);'
            )

    sections.append("")
    sections.append(f"-- === END OF AUTO-GENERATED SCHEMA — {len(tables)} tables, {len(fks)} FK edges ===")

    return "\n".join(sections)


def generate_python_method(
    fks: List[ForeignKey],
    tables: Dict[str, DDICTable],
) -> str:
    """Generate the _populate_graph_from_ddic() method for graph_store.py."""

    lines = [
        "    def _populate_graph_from_ddic(self) -> None:",
        '        """',
        "        Populates the graph from structured DD08L FK metadata.",
        "        Auto-generated by ddic_auto_populate.py — DO NOT EDIT BY HAND.",
        f"        {len(tables)} tables, {len(fks)} FK edges.",
        "        Call this instead of _populate_graph() for DDIC-driven graph build.",
        '        """',
        "",
    ]

    # ── Nodes ────────────────────────────────────────────────────────────────
    lines.append("        # ── Nodes (tables) ───────────────────────────────────────────────")
    node: DDICTable
    for node in sorted(tables.values(), key=lambda n: n.tabname):
        lines.append(
            f'        self._add_node("{node.tabname}", '
            f'"{node.module}", "{node.domain}", '
            f'"{node.ddtext}", {node.primary_key!r})'
        )

    lines.append("")

    # ── Edges ────────────────────────────────────────────────────────────────
    lines.append("        # ── FK Edges (from DD08L) ───────────────────────────────────────")

    # Deduplicate edges (same tabname+reftable pair)
    seen: set = set()
    for fk in sorted(fks, key=lambda x: (x.tabname, x.reftable)):
        key = (fk.tabname, fk.reftable)
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f'        self._add_edge("{fk.tabname}", "{fk.reftable}", '
            f'"{fk.condition}", cardinality="{fk.cardinality}", '
            f'bridge_type="{fk.bridge_type}")'
        )

    lines.append(f'        logger.info("DDIC graph populated: {len(tables)} tables, {len(seen)} FK edges")')
    lines.append("        return")

    return "\n".join(lines)


def generate_yaml_output(
    fks: List[ForeignKey],
    tables: Dict[str, DDICTable],
    mode: str,
) -> Dict:
    """Build the YAML structure for ddic_metadata.yaml."""
    return {
        "metadata": {
            "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "mode": mode,
            "source": "SAP DD08L" if mode == "hana" else "SEED (SAP-like DD08L subset)",
            "table_count": len(tables),
            "fk_edge_count": len(fks),
        },
        "tables": {
            t.tabname: {
                "module": t.module,
                "domain": t.domain,
                "description": t.ddtext,
                "primary_key": t.primary_key,
                "bridge": t.bridge,
            }
            for t in sorted(tables.values(), key=lambda x: x.tabname)
        },
        "foreign_keys": [
            {
                "tabname": fk.tabname,
                "fieldname": fk.fieldname,
                "reftable": fk.reftable,
                "refField": fk.refField,
                "cardinality": fk.cardinality,
                "bridge_type": fk.bridge_type,
                "condition": fk.condition,
            }
            for fk in sorted(fks, key=lambda x: (x.tabname, x.reftable))
        ],
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ddic_auto_populate — auto-build FK graph from SAP DD08L",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode", choices=["hana", "seed"], default=os.getenv("HANA_MODE", "seed"),
        help="hana = query real SAP HANA DD08L; seed = use embedded seed data"
    )
    parser.add_argument("--host", default=os.getenv("HANA_HOST"))
    parser.add_argument("--port", default=os.getenv("HANA_PORT", "30015"))
    parser.add_argument("--user", default=os.getenv("HANA_USER"))
    parser.add_argument("--password", default=os.getenv("HANA_PASSWORD"))
    parser.add_argument("--schema", default=os.getenv("HANA_SCHEMA", "SAPSR3"))
    parser.add_argument(
        "--sync", action="store_true",
        help="Overwrite init_schema.cql, ddic_metadata.yaml, and graph_store_ddic.py"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be generated without writing files"
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show summary statistics and exit"
    )
    return parser.parse_args()


def run():
    args = parse_args()

    # ── Load data ──────────────────────────────────────────────────────────
    t0 = time.time()
    if args.mode == "hana":
        if not args.host or not args.user or not args.password:
            logger.error(
                "--mode hana requires --host, --user, --password "
                "(or HANA_HOST, HANA_USER, HANA_PASSWORD env vars)"
            )
            sys.exit(1)
        raw_dd08l, raw_dd02l = load_from_hana(args)
    else:
        raw_dd08l, raw_dd02l = load_seed_data()
        logger.info(f"Loaded {len(raw_dd08l)} seed FK records from embedded DD08L")

    # ── Build objects ────────────────────────────────────────────────────────
    fks = []
    for raw in raw_dd08l:
        try:
            fks.append(build_fk_object(raw))
        except KeyError:
            continue

    tables: Dict[str, DDICTable] = {}
    for tabname, meta in raw_dd02l.items():
        tables[tabname] = DDICTable(
            tabname=tabname,
            ddtext=meta.get("DDTEXT", tabname),
            tabclass=meta.get("TABCLASS", "TRANSP"),
            primary_key=[],           # Would need DD03L PK query for real HANA
            domain="",
            module=get_table_module(tabname),
            bridge=get_bridge_type(tabname),
        )

    # Stats
    cross_module = sum(1 for f in fks if f.bridge_type == "cross_module")
    internal = len(fks) - cross_module
    by_module: Dict[str, int] = {}
    for t in tables.values():
        by_module.setdefault(t.module, 0)
        by_module[t.module] += 1

    logger.info(f"Built {len(tables)} tables, {len(fks)} FK edges "
                f"({internal} internal, {cross_module} cross-module) in {time.time()-t0:.1f}s")

    if args.stats:
        print(f"\n  Tables:         {len(tables)}")
        print(f"  FK Edges:      {len(fks)}")
        print(f"  Internal:      {internal}")
        print(f"  Cross-module:  {cross_module}")
        print(f"\n  By module:")
        for mod, cnt in sorted(by_module.items()):
            print(f"    {mod:12s}  {cnt:3d} tables")
        return

    # ── Generate outputs ────────────────────────────────────────────────────
    cql = generate_init_cql(fks, tables)
    py_method = generate_python_method(fks, tables)
    yaml_data = generate_yaml_output(fks, tables, args.mode)

    if args.dry_run:
        print("\n─── init_schema.cql (first 30 lines) ───")
        for line in cql.splitlines()[:30]:
            print(line)
        print(f"\n  ... [{len(cql.splitlines())} total lines]")
        print("\n─── Python method (first 20 lines) ───")
        for line in py_method.splitlines()[:20]:
            print(line)
        print(f"\n  ... [{len(py_method.splitlines())} total lines]")
        print(f"\n─── YAML metadata ───")
        print(f"  tables: {len(yaml_data['tables'])}")
        print(f"  foreign_keys: {len(yaml_data['foreign_keys'])}")
        print(f"  metadata: {yaml_data['metadata']}")
        return

    if not args.sync:
        logger.info("Use --sync to write files (dry-run mode, no files written)")
        return

    # ── Write files ─────────────────────────────────────────────────────────
    logger.info("Writing init_schema.cql ...")
    SCHEMA_CQL_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_CQL_PATH.write_text(cql, encoding="utf-8")

    logger.info("Writing ddic_metadata.yaml ...")
    DDIC_YAML_PATH.parent.mkdir(parents=True, exist_ok=True)
    DDIC_YAML_PATH.write_text(yaml.dump(yaml_data, default_flow_style=False, sort_keys=True), encoding="utf-8")

    logger.info("Writing graph_store_ddic.py ...")
    DDIC_METHOD_PATH.write_text(py_method, encoding="utf-8")

    logger.info(f"\n✅ DDIC auto-population complete:")
    logger.info(f"   {SCHEMA_CQL_PATH}   — {len(cql.splitlines())} lines")
    logger.info(f"   {DDIC_YAML_PATH}   — {len(tables)} tables, {len(fks)} FK edges")
    logger.info(f"   {DDIC_METHOD_PATH} — Python method")
    logger.info(f"\n   Next: restart Memgraph + re-run bolt_load.py to load new schema")
    logger.info(f"   Or:   from app.core.graph_store_ddic import _populate_graph_from_ddic")


if __name__ == "__main__":
    run()
