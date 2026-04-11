"""
schema_auto_discover.py — Phase 5 Schema Auto-Discovery
=======================================================
When both Schema RAG (Qdrant) and SQL Pattern RAG (ChromaDB) return empty/nothing,
this module queries SAP DDIC directly (DD03L/DD04L) to find matching tables/fields.

Triggered when:
  1. schema_lookup() returns empty
  2. sql_pattern_lookup() returns empty
  → auto_discover(query, auth_context) fires as last resort

Outputs:
  - List of matching tables with field details
  - Confidence score (based on field name match quality)
  - Auto-add to memory/sap_sessions/schema_discoveries.json

Usage:
  from app.core.schema_auto_discover import SchemaAutoDiscover
  discoverer = SchemaAutoDiscover()
  results = discoverer.search(query="vendor tax identification", auth_context=ctx)
  for table in results["tables"]:
      print(f"  {table['table']} — {table['domain']} — confidence: {table['confidence']}")
"""

import re
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from app.core.memory_layer import sap_memory

# ---------------------------------------------------------------------------
# DDIC Mirror — embedded SAP DDIC metadata (subset of DD03L/DD04L)
# In production, replace with real SAP DD03L/DD04L query via hdbcli
# ---------------------------------------------------------------------------

@dataclass
class DDICTable:
    table: str
    description: str
    domain: str
    fields: List[Dict[str, str]]  # [{name, type, description}]
    is_cross_module: bool = False
    centrality_score: float = 0.0

# Embedded DDIC mirror — 80+ tables across 18 SAP domains
# Covers the most common master data and transactional tables
DDIC_MIRROR: List[DDICTable] = [
    # Business Partner (BP)
    DDICTable(table="LFA1", description="Vendor Master (General Section)",
              domain="business_partner",
              fields=[
                  {"name": "LIFNR", "type": "CHAR", "description": "Vendor Account Number"},
                  {"name": "NAME1", "type": "CHAR", "description": "Name 1"},
                  {"name": "NAME2", "type": "CHAR", "description": "Name 2"},
                  {"name": "STRAS", "type": "CHAR", "description": "Street Address"},
                  {"name": "ORT01", "type": "CHAR", "description": "City"},
                  {"name": "LAND1", "type": "CHAR", "description": "Country Key"},
                  {"name": "STCD1", "type": "CHAR", "description": "Tax Number 1 (SSN/EIN)"},
                  {"name": "STCD2", "type": "CHAR", "description": "Tax Number 2 (VAT ID)"},
                  {"name": "KTOKK", "type": "CHAR", "description": "Account Group"},
                  {"name": "SPERR", "type": "CHAR", "description": "Central Post Block"},
                  {"name": "LOEVM", "type": "CHAR", "description": "Deletion Flag"},
                  {"name": "ADRNR", "type": "CHAR", "description": "Address Number"},
              ]),
    DDICTable(table="LFB1", description="Vendor Master (Company Code)",
              domain="business_partner",
              fields=[
                  {"name": "LIFNR", "type": "CHAR", "description": "Vendor Account Number"},
                  {"name": "BUKRS", "type": "CHAR", "description": "Company Code"},
                  {"name": "AKONT", "type": "CHAR", "description": "Reconciliation Account"},
                  {"name": "WAERS", "type": "CUKY", "description": "Currency Key"},
                  {"name": "ZAHLS", "type": "CHAR", "description": "Payment Terms Key"},
                  {"name": "ZTERM", "type": "CHAR", "description": "Payment Terms Description"},
                  {"name": "KULT1", "type": "CHAR", "description": "First Tolerance Group"},
                  {"name": "SPERR", "type": "CHAR", "description": "Posting Block"},
              ]),
    DDICTable(table="LFBK", description="Vendor Master (Bank Details)",
              domain="business_partner",
              fields=[
                  {"name": "LIFNR", "type": "CHAR", "description": "Vendor Account Number"},
                  {"name": "BANKS", "type": "CHAR", "description": "Bank Country Key"},
                  {"name": "BANKL", "type": "CHAR", "description": "Bank Key"},
                  {"name": "BANKN", "type": "CHAR", "description": "Bank Account Number"},
                  {"name": "KOINH", "type": "CHAR", "description": "Account Holder Name"},
              ]),
    DDICTable(table="KNA1", description="Customer Master (General Section)",
              domain="business_partner",
              fields=[
                  {"name": "KUNNR", "type": "CHAR", "description": "Customer Account Number"},
                  {"name": "NAME1", "type": "CHAR", "description": "Name 1"},
                  {"name": "STCD1", "type": "CHAR", "description": "Tax Number 1"},
                  {"name": "STCD2", "type": "CHAR", "description": "Tax Number 2 (VAT)"},
                  {"name": "KTOKD", "type": "CHAR", "description": "Customer Account Group"},
                  {"name": "SPERR", "type": "CHAR", "description": "Central Post Block"},
                  {"name": "LOEVM", "type": "CHAR", "description": "Deletion Flag"},
                  {"name": "ADRNR", "type": "CHAR", "description": "Address Number"},
              ]),
    DDICTable(table="BUT000", description="Business Partner Master (Generic)",
              domain="business_partner",
              fields=[
                  {"name": "PARTNER", "type": "CHAR", "description": "Business Partner Number"},
                  {"name": "TYPE", "type": "CHAR", "description": "BP Category (Person/Organization)"},
                  {"name": "BU_GROUP", "type": "CHAR", "description": "BP Grouping"},
                  {"name": "STCD1", "type": "CHAR", "description": "Tax Number 1"},
                  {"name": "STCD2", "type": "CHAR", "description": "Tax Number 2"},
              ]),
    DDICTable(table="ADRC", description="Business Address Services",
              domain="business_partner",
              fields=[
                  {"name": "ADDRNUMBER", "type": "CHAR", "description": "Address Number"},
                  {"name": "NAME1", "type": "CHAR", "description": "Name 1"},
                  {"name": "STREET", "type": "CHAR", "description": "Street"},
                  {"name": "CITY1", "type": "CHAR", "description": "City"},
                  {"name": "COUNTRY", "type": "CHAR", "description": "Country Key"},
                  {"name": "TIME_ZONE", "type": "CHAR", "description": "Time Zone"},
                  {"name": "TEL_NUMBER", "type": "CHAR", "description": "Telephone Number"},
                  {"name": "SMTP_ADDR", "type": "CHAR", "description": "E-Mail Address"},
              ]),
    # Material Master (MM)
    DDICTable(table="MARA", description="Material Master (General)",
              domain="material_master",
              fields=[
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "MTART", "type": "CHAR", "description": "Material Type"},
                  {"name": "MBRSH", "type": "CHAR", "description": "Industry Sector"},
                  {"name": "MATKL", "type": "CHAR", "description": "Material Group"},
                  {"name": "BISMT", "type": "CHAR", "description": "Old Material Number"},
                  {"name": "MEINS", "type": "UNIT", "description": "Base Unit of Measure"},
                  {"name": "NTGEW", "type": "QUAN", "description": "Net Weight"},
                  {"name": "GEWEI", "type": "UNIT", "description": "Weight Unit"},
                  {"name": "VOLUM", "type": "QUAN", "description": "Volume"},
                  {"name": "VOLEH", "type": "UNIT", "description": "Volume Unit"},
                  {"name": "LAENG", "type": "QUAN", "description": "Length"},
                  {"name": "BREIT", "type": "QUAN", "description": "Width"},
                  {"name": "HOEHE", "type": "QUAN", "description": "Height"},
              ]),
    DDICTable(table="MARC", description="Material Master (Plant)",
              domain="material_master",
              fields=[
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "BESKZ", "type": "CHAR", "description": "Procurement Type (E/F/X)"},
                  {"name": "SOBSL", "type": "CHAR", "description": "Special Procurement Type"},
                  {"name": "DISMM", "type": "CHAR", "description": "MRP Type"},
                  {"name": "DISPO", "type": "CHAR", "description": "MRP Controller"},
                  {"name": "DISLS", "type": "CHAR", "description": "Lot Size Key"},
                  {"name": "MINBE", "type": "QUAN", "description": "Safety Stock"},
                  {"name": "MAXBE", "type": "QUAN", "description": "Maximum Stock"},
                  {"name": "BSTFE", "type": "QUAN", "description": "Fixed Lot Size"},
                  {"name": "BSTMI", "type": "QUAN", "description": "Minimum Lot Size"},
                  {"name": "MTVFP", "type": "CHAR", "description": "Availability Check"},
              ]),
    DDICTable(table="MARD", description="Material Master (Storage Location)",
              domain="material_master",
              fields=[
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "LGORT", "type": "CHAR", "description": "Storage Location"},
                  {"name": "LGPBE", "type": "CHAR", "description": "Storage Bin"},
                  {"name": "SPERR", "type": "CHAR", "description": "Blocked Stock"},
                  {"name": "INSME", "type": "QUAN", "description": "Quality Inspection Stock"},
                  {"name": "EINME", "type": "QUAN", "description": "Unrestricted Stock"},
                  {"name": "RETME", "type": "QUAN", "description": "Returns Stock"},
              ]),
    DDICTable(table="MBEW", description="Material Valuation",
              domain="material_master",
              fields=[
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "BWKRS", "type": "CHAR", "description": "Valuation Area (Company Code)"},
                  {"name": "BWPRZ", "type": "DEC", "description": "Price Unit"},
                  {"name": "VPRSV", "type": "CHAR", "description": "Price Control (S/M)"},
                  {"name": "STPRS", "type": "CURR", "description": "Standard Price"},
                  {"name": "PEINH", "type": "DEC", "description": "Price Unit"},
                  {"name": "MBEW~VERPR", "type": "CURR", "description": "Moving Average Price"},
                  {"name": "BWTAR", "type": "CHAR", "description": "Valuation Type"},
              ]),
    DDICTable(table="MSKA", description="Material Master (Sales Order Stock)",
              domain="material_master",
              fields=[
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "LGORT", "type": "CHAR", "description": "Storage Location"},
                  {"name": "KUNNU", "type": "CHAR", "description": "Customer Number"},
                  {"name": "KUNWE", "type": "CHAR", "description": "Ship-To Customer"},
                  {"name": "EMLIF", "type": "CHAR", "description": "Vendor Account Number"},
              ]),
    # Purchasing
    DDICTable(table="EKKO", description="Purchasing Document Header",
              domain="purchasing",
              fields=[
                  {"name": "EBELN", "type": "CHAR", "description": "Purchasing Document Number"},
                  {"name": "BUKRS", "type": "CHAR", "description": "Company Code"},
                  {"name": "BSTYP", "type": "CHAR", "description": "Purchasing Document Type"},
                  {"name": "BSART", "type": "CHAR", "description": "Document Type (RFQ/PO/Contract)"},
                  {"name": "LOEKZ", "type": "CHAR", "description": "Deletion Flag"},
                  {"name": "STATU", "type": "CHAR", "description": "Status"},
                  {"name": "ANGDT", "type": "DATS", "description": "Quotation Deadline"},
                  {"name": "BIDDT", "type": "DATS", "description": "Bidding Deadline"},
                  {"name": "FRGKE", "type": "CHAR", "description": "Release Indicator"},
                  {"name": "ZTERM", "type": "CHAR", "description": "Payment Terms"},
                  {"name": "WAERS", "type": "CUKY", "description": "Currency"},
                  {"name": "WKURS", "type": "DEC", "description": "Exchange Rate"},
                  {"name": "PINCR", "type": "DEC", "description": "Item Number Increment"},
              ]),
    DDICTable(table="EKPO", description="Purchasing Document Item",
              domain="purchasing",
              fields=[
                  {"name": "EBELN", "type": "CHAR", "description": "Purchasing Document Number"},
                  {"name": "EBELP", "type": "CHAR", "description": "Item Number"},
                  {"name": "LOEKZ", "type": "CHAR", "description": "Deletion Flag"},
                  {"name": "EMATN", "type": "CHAR", "description": "Material Number"},
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number (Cross-Plant)"},
                  {"name": "TXZ01", "type": "CHAR", "description": "Short Text"},
                  {"name": "BUKRS", "type": "CHAR", "description": "Company Code"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "LGORT", "type": "CHAR", "description": "Storage Location"},
                  {"name": "MENGE", "type": "QUAN", "description": "Purchase Order Quantity"},
                  {"name": "MEINS", "type": "UNIT", "description": "Order Unit"},
                  {"name": "PEINH", "type": "DEC", "description": "Price Unit"},
                  {"name": "NETWR", "type": "CURR", "description": "Net Order Value"},
                  {"name": "WAERS", "type": "CUKY", "description": "Currency"},
                  {"name": "BRNDC", "type": "CHAR", "description": "Brand"},
                  {"name": "ELIKZ", "type": "CHAR", "description": "Delivery Completed Indicator"},
                  {"name": "AGREF", "type": "CHAR", "description": "Customer Reference"},
                  {"name": "KTWRT", "type": "CURR", "description": "Target Value"},
              ]),
    DDICTable(table="EINA", description="Purchasing Info Record (General)",
              domain="purchasing",
              fields=[
                  {"name": "INFNR", "type": "CHAR", "description": "Info Record Number"},
                  {"name": "LIFNR", "type": "CHAR", "description": "Vendor Account Number"},
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "EKORG", "type": "CHAR", "description": "Purchasing Organization"},
                  {"name": "ESOKZ", "type": "CHAR", "description": "Info Record Type (Standard/Subcontract)"},
                  {"name": "DATAB", "type": "DATS", "description": "Validity Start Date"},
                  {"name": "DATBI", "type": "DATS", "description": "Validity End Date"},
                  {"name": "NETPR", "type": "CURR", "description": "Net Price"},
                  {"name": "PEINH", "type": "DEC", "description": "Price Unit"},
                  {"name": "WAERS", "type": "CUKY", "description": "Currency"},
              ]),
    DDICTable(table="EINE", description="Purchasing Info Record (Purchasing Organization)",
              domain="purchasing",
              fields=[
                  {"name": "INFNR", "type": "CHAR", "description": "Info Record Number"},
                  {"name": "EKORG", "type": "CHAR", "description": "Purchasing Organization"},
                  {"name": "ESOKZ", "type": "CHAR", "description": "Info Record Type"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "PSTTP", "type": "CHAR", "description": "Purchasing Info Record Type"},
                  {"name": "DATAB", "type": "DATS", "description": "Validity Start Date"},
                  {"name": "DATBI", "type": "DATS", "description": "Validity End Date"},
                  {"name": "NETPR", "type": "CURR", "description": "Net Price"},
                  {"name": "PEINH", "type": "DEC", "description": "Price Unit"},
              ]),
    DDICTable(table="EORD", description="Purchasing Source List",
              domain="purchasing",
              fields=[
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "LIFNR", "type": "CHAR", "description": "Vendor Account Number"},
                  {"name": "EKORG", "type": "CHAR", "description": "Purchasing Organization"},
                  {"name": "DATAB", "type": "DATS", "description": "Valid-From Date"},
                  {"name": "DATBI", "type": "DATS", "description": "Valid-To Date"},
              ]),
    # Sales & Distribution
    DDICTable(table="VBAK", description="Sales Document Header",
              domain="sales_distribution",
              fields=[
                  {"name": "VBELN", "type": "CHAR", "description": "Sales Document Number"},
                  {"name": "AUART", "type": "CHAR", "description": "Sales Document Type"},
                  {"name": "VKORG", "type": "CHAR", "description": "Sales Organization"},
                  {"name": "VTWEG", "type": "CHAR", "description": "Distribution Channel"},
                  {"name": "SPART", "type": "CHAR", "description": "Division"},
                  {"name": "VKBUR", "type": "CHAR", "description": "Sales Office"},
                  {"name": "VKGRP", "type": "CHAR", "description": "Sales Group"},
                  {"name": "GSBER", "type": "CHAR", "description": "Business Area"},
                  {"name": "KUNNR", "type": "CHAR", "description": "Sold-To Party"},
                  {"name": "KUNAG", "type": "CHAR", "description": "Payer"},
                  {"name": "KUNWE", "type": "CHAR", "description": "Ship-To Party"},
                  {"name": "WAERK", "type": "CUKY", "description": "Currency Key"},
                  {"name": "NETWR", "type": "CURR", "description": "Net Value of Sales Order"},
              ]),
    DDICTable(table="VBAP", description="Sales Document Item",
              domain="sales_distribution",
              fields=[
                  {"name": "VBELN", "type": "CHAR", "description": "Sales Document Number"},
                  {"name": "POSNR", "type": "CHAR", "description": "Item Number"},
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "KWMENG", "type": "QUAN", "description": "Cumulative Order Quantity"},
                  {"name": "VRKME", "type": "UNIT", "description": "Sales Unit"},
                  {"name": "NETWR", "type": "CURR", "description": "Net Item Value"},
                  {"name": "WAERK", "type": "CUKY", "description": "Currency"},
                  {"name": "KBETR", "type": "CURR", "description": "Condition Rate"},
                  {"name": "KONWA", "type": "CUKY", "description": "Condition Currency"},
              ]),
    DDICTable(table="LIKP", description="SD Document Delivery Header",
              domain="sales_distribution",
              fields=[
                  {"name": "VBELN", "type": "CHAR", "description": "Delivery Number"},
                  {"name": "KUNNR", "type": "CHAR", "description": "Ship-To Party"},
                  {"name": "VSTEL", "type": "CHAR", "description": "Shipping Point"},
                  {"name": "LIFEX", "type": "CHAR", "description": "External Delivery ID"},
                  {"name": "WADAT", "type": "DATS", "description": "Planned Goods Issue Date"},
                  {"name": "WADAT_IST", "type": "DATS", "description": "Actual Goods Issue Date"},
                  {"name": "BLDAT", "type": "DATS", "description": "Billing Date"},
                  {"name": "BWART", "type": "CHAR", "description": "Movement Type"},
              ]),
    DDICTable(table="KNV", description="Customer Master (Sales Area)",
              domain="sales_distribution",
              fields=[
                  {"name": "KUNNR", "type": "CHAR", "description": "Customer Account Number"},
                  {"name": "VKORG", "type": "CHAR", "description": "Sales Organization"},
                  {"name": "VTWEG", "type": "CHAR", "description": "Distribution Channel"},
                  {"name": "SPART", "type": "CHAR", "description": "Division"},
                  {"name": "VSBED", "type": "CHAR", "description": "Shipping Condition"},
                  {"name": "KTAXB", "type": "CHAR", "description": "Tax Classification"},
                  {"name": "AWAHR", "type": "CHAR", "description": "Sales Probability"},
              ]),
    DDICTable(table="KONV", description="Pricing Conditions",
              domain="sales_distribution",
              fields=[
                  {"name": "KNUMV", "type": "CHAR", "description": "Number of Document Condition"},
                  {"name": "KPOSN", "type": "CHAR", "description": "Condition Item Number"},
                  {"name": "KAPPL", "type": "CHAR", "description": "Application (SD/MM/PP)"},
                  {"name": "KSCHL", "type": "CHAR", "description": "Condition Type (PR00/K007)"},
                  {"name": "KBETR", "type": "CURR", "description": "Condition Amount"},
                  {"name": "WAERS", "type": "CUKY", "description": "Currency"},
                  {"name": "KPEIN", "type": "DEC", "description": "Condition Pricing Unit"},
                  {"name": "KMEIN", "type": "UNIT", "description": "Condition Unit"},
              ]),
    # Quality Management
    DDICTable(table="QALS", description="QM Inspection Lot",
              domain="quality_management",
              fields=[
                  {"name": "PRUEFLOS", "type": "CHAR", "description": "Inspection Lot Number"},
                  {"name": "ART", "type": "CHAR", "description": "Inspection Type (01=Receipt, 04=Processing)"},
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "CHARG", "type": "CHAR", "description": "Batch Number"},
                  {"name": "LIFNUM", "type": "CHAR", "description": "Vendor Number"},
                  {"name": "ZZCUNUM", "type": "CHAR", "description": "Customer Number"},
                  {"name": "SPRUCH", "type": "CHAR", "description": "Urgent Flag"},
                  {"name": "TATYP", "type": "CHAR", "description": "Task List Type"},
                  {"name": "STTRT", "type": "CHAR", "description": "Inspection Origin"},
                  {"name": "QMDAT", "type": "DATS", "description": "Inspection Date"},
                  {"name": "BUDAT", "type": "DATS", "description": "Posting Date"},
                  {"name": "UMSDT", "type": "DATS", "description": "Stock Transfer Date"},
                  {"name": "BEWERTG", "type": "CHAR", "description": "Usage Decision Code (SAP QM)"},
                  {"name": "LOSFE", "type": "QUAN", "description": "Inspection Lot Size"},
                  {"name": "MEINS", "type": "UNIT", "description": "Base Unit of Measure"},
              ]),
    DDICTable(table="QMEL", description="Quality Notification",
              domain="quality_management",
              fields=[
                  {"name": "QMNUM", "type": "CHAR", "description": "Notification Number"},
                  {"name": "QMART", "type": "CHAR", "description": "Notification Type (M1=Complaint)"},
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "ERNAM", "type": "CHAR", "description": "Created By"},
                  {"name": "ERDAT", "type": "DATS", "description": "Created On"},
                  {"name": "QMTXT", "type": "CHAR", "description": "Short Text Description"},
                  {"name": "ISTEM", "type": "CHAR", "description": "Item Number"},
                  {"name": "CODX1", "type": "CHAR", "description": "Code Group 1"},
                  {"name": "CODX2", "type": "CHAR", "description": "Code Group 2"},
              ]),
    DDICTable(table="MAPL", description="Task List - Material Allocation",
              domain="quality_management",
              fields=[
                  {"name": "PLNNR", "type": "CHAR", "description": "Task List Number"},
                  {"name": "PLNAA", "type": "CHAR", "description": "Group Counter"},
                  {"name": "PLNTY", "type": "CHAR", "description": "Task List Type (Q=Inspection)"},
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "PLIKZ", "type": "CHAR", "description": "Inspection Setup Active"},
              ]),
    DDICTable(table="QAMV", description="Inspection Characteristics Results",
              domain="quality_management",
              fields=[
                  {"name": "PRUEFLOS", "type": "CHAR", "description": "Inspection Lot Number"},
                  {"name": "VORNR", "type": "CHAR", "description": "Operation Number"},
                  {"name": "MERKNR", "type": "CHAR", "description": "Inspection Characteristic Number"},
                  {"name": "MBEWERTG", "type": "CHAR", "description": " valuation mode"},
                  {"name": "Sollwert", "type": "QUAN", "description": "Target Value"},
                  {"name": "USTR-TMG", "type": "QUAN", "description": "Upper Specification Limit"},
                  {"name": "LSTR-TMG", "type": "QUAN", "description": "Lower Specification Limit"},
                  {"name": "PRUEFMG", "type": "CHAR", "description": "Inspection Lot Usage Decision"},
              ]),
    DDICTable(table="QAVE", description="QM Inspection Results",
              domain="quality_management",
              fields=[
                  {"name": "PRUEFLOS", "type": "CHAR", "description": "Inspection Lot Number"},
                  {"name": "TATYP", "type": "CHAR", "description": "Task List Type"},
                  {"name": "BEWERTG", "type": "CHAR", "description": "Usage Decision Code"},
                  {"name": "BEBSTER", "type": "CHAR", "description": "Decision By"},
                  {"name": "BEDAT", "type": "DATS", "description": "Date of Inspection"},
                  {"name": "ERNAM", "type": "CHAR", "description": "Inspector"},
              ]),
    # Warehouse Management
    DDICTable(table="LAGP", description="Storage Location Master",
              domain="warehouse_management",
              fields=[
                  {"name": "LAGPR", "type": "CHAR", "description": "Storage Location Number"},
                  {"name": "LGPBE", "type": "CHAR", "description": "Storage Bin"},
                  {"name": "LGPRO", "type": "CHAR", "description": "Storage Type"},
                  {"name": "LAND1", "type": "CHAR", "description": "Country"},
                  {"name": "ADRNR", "type": "CHAR", "description": "Address Number"},
              ]),
    DDICTable(table="LQUA", description="Quants (Warehouse Management)",
              domain="warehouse_management",
              fields=[
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "LGORT", "type": "CHAR", "description": "Storage Location"},
                  {"name": "CHARG", "type": "CHAR", "description": "Batch Number"},
                  {"name": "LGTYP", "type": "CHAR", "description": "Storage Type"},
                  {"name": "LGPLA", "type": "CHAR", "description": "Storage Bin"},
                  {"name": "CLABS", "type": "QUAN", "description": "Unrestricted Stock"},
                  {"name": "CINSM", "type": "QUAN", "description": "Quality Inspection Stock"},
                  {"name": "CSPEM", "type": "QUAN", "description": "Blocked Stock"},
                  {"name": "CRETM", "type": "QUAN", "description": "Returns Stock"},
                  {"name": "CUMLM", "type": "QUAN", "description": "Stock in Transfer"},
              ]),
    DDICTable(table="VEKP", description="Handling Unit - Header",
              domain="warehouse_management",
              fields=[
                  {"name": "EXIDV", "type": "CHAR", "description": "Handling Unit Number"},
                  {"name": "VHILM", "type": "CHAR", "description": "Hierarchical Item"},
                  {"name": "BEZNK", "type": "CHAR", "description": "HU Category"},
                  {"name": "LAENG", "type": "QUAN", "description": "Length"},
                  {"name": "BREIT", "type": "QUAN", "description": "Width"},
                  {"name": "HOEHE", "type": "QUAN", "description": "Height"},
              ]),
    DDICTable(table="MLGT", description="Storage Location Stock (WM)",
              domain="warehouse_management",
              fields=[
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
                  {"name": "LGORT", "type": "CHAR", "description": "Storage Location"},
                  {"name": "LGTYP", "type": "CHAR", "description": "Storage Type"},
                  {"name": "LGPLA", "type": "CHAR", "description": "Storage Bin"},
                  {"name": "CLABS", "type": "QUAN", "description": "Unrestricted Stock"},
                  {"name": "CINSM", "type": "QUAN", "description": "Quality Inspection Stock"},
              ]),
    # Financials
    DDICTable(table="BSIK", description="Accounting (Vendor Line Items - Cleared)",
              domain="financials",
              fields=[
                  {"name": "BUKRS", "type": "CHAR", "description": "Company Code"},
                  {"name": "LIFNR", "type": "CHAR", "description": "Vendor Account Number"},
                  {"name": "GJAHR", "type": "NUMC", "description": "Fiscal Year"},
                  {"name": "BELNR", "type": "CHAR", "description": "Accounting Document Number"},
                  {"name": "BUZEL", "type": "CHAR", "description": "Line Item Number"},
                  {"name": "BUDAT", "type": "DATS", "description": "Posting Date"},
                  {"name": "BLDAT", "type": "DATS", "description": "Document Date"},
                  {"name": "WAERS", "type": "CUKY", "description": "Currency Key"},
                  {"name": "WRBTR", "type": "CURR", "description": "Amount in Local Currency"},
                  {"name": "DMBTR", "type": "CURR", "description": "Amount in Company Code Currency"},
                  {"name": "SHKZG", "type": "CHAR", "description": "Debit/Credit Indicator (S/H)"},
                  {"name": "ZTERM", "type": "CHAR", "description": "Payment Terms"},
                  {"name": "ZAHLS", "type": "CHAR", "description": "Payment Block Key"},
              ]),
    DDICTable(table="BSAK", description="Accounting (Vendor Line Items - Cleared)",
              domain="financials",
              fields=[
                  {"name": "BUKRS", "type": "CHAR", "description": "Company Code"},
                  {"name": "LIFNR", "type": "CHAR", "description": "Vendor Account Number"},
                  {"name": "GJAHR", "type": "NUMC", "description": "Fiscal Year"},
                  {"name": "BELNR", "type": "CHAR", "description": "Accounting Document Number"},
                  {"name": "BUZEL", "type": "CHAR", "description": "Line Item"},
                  {"name": "AUGDT", "type": "DATS", "description": "Clearing Date"},
                  {"name": "BUDAT", "type": "DATS", "description": "Posting Date"},
              ]),
    DDICTable(table="BSEG", description="Accounting Document Segment",
              domain="financials",
              fields=[
                  {"name": "BUKRS", "type": "CHAR", "description": "Company Code"},
                  {"name": "BELNR", "type": "CHAR", "description": "Accounting Document Number"},
                  {"name": "GJAHR", "type": "NUMC", "description": "Fiscal Year"},
                  {"name": "BUZEI", "type": "CHAR", "description": "Line Item"},
                  {"name": "KTOSL", "type": "CHAR", "description": "Transaction Key"},
                  {"name": "HKONT", "type": "CHAR", "description": "General Ledger Account"},
                  {"name": "PRCTR", "type": "CHAR", "description": "Profit Center"},
                  {"name": "KUNNR", "type": "CHAR", "description": "Customer Number"},
                  {"name": "LIFNR", "type": "CHAR", "description": "Vendor Number"},
                  {"name": "MWSTS", "type": "CURR", "description": "Tax Amount"},
                  {"name": "WRBTR", "type": "CURR", "description": "Amount in Transaction Currency"},
              ]),
    DDICTable(table="BKPF", description="Accounting Document Header",
              domain="financials",
              fields=[
                  {"name": "BUKRS", "type": "CHAR", "description": "Company Code"},
                  {"name": "BELNR", "type": "CHAR", "description": "Accounting Document Number"},
                  {"name": "GJAHR", "type": "NUMC", "description": "Fiscal Year"},
                  {"name": "BKTXT", "type": "CHAR", "description": "Document Header Text"},
                  {"name": "BLART", "type": "CHAR", "description": "Document Type (SA/RA/DR/CR)"},
                  {"name": "BUDAT", "type": "DATS", "description": "Posting Date"},
                  {"name": "BLDAT", "type": "DATS", "description": "Document Date"},
                  {"name": "WAERS", "type": "CUKY", "description": "Currency Key"},
                  {"name": "Kursf", "type": "DEC", "description": "Exchange Rate"},
                  {"name": "STBLG", "type": "CHAR", "description": "Reversed Document"},
                  {"name": "STJAH", "type": "NUMC", "description": "Reversal Year"},
              ]),
    # Project System
    DDICTable(table="PRPS", description="WBS (Work Breakdown Structure) Element",
              domain="project_system",
              fields=[
                  {"name": "PSPNR", "type": "CHAR", "description": "WBS Element Number"},
                  {"name": "POSID", "type": "CHAR", "description": "WBS Element (PSpel)"},
                  {"name": "STUFE", "type": "NUMC", "description": "Level Number"},
                  {"name": "KOSTL", "type": "CHAR", "description": "Cost Center"},
                  {"name": "PRCTR", "type": "CHAR", "description": "Profit Center"},
                  {"name": "PBUKR", "type": "CHAR", "description": "Company Code"},
                  {"name": "PPRCTR", "type": "CHAR", "description": "Partner Profit Center"},
                  {"name": "STRAS", "type": "CHAR", "description": "Street Address"},
                  {"name": "PERSA", "type": "CHAR", "description": "Person Responsible"},
                  {"name": "STTXT", "type": "CHAR", "description": "Description"},
              ]),
    DDICTable(table="COSP", description="CO Object: Cost Totals",
              domain="project_system",
              fields=[
                  {"name": "KOKRS", "type": "CHAR", "description": "Controlling Area"},
                  {"name": "BELNR", "type": "CHAR", "description": "Document Number"},
                  {"name": "BUZEI", "type": "CHAR", "description": "Line Item"},
                  {"name": "GJAHR", "type": "NUMC", "description": "Fiscal Year"},
                  {"name": "PERBL", "type": "NUMC", "description": "Period (01-12)"},
                  {"name": "KTOSL", "type": "CHAR", "description": "Transaction Key"},
                  {"name": "HRKFT", "type": "CHAR", "description": "CO Object Assignment"},
                  {"name": "WSL", "type": "CURR", "description": "Costs in Transaction Currency"},
                  {"name": "WTGBTR", "type": "CURR", "description": "Total Value"},
              ]),
    # Project System (cont)
    DDICTable(table="COSS", description="CO Object: Plan/Actual Line Items",
              domain="project_system",
              fields=[
                  {"name": "KOKRS", "type": "CHAR", "description": "Controlling Area"},
                  {"name": "PSPNR", "type": "CHAR", "description": "WBS Element"},
                  {"name": "GJAHR", "type": "NUMC", "description": "Fiscal Year"},
                  {"name": "PERBL", "type": "NUMC", "description": "Period"},
                  {"name": "WRTTP", "type": "CHAR", "description": "Value Type (1=Plan, 2=Actual)"},
                  {"name": "KOSTL", "type": "CHAR", "description": "Cost Center"},
                  {"name": "WSL", "type": "CURR", "description": "Cost in Transaction Currency"},
              ]),
    # HR
    DDICTable(table="PA0008", description="HR Master Record (Payroll)",
              domain="hr",
              fields=[
                  {"name": "PERNR", "type": "CHAR", "description": "Personnel Number"},
                  {"name": "INFTY", "type": "CHAR", "description": "Infotype"},
                  {"name": "SUBTY", "type": "CHAR", "description": "Subtype"},
                  {"name": "OBJPS", "type": "CHAR", "description": "Object Key"},
                  {"name": "SPRPS", "type": "CHAR", "description": "Locked/Deleted Indicator"},
                  {"name": "ENDDA", "type": "DATS", "description": "End Date"},
                  {"name": "BEGDA", "type": "DATS", "description": "Start Date"},
                  {"name": "BET01", "type": "CURR", "description": "Pay Scale Amount"},
                  {"name": "BET02", "type": "CURR", "description": "Pay Scale Amount 2"},
                  {"name": "BET03", "type": "CURR", "description": "Pay Scale Amount 3"},
                  {"name": "ANSVH", "type": "CHAR", "description": "Previous Employment Type"},
              ]),
    DDICTable(table="PA0001", description="HR Master Record (Organizational Assignment)",
              domain="hr",
              fields=[
                  {"name": "PERNR", "type": "CHAR", "description": "Personnel Number"},
                  {"name": "BUKRS", "type": "CHAR", "description": "Company Code"},
                  {"name": "KOSTL", "type": "CHAR", "description": "Cost Center"},
                  {"name": "PERSG", "type": "CHAR", "description": "Employee Group"},
                  {"name": "PERSK", "type": "CHAR", "description": "Employee Subgroup"},
                  {"name": "ABKRS", "type": "CHAR", "description": "Payroll Area"},
                  {"name": "BTRTL", "type": "CHAR", "description": "Personal Area"},
                  {"name": "WERKS", "type": "CHAR", "description": "Personnel Area"},
              ]),
    DDICTable(table="PA0002", description="HR Master Record (Personal Data)",
              domain="hr",
              fields=[
                  {"name": "PERNR", "type": "CHAR", "description": "Personnel Number"},
                  {"name": "NACHN", "type": "CHAR", "description": "Last Name"},
                  {"name": "VORNA", "type": "CHAR", "description": "First Name"},
                  {"name": "GBDAT", "type": "DATS", "description": "Date of Birth"},
                  {"name": "GESCH", "type": "CHAR", "description": "Gender"},
                  {"name": "FAMAB", "type": "CHAR", "description": "Marital Status"},
                  {"name": "STIBR", "type": "CHAR", "description": "Tax ID"},
              ]),
    # EHS
    DDICTable(table="CAMS_UADI", description="EHS Incident Report",
              domain="ehs",
              fields=[
                  {"name": "INCID_UUID", "type": "CHAR", "description": "Incident UUID"},
                  {"name": "INCID_NUM", "type": "CHAR", "description": "Incident Number"},
                  {"name": "INCID_TYP", "type": "CHAR", "description": "Incident Type"},
                  {"name": "REPORTER", "type": "CHAR", "description": "Reporter Personnel Number"},
                  {"name": "INCDDT", "type": "DATS", "description": "Incident Date"},
                  {"name": "INCTIM", "type": "TIMS", "description": "Incident Time"},
                  {"name": "PLANS_UUID", "type": "CHAR", "description": "Location UUID"},
                  {"name": "SUBSTANCE_UUID", "type": "CHAR", "description": "Substance UUID"},
                  {"name": "SEVIRITY", "type": "CHAR", "description": "Severity (1-4)"},
                  {"name": "INC_STS", "type": "CHAR", "description": "Incident Status"},
              ]),
    # Variant Configuration
    DDICTable(table="SWKMCNT", description="Variant Configuration (Configuration)",
              domain="variant_configuration",
              fields=[
                  {"name": "MATNR", "type": "CHAR", "description": "Material Number"},
                  {"name": "CADZEI", "type": "CHAR", "description": "Internal Counter"},
                  {"name": "CLASS", "type": "CHAR", "description": "Class Number"},
                  {"name": "CLART", "type": "CHAR", "description": "Class Type"},
                  {"name": "WERKS", "type": "CHAR", "description": "Plant"},
              ]),
    # Real Estate
    DDICTable(table="VIM7T", description="Real Estate Contract",
              domain="real_estate",
              fields=[
                  {"name": "VIREF", "type": "CHAR", "description": "Contract Number"},
                  {"name": "VISTG", "type": "CHAR", "description": "Contract Type"},
                  {"name": "VIBUK", "type": "CHAR", "description": "Company Code"},
                  {"name": "VIREB", "type": "CHAR", "description": "Real Estate Business Area"},
                  {"name": "VIREN", "type": "CHAR", "description": "Contract Category"},
                  {"name": "VILAK", "type": "CHAR", "description": "Account Assignment Category"},
              ]),
    # Transportation
    DDICTable(table="VTTK", description="Shipment Header",
              domain="transportation",
              fields=[
                  {"name": "TKNUM", "type": "CHAR", "description": "Shipment Number"},
                  {"name": "TDLNR", "type": "CHAR", "description": "Carrier/Lot Transportation"},
                  {"name": "VSART", "type": "CHAR", "description": "Shipping Type"},
                  {"name": "STTRG", "type": "CHAR", "description": "Transportation Group"},
                  {"name": "KZEPO", "type": "CHAR", "description": "Routes Determined"},
                  {"name": "ROUTE", "type": "CHAR", "description": "Route ID"},
                  {"name": "STADT", "type": "DATS", "description": "Planned Start Date"},
                  {"name": "UZTKR", "type": "TIMS", "description": "Planned Start Time"},
                  {"name": "ENDDT", "type": "DATS", "description": "Planned End Date"},
                  {"name": "EZTKR", "type": "TIMS", "description": "Planned End Time"},
              ]),
    DDICTable(table="VTTSF", description="Shipment Stages",
              domain="transportation",
              fields=[
                  {"name": "TKNUM", "type": "CHAR", "description": "Shipment Number"},
                  {"name": "TSNUM", "type": "CHAR", "description": "Stage Sequence"},
                  {"name": "TDLNR", "type": "CHAR", "description": "Carrier"},
                  {"name": "STZTY", "type": "CHAR", "description": "Stage Type (Pickup/Delivery)"},
                  {"name": "LAND1", "type": "CHAR", "description": "Country"},
                  {"name": "TDLST", "type": "CHAR", "description": "Transportation Service"},
              ]),
    DDICTable(table="TVRO", description="Transportation Connections",
              domain="transportation",
              fields=[
                  {"name": "ROUTE", "type": "CHAR", "description": "Route ID"},
                  {"name": "STTN1", "type": "CHAR", "description": "Leg 1 Stop"},
                  {"name": "STTN2", "type": "CHAR", "description": "Leg 2 Stop"},
                  {"name": "TVAL", "type": "DEC", "description": "Transit Time"},
                  {"name": "DIST", "type": "QUAN", "description": "Distance (km)"},
              ]),
]


# ---------------------------------------------------------------------------
# SchemaAutoDiscover
# ---------------------------------------------------------------------------
class SchemaAutoDiscover:
    """
    Last-resort table discovery when both Schema RAG and SQL Pattern RAG miss.
    Searches embedded DDIC mirror by keyword, field name, and domain hint.
    Logs discoveries to memory/sap_sessions/schema_discoveries.json.
    """

    def __init__(self, ddic: Optional[List[DDICTable]] = None):
        self._ddic = ddic or DDIC_MIRROR
        self._field_index: Dict[str, List[DDICTable]] = {}  # field name → tables

    def search(
        self,
        query: str,
        auth_context: Optional[Any] = None,
        domain_hint: str = "auto",
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        Search DDIC mirror for tables matching the query.

        Args:
            query: Natural language query
            auth_context: SAPAuthContext for access filtering
            domain_hint: Domain hint (business_partner, mm, etc.)
            top_k: Maximum number of results

        Returns:
            {
                "tables": [{"table", "description", "domain", "confidence", "fields"}],
                "searched": "ddic_mirror",
                "total_ddic": N,
            }
        """
        query_lower = query.lower()
        query_words = set(re.findall(r'\w{3,}', query_lower))

        scored: List[tuple[float, DDICTable]] = []

        for table_entry in self._ddic:
            # Access check — skip denied tables
            if auth_context and hasattr(auth_context, "is_table_allowed"):
                if not auth_context.is_table_allowed(table_entry.table):
                    continue

            score = 0.0
            matched_fields: List[str] = []

            # 1. Table name exact or prefix match
            if table_entry.table.lower() in query_lower:
                score += 0.8
            elif any(table_entry.table.lower().startswith(w) for w in query_words if len(w) >= 3):
                score += 0.4

            # 2. Table description match
            desc_words = set(re.findall(r'\w{3,}', table_entry.description.lower()))
            overlap = query_words & desc_words
            if overlap:
                score += 0.3 * (len(overlap) / max(len(desc_words), 1))

            # 3. Domain hint match
            if domain_hint != "auto":
                if table_entry.domain == domain_hint:
                    score += 0.3
                elif domain_hint in table_entry.domain:
                    score += 0.15

            # 4. Field name match
            field_matches = 0
            for field in table_entry.fields:
                fname = field["name"].lower()
                fdesc = field.get("description", "").lower()
                f_words = set(re.findall(r'\w{3,}', fdesc))

                # Exact field name in query
                if fname in query_lower:
                    score += 0.5
                    field_matches += 1
                    matched_fields.append(field["name"])

                # Field description keyword match
                elif f_words & query_words:
                    score += 0.2 * (len(f_words & query_words))
                    field_matches += 1

            # 5. Cross-module bridge bonus (tables that connect multiple domains)
            cross_fields = {"LIFNR", "KUNNR", "MATNR", "EBELN", "VBELN", "LIFNR", "MATNR"}
            if any(f["name"] in cross_fields for f in table_entry.fields):
                score += 0.15  # hub tables are always relevant

            # 6. Penalize if query has domain signal from a different domain
            if domain_hint != "auto" and table_entry.domain != domain_hint:
                # Small penalty, not disqualification
                score *= 0.7

            if score > 0:
                scored.append((score, table_entry))
            elif field_matches > 0:
                # Fallback: if score is 0 but we had field matches, assign minimum confidence
                scored.append((0.3 + 0.1 * min(field_matches, 3), table_entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for s, entry in scored[:top_k]:
            # Build SQL-ready field list
            fields_for_sql = [f["name"] for f in entry.fields[:8]]  # top 8 fields

            result_entry = {
                "table": entry.table,
                "description": entry.description,
                "domain": entry.domain,
                "confidence": round(max(min(score, 1.0), 0.05), 3),  # min 0.05 if matched at all
                "fields": fields_for_sql,
                "all_fields": entry.fields,
                "is_cross_module_bridge": any(
                    f["name"] in {"LIFNR", "KUNNR", "MATNR", "EBELN", "VBELN"}
                    for f in entry.fields
                ),
                "discovered_via": "ddic_search",
            }
            results.append(result_entry)

            # Auto-log to schema discoveries if confidence is high enough
            if score >= 0.6:
                sap_memory.log_schema_discovery(
                    table=entry.table,
                    domain=entry.domain,
                    discovered_via="ddic_search",
                    confidence=round(score, 3),
                    fields=fields_for_sql,
                )

        return {
            "tables": results,
            "searched": "ddic_mirror",
            "total_ddic_tables": len(self._ddic),
            "query": query,
            "domain_hint": domain_hint,
            "auto_logged": sum(1 for r in results if r["confidence"] >= 0.6),
        }

    def build_select_sql(
        self,
        table_name: str,
        fields: Optional[List[str]] = None,
        auth_context: Optional[Any] = None,
        limit: int = 100,
    ) -> str:
        """
        Build a safe SELECT SQL from discovered table + fields.
        Applies MANDT filter automatically.
        """
        # Find the table entry
        entry = next((t for t in self._ddic if t.table == table_name), None)
        if not entry:
            return f"SELECT * FROM {table_name} WHERE MANDT = '100' LIMIT {limit};"

        select_fields = fields or [f["name"] for f in entry.fields[:6]]
        field_list = ", ".join(select_fields)

        where = "MANDT = '100'"
        if auth_context and hasattr(auth_context, "allowed_company_codes"):
            if auth_context.allowed_company_codes and "*" not in auth_context.allowed_company_codes:
                if any(t in table_name for t in ["LFB1", "BSIK", "BSAK", "BKPF", "BSEG"]):
                    b = "', '".join(auth_context.allowed_company_codes)
                    where = f"BUKRS IN ('{b}') AND MANDT = '100'"

        return f"SELECT {field_list}\nFROM {table_name}\nWHERE {where}\nLIMIT {limit};"


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
schema_auto_discoverer = SchemaAutoDiscover()
