"""
DDIC Auto-Ingestion Pipeline for Know Your SAP Masters
======================================================
Extracts table metadata and foreign key relationships directly from SAP DDIC
(DD02L, DD02T, DD03L, DD08L) and loads them into Memgraph.

This allows the graph to automatically learn custom Z* and Y* tables
deployed in any specific SAP customer environment.

Usage:
    python backend/scripts/ddic_auto_ingest.py [--mock]
"""
import os
import sys
import argparse
import logging
from typing import List, Dict

# Setup Python path to import app modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.app.core.memgraph_adapter import use_memgraph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Mock Data to simulate SAP HANA SQL results (Until Phase M7 is wired)
MOCK_DD02L_TABLES = [
    {"TABNAME": "MARA", "AS4LOCAL": "A", "TABCLASS": "TRANSP", "DDTEXT": "General Material Data", "DEVCLASS": "MG"},
    {"TABNAME": "MARC", "AS4LOCAL": "A", "TABCLASS": "TRANSP", "DDTEXT": "Plant Data for Material", "DEVCLASS": "MG"},
    {"TABNAME": "LFA1", "AS4LOCAL": "A", "TABCLASS": "TRANSP", "DDTEXT": "Vendor Master (General Section)", "DEVCLASS": "FB"},
    {"TABNAME": "EKKO", "AS4LOCAL": "A", "TABCLASS": "TRANSP", "DDTEXT": "Purchasing Document Header", "DEVCLASS": "ME"},
    {"TABNAME": "Z_SUPPLIER_SCORE", "AS4LOCAL": "A", "TABCLASS": "TRANSP", "DDTEXT": "Custom Supplier ESG Scoring", "DEVCLASS": "Z_ESG"},
]

MOCK_DD03L_KEYS = [
    {"TABNAME": "MARA", "FIELDNAME": "MATNR", "KEYFLAG": "X"},
    {"TABNAME": "MARC", "FIELDNAME": "MATNR", "KEYFLAG": "X"},
    {"TABNAME": "MARC", "FIELDNAME": "WERKS", "KEYFLAG": "X"},
    {"TABNAME": "LFA1", "FIELDNAME": "LIFNR", "KEYFLAG": "X"},
    {"TABNAME": "EKKO", "FIELDNAME": "EBELN", "KEYFLAG": "X"},
    {"TABNAME": "Z_SUPPLIER_SCORE", "FIELDNAME": "LIFNR", "KEYFLAG": "X"},
]

MOCK_DD08L_FKS = [
    {"TABNAME": "MARC", "FIELDNAME": "MATNR", "CHECKTABLE": "MARA", "FRKART": "KEY", "CARD": "CN"},
    {"TABNAME": "EKKO", "FIELDNAME": "LIFNR", "CHECKTABLE": "LFA1", "FRKART": "KEY", "CARD": "CN"},
    {"TABNAME": "Z_SUPPLIER_SCORE", "FIELDNAME": "LIFNR", "CHECKTABLE": "LFA1", "FRKART": "KEY", "CARD": "C1"},
]

# Map SAP development classes (Packages) to our modules
DEVCLASS_MAP = {
    "MG": "MM",       # Material Management
    "ME": "PUR",      # Purchasing
    "FB": "BP",       # Business Partner
    "Z_ESG": "COMP",  # Compliance
}

def extract_tables(use_mock: bool) -> List[Dict]:
    if use_mock:
        return MOCK_DD02L_TABLES
    # Phase M7 Placeholder: Execute SQL via hdbcli against SAP HANA
    logger.warning("Real HANA extraction not wired yet (Pending Phase M7). Using mock.")
    return MOCK_DD02L_TABLES

def extract_keys(use_mock: bool) -> List[Dict]:
    if use_mock:
        return MOCK_DD03L_KEYS
    return MOCK_DD03L_KEYS

def extract_fks(use_mock: bool) -> List[Dict]:
    if use_mock:
        return MOCK_DD08L_FKS
    return MOCK_DD08L_FKS

def transform_to_graph(tables, keys, fks):
    """Transform SAP DDIC rows into Memgraph-ready node/edge dicts."""
    nodes = []
    edges = []
    
    # Process Keys
    table_keys = {}
    for k in keys:
        if k["KEYFLAG"] == "X":
            table_keys.setdefault(k["TABNAME"], []).append(k["FIELDNAME"])
            
    # Process Nodes
    table_modules = {}
    for t in tables:
        module = DEVCLASS_MAP.get(t["DEVCLASS"], "CROSS")
        table_modules[t["TABNAME"]] = module
        nodes.append({
            "table_name": t["TABNAME"],
            "module": module,
            "domain": "auto",  # Can be enriched via NLP later
            "description": t.get("DDTEXT", ""),
            "key_columns": table_keys.get(t["TABNAME"], [])
        })
        
    # Process Edges
    for fk in fks:
        src = fk["TABNAME"]
        tgt = fk["CHECKTABLE"]
        
        # Determine bridge type
        src_mod = table_modules.get(src, "UNKNOWN")
        tgt_mod = table_modules.get(tgt, "UNKNOWN")
        bridge_type = "cross_module" if src_mod != tgt_mod else "internal"
        
        # Translate DDIC Cardinality to RAG Cardinality
        card = "1:N" if fk["CARD"] in ["CN", "C"] else "1:1"
        
        edges.append({
            "src": src,
            "tgt": tgt,
            "condition": f"{src}.{fk['FIELDNAME']} = {tgt}.{fk['FIELDNAME']}",
            "cardinality": card,
            "bridge_type": bridge_type,
            "notes": f"DDIC Auto-Ingested FK ({fk['FRKART']})"
        })
        
    return nodes, edges

def main():
    parser = argparse.ArgumentParser(description="DDIC Auto-Ingestion Pipeline")
    parser.add_argument("--mock", action="store_true", default=True, help="Use mock DDIC data")
    args = parser.parse_args()

    logger.info("Starting DDIC Auto-Ingestion Pipeline...")
    
    # 1. Extract
    logger.info("Extracting data from SAP DDIC (DD02L, DD03L, DD08L)...")
    raw_tables = extract_tables(args.mock)
    raw_keys = extract_keys(args.mock)
    raw_fks = extract_fks(args.mock)
    
    # 2. Transform
    logger.info("Transforming SAP metadata into Graph topology...")
    nodes, edges = transform_to_graph(raw_tables, raw_keys, raw_fks)
    logger.info(f"Transformed {len(nodes)} tables and {len(edges)} relationships.")
    
    # 3. Load
    logger.info("Loading into Memgraph...")
    mg = use_memgraph(uri=os.environ.get("MEMGRAPH_URI", "bolt://localhost:7687"))
    
    # Perform the injection directly
    mg.ingest_from_ddic_records(nodes, edges)
    
    logger.info("Ingestion complete. Current Graph stats:")
    print(mg.stats())

if __name__ == "__main__":
    main()