"""
cds_mapping.py — Core Data Services (CDS) View Equivalents
==========================================================
Maps standard SAP HANA physical tables to S/4HANA Cloud Virtual Data Model (VDM) CDS views.
Crucial for S/4HANA Public Cloud environments where direct physical table access 
is restricted and queries must go through the ABAP-managed CDS layer.
"""

from typing import Dict, List, Optional

SAP_TABLE_TO_CDS: Dict[str, str] = {
    # Business Partner / Vendor / Customer
    "BUT000": "I_BusinessPartner",
    "LFA1": "I_Supplier",
    "LFB1": "I_SupplierCompany",
    "LFBK": "I_SupplierBankDetails",
    "KNA1": "I_Customer",
    "KNB1": "I_CustomerCompany",
    "KNVV": "I_CustomerSalesArea",

    # Material Master
    "MARA": "I_Product",
    "MARC": "I_ProductPlant",
    "MARD": "I_ProductStorageLocation",
    "MBEW": "I_ProductValuation",
    "MARM": "I_ProductUnitOfMeasure",
    "MAKT": "I_ProductDescription",

    # Purchasing (MM-PUR)
    "EKKO": "I_PurchaseOrder",
    "EKPO": "I_PurchaseOrderItem",
    "EINA": "I_PurchasingInfoRecord",
    "EINE": "I_PurInfoRecordPrcgCndn",
    "EKES": "I_PurOrdSupplierConfirmation",
    "EORD": "I_PurchasingSourceList",

    # Sales & Distribution (SD)
    "VBAK": "I_SalesOrder",
    "VBAP": "I_SalesOrderItem",
    "VBEP": "I_SalesOrderScheduleLine",
    "LIKP": "I_DeliveryDocument",
    "LIPS": "I_DeliveryDocumentItem",
    "VBRK": "I_BillingDocument",
    "VBRP": "I_BillingDocumentItem",

    # Finance / Controlling (FI/CO)
    "BKPF": "I_JournalEntry",
    "BSEG": "I_JournalEntryItem",
    "CSKS": "I_CostCenter",
    "ANLA": "I_FixedAsset",
    
    # Project Systems (PS)
    "PROJ": "I_Project",
    "PRPS": "I_WBSElement",

    # Quality Management (QM)
    "QALS": "I_InspectionLot",
    "QAVE": "I_InspectionUsageDecision",
}

def get_cds_view(table_name: str) -> str:
    """Returns the S/4HANA CDS view equivalent for a physical table, if available."""
    return SAP_TABLE_TO_CDS.get(table_name.upper(), "")

def translate_path_to_cds(path: List[str]) -> List[str]:
    """
    Translates a list of physical table names into their CDS view equivalents.
    If a CDS view isn't mapped, it falls back to the physical table name.
    """
    return [get_cds_view(t) or t for t in path]

def format_cds_join(physical_join_str: str) -> str:
    """
    Naively translates a generated physical SQL JOIN string into a CDS-based JOIN string
    by replacing table names with their CDS equivalents.
    """
    translated_str = physical_join_str
    # Sort by length descending to prevent partial replacements (e.g. replacing 'LFA1' inside 'LFA1_TMP')
    for table in sorted(SAP_TABLE_TO_CDS.keys(), key=len, reverse=True):
        cds = SAP_TABLE_TO_CDS[table]
        # Replace occurrences. Note: In a robust parser, we'd use regex with word boundaries \b
        import re
        translated_str = re.sub(rf"\b{table}\b", cds, translated_str)
        
    return translated_str
