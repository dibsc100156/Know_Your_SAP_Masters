from typing import List, Dict, Any

# Scaffold Mock of SAP DDIC / Vector Store for Tables
# In production, this data is extracted via RFC (DD02T, DD03L) and embedded into ChromaDB or SAP HANA Vector
MOCK_SAP_SCHEMA_STORE = [
    {
        "table": "LFA1",
        "description": "Vendor Master (General Section). Contains the vendor number, name, country, and address.",
        "key_columns": ["LIFNR", "NAME1", "LAND1", "ORT01"],
        "sensitive_columns": ["BANKL", "BANKN", "STCD1", "STCD2"],
        "module": "MM/FI",
        "auth_object": "F_LFA1_BUK"
    },
    {
        "table": "LFB1",
        "description": "Vendor Master (Company Code Data). Contains the vendor number, company code, and payment terms.",
        "key_columns": ["LIFNR", "BUKRS", "ZTERM", "AKONT"],
        "sensitive_columns": [],
        "module": "FI",
        "auth_object": "F_LFA1_BUK"
    },
    {
        "table": "EKKO",
        "description": "Purchasing Document Header. Contains Purchase Orders, contracts, creation dates, purchasing orgs.",
        "key_columns": ["EBELN", "BUKRS", "BSTYP", "EKORG", "LIFNR"],
        "sensitive_columns": [],
        "module": "MM",
        "auth_object": "M_BEST_EKO"
    },
    {
        "table": "EKPO",
        "description": "Purchasing Document Item. Contains material numbers, quantities, and net prices for Purchase Orders.",
        "key_columns": ["EBELN", "EBELP", "MATNR", "MENGE", "NETPR"],
        "sensitive_columns": [],
        "module": "MM",
        "auth_object": "M_BEST_EKO"
    },
    {
        "table": "BSIK",
        "description": "Accounting: Secondary Index for Vendors (Open Items). Contains unpaid invoices.",
        "key_columns": ["LIFNR", "BUKRS", "BELNR", "DMBTR", "ZFBDT"],
        "sensitive_columns": [],
        "module": "FI",
        "auth_object": "F_BKPF_BUK"
    },
    {
        "table": "BSAK",
        "description": "Accounting: Secondary Index for Vendors (Cleared Items). Contains paid invoices and payment histories.",
        "key_columns": ["LIFNR", "BUKRS", "BELNR", "DMBTR", "AUGBL"],
        "sensitive_columns": [],
        "module": "FI",
        "auth_object": "F_BKPF_BUK"
    }
]

def search_tables(query: str) -> List[Dict[str, Any]]:
    """
    Mock vector search for finding tables relevant to the query.
    In production, this is `vector_store.similarity_search(query)`.
    """
    query_lower = query.lower()
    results = []
    
    # Naive keyword matching to simulate semantic search
    for schema in MOCK_SAP_SCHEMA_STORE:
        if any(word in schema["description"].lower() for word in query_lower.split()):
            results.append(schema)
        elif any(word in schema["table"].lower() for word in query_lower.split()):
            results.append(schema)
            
    # If no exact word match, return the common ones for the scaffold
    if not results:
        results = [s for s in MOCK_SAP_SCHEMA_STORE if s["table"] in ["LFA1", "EKKO", "BSIK"]]
        
    return results