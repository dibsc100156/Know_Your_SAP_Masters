-- init_schema.cql
-- ============================================================
-- Memgraph Init Script — SAP Enterprise Schema Graph (Know Your SAP Masters)
-- Generated: April 6, 2026
-- ============================================================
-- Load this via docker-compose volume mount:
--   ./docker/memgraph/init_schema.cql:/docker-entrypoint-initdb.d/01-schema.cql
--
-- Or run manually in Memgraph Lab:
--   Paste this entire file and execute.
-- ============================================================

-- ── 1. Create indexes (speed up label lookups) ──────────────────────────────
CREATE INDEX ON :SAPTable(table_name);
CREATE INDEX ON :SAPTable(module);
CREATE INDEX ON :SAPTable(domain);
CREATE INDEX ON :SAPTable(bridge);
CREATE INDEX ON :SAPTable(table);  -- legacy label for mg_networkx compat

-- ── 2. Material Master Nodes (MM) ───────────────────────────────────────────
MERGE (m:SAPTable {table_name:"MARA"}) SET m.module="MM", m.domain="material_master", m.description="General Material Data", m.key_columns=["MATNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MARC"}) SET m.module="MM", m.domain="material_master", m.description="Plant Data for Material", m.key_columns=["MATNR","WERKS"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MARD"}) SET m.module="MM", m.domain="material_master", m.description="Storage Location Data for Material", m.key_columns=["MATNR","WERKS","LGORT"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MBEW"}) SET m.module="MM", m.domain="material_master", m.description="Material Valuation", m.key_columns=["MATNR","BWKEY"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MAKT"}) SET m.module="MM", m.domain="material_master", m.description="Material Descriptions", m.key_columns=["MATNR","SPRAS"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MLGN"}) SET m.module="MM", m.domain="material_master", m.description="Material Data for Each Storage Location (WM)", m.key_columns=["MATNR","WERKS","LGORT"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MLGT"}) SET m.module="MM", m.domain="material_master", m.description="Material Data for Each Storage Type (WM)", m.key_columns=["MATNR","WERKS","LGORT","LGTYP"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MCH1"}) SET m.module="MM", m.domain="material_master", m.description="Batch Stock (Quantities)", m.key_columns=["MATNR","WERKS","LGORT","CHARG"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MCHA"}) SET m.module="MM", m.domain="material_master", m.description="Batch Master Record", m.key_columns=["MATNR","CHARG"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MSKA"}) SET m.module="MM", m.domain="material_master", m.description="Sales Order Stock", m.key_columns=["MATNR","WERKS","LGORT","KUNNU"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MSLB"}) SET m.module="MM", m.domain="material_master", m.description="Special Stock (Vendor-owned)", m.key_columns=["MATNR","WERKS","LGORT","LIFNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MKOL"}) SET m.module="MM", m.domain="material_master", m.description="Special Stock (Project-owned)", m.key_columns=["MATNR","WERKS","LGORT"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MVKE"}) SET m.module="MM", m.domain="material_master", m.description="Sales Data for Material", m.key_columns=["MATNR","VKORG","VTWEG"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MARM"}) SET m.module="MM", m.domain="material_master", m.description="Unit of Measure Data for Material", m.key_columns=["MATNR","MEINH"], m.bridge=false;

-- ── 3. Vendor / Business Partner Nodes (BP / MM-PUR / FI) ──────────────────
MERGE (m:SAPTable {table_name:"LFA1"}) SET m.module="BP", m.domain="business_partner", m.description="Vendor Master (General Section)", m.key_columns=["LIFNR"], m.bridge=true;
MERGE (m:SAPTable {table_name:"LFB1"}) SET m.module="FI", m.domain="business_partner", m.description="Vendor Master (Company Code Data)", m.key_columns=["LIFNR","BUKRS"], m.bridge=false;
MERGE (m:SAPTable {table_name:"LFBK"}) SET m.module="BP", m.domain="business_partner", m.description="Vendor Master (Bank Details)", m.key_columns=["LIFNR","BANKN"], m.bridge=false;
MERGE (m:SAPTable {table_name:"LFBW"}) SET m.module="MM", m.domain="purchasing", m.description="Vendor Evaluation Grades (Material/Plant)", m.key_columns=["LIFNR","MATNR","WERKS"], m.bridge=false;
MERGE (m:SAPTable {table_name:"EINA"}) SET m.module="MM-PUR", m.domain="purchasing", m.description="Purchasing Info Record: General Data", m.key_columns=["INFNR","LIFNR","MATNR"], m.bridge=true;
MERGE (m:SAPTable {table_name:"EINE"}) SET m.module="MM-PUR", m.domain="purchasing", m.description="Purchasing Info Record: Purchasing Organization Data", m.key_columns=["INFNR","EKORG","ESOKZ"], m.bridge=false;
MERGE (m:SAPTable {table_name:"EORD"}) SET m.module="MM-PUR", m.domain="purchasing", m.description="Source List (Vendor-Material-Plant)", m.key_columns=["LIFNR","MATNR","WERKS","ERNAM"], m.bridge=true;
MERGE (m:SAPTable {table_name:"EKKO"}) SET m.module="MM-PUR", m.domain="purchasing", m.description="Purchasing Document Header", m.key_columns=["EBELN"], m.bridge=true;
MERGE (m:SAPTable {table_name:"EKPO"}) SET m.module="MM-PUR", m.domain="purchasing", m.description="Purchasing Document Item", m.key_columns=["EBELN","EBELP"], m.bridge=false;
MERGE (m:SAPTable {table_name:"EKKN"}) SET m.module="MM-PUR", m.domain="purchasing", m.description="Account Assignment (Purchasing Document)", m.key_columns=["EBELN","EBELP","KTPNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"EKES"}) SET m.module="MM-PUR", m.domain="purchasing", m.description="Vendor Confirmations (Scheduling Agreements)", m.key_columns=["EBELN","EBELP","EBTYP"], m.bridge=false;

-- ── 4. Customer / Sales Nodes (SD / BP) ─────────────────────────────────────
MERGE (m:SAPTable {table_name:"KNA1"}) SET m.module="SD", m.domain="sales_distribution", m.description="Customer Master (General Data)", m.key_columns=["KUNNR"], m.bridge=true;
MERGE (m:SAPTable {table_name:"KNB1"}) SET m.module="FI", m.domain="sales_distribution", m.description="Customer Master (Company Code Data)", m.key_columns=["KUNNR","BUKRS"], m.bridge=false;
MERGE (m:SAPTable {table_name:"KNVV"}) SET m.module="SD", m.domain="sales_distribution", m.description="Customer Master (Sales Area Data)", m.key_columns=["KUNNR","VKORG","VTWEG","SPART"], m.bridge=false;
MERGE (m:SAPTable {table_name:"KNVK"}) SET m.module="SD", m.domain="customer_service", m.description="Customer Master Contact Relationships", m.key_columns=["KUNNR","PARZA"], m.bridge=false;
MERGE (m:SAPTable {table_name:"ADRC"}) SET m.module="BP", m.domain="business_partner", m.description="Business Address Services (Central Address Mgmt)", m.key_columns=["ADDRNUMBER","PERSNUMBER"], m.bridge=true;
MERGE (m:SAPTable {table_name:"VBAK"}) SET m.module="SD", m.domain="sales_distribution", m.description="Sales Document Header", m.key_columns=["VBELN"], m.bridge=false;
MERGE (m:SAPTable {table_name:"VBAP"}) SET m.module="SD", m.domain="sales_distribution", m.description="Sales Document Item", m.key_columns=["VBELN","POSNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"VBEP"}) SET m.module="SD", m.domain="sales_distribution", m.description="Sales Document: Schedule Line", m.key_columns=["VBELN","POSNR","ETENR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"VBFA"}) SET m.module="SD", m.domain="sales_distribution", m.description="Sales Document Flow (Document Chain)", m.key_columns=["VBELV","POSNV","VBELN","POSNN"], m.bridge=false;
MERGE (m:SAPTable {table_name:"LIKP"}) SET m.module="SD", m.domain="sales_distribution", m.description="Delivery Document Header", m.key_columns=["VBELN"], m.bridge=false;
MERGE (m:SAPTable {table_name:"LIPS"}) SET m.module="SD", m.domain="sales_distribution", m.description="Delivery Document Item", m.key_columns=["VBELN","POSNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"VBRP"}) SET m.module="SD", m.domain="sales_distribution", m.description="Billing Document Item", m.key_columns=["VBELN","POSNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"VBRK"}) SET m.module="SD", m.domain="sales_distribution", m.description="Billing Document Header", m.key_columns=["VBELN"], m.bridge=false;
MERGE (m:SAPTable {table_name:"KONV"}) SET m.module="SD", m.domain="sales_distribution", m.description="Pricing Conditions (Communication)", m.key_columns=["KNUMV","KPOSN","STUNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"A003"}) SET m.module="SD", m.domain="sales_distribution", m.description="Condition Records: Tax (Customer-Material-Country)", m.key_columns=["KAPPL","KSCHL","VKORG","VTWEG","MATNR","LAND1"], m.bridge=false;

-- ── 5. Finance / Accounting Nodes (FI / CO) ──────────────────────────────────
MERGE (m:SAPTable {table_name:"BKPF"}) SET m.module="FI", m.domain="financial_accounting", m.description="Accounting Document Header", m.key_columns=["BELNR","GJAHR","BUKRS"], m.bridge=true;
MERGE (m:SAPTable {table_name:"BSEG"}) SET m.module="FI", m.domain="financial_accounting", m.description="Accounting Document Segment (Line Items)", m.key_columns=["BELNR","GJAHR","BUZEI","BUKRS"], m.bridge=true;
MERGE (m:SAPTable {table_name:"BSIK"}) SET m.module="FI", m.domain="financial_accounting", m.description="Accounting: Secondary Index for Vendors (Open Items)", m.key_columns=["LIFNR","BUKRS","BELNR","BUZEI"], m.bridge=false;
MERGE (m:SAPTable {table_name:"BSAK"}) SET m.module="FI", m.domain="financial_accounting", m.description="Accounting: Secondary Index for Vendors (Cleared Items)", m.key_columns=["LIFNR","BUKRS","BELNR","BUZEI"], m.bridge=false;
MERGE (m:SAPTable {table_name:"BSID"}) SET m.module="FI", m.domain="financial_accounting", m.description="Accounting: Secondary Index for Customers (Open Items)", m.key_columns=["KUNNR","BUKRS","BELNR","BUZEI"], m.bridge=false;
MERGE (m:SAPTable {table_name:"BSAD"}) SET m.module="FI", m.domain="financial_accounting", m.description="Accounting: Secondary Index for Customers (Cleared Items)", m.key_columns=["KUNNR","BUKRS","BELNR","BUZEI"], m.bridge=false;
MERGE (m:SAPTable {table_name:"BSAS"}) SET m.module="FI", m.domain="financial_accounting", m.description="Accounting: Secondary Index for G/L Accounts (Cleared Items)", m.key_columns=["HKONT","BUKRS","BELNR","BUZEI"], m.bridge=false;
MERGE (m:SAPTable {table_name:"SKA1"}) SET m.module="FI", m.domain="financial_accounting", m.description="G/L Account Master (Chart of Accounts)", m.key_columns=["SAKNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"SKB1"}) SET m.module="FI", m.domain="financial_accounting", m.description="G/L Account Master (Company Code)", m.key_columns=["SAKNR","BUKRS"], m.bridge=false;
MERGE (m:SAPTable {table_name:"T001"}) SET m.module="FI", m.domain="financial_accounting", m.description="Company Codes", m.key_columns=["BUKRS"], m.bridge=true;
MERGE (m:SAPTable {table_name:"T001W"}) SET m.module="MM", m.domain="material_master", m.description="Plants", m.key_columns=["WERKS"], m.bridge=true;
MERGE (m:SAPTable {table_name:"T024"}) SET m.module="MM-PUR", m.domain="purchasing", m.description="Purchasing Organizations", m.key_columns=["EKORG"], m.bridge=true;
MERGE (m:SAPTable {table_name:"T001L"}) SET m.module="MM", m.domain="warehouse_management", m.description="Storage Locations", m.key_columns=["WERKS","LGORT"], m.bridge=false;
MERGE (m:SAPTable {table_name:"T001K"}) SET m.module="FI", m.domain="financial_accounting", m.description="Valuation Area (Company Code or Plant Level)", m.key_columns=["BWKEY","BUKRS"], m.bridge=false;
MERGE (m:SAPTable {table_name:"T024E"}) SET m.module="MM-PUR", m.domain="purchasing", m.description="Purchasing Groups", m.key_columns=["EKGRP"], m.bridge=false;
MERGE (m:SAPTable {table_name:"T003"}) SET m.module="SD", m.domain="sales_distribution", m.description="Sales Document Types", m.key_columns=["AUART"], m.bridge=false;
MERGE (m:SAPTable {table_name:"TVAK"}) SET m.module="SD", m.domain="sales_distribution", m.description="Sales Document Types (Header)", m.key_columns=["AUART"], m.bridge=false;

-- ── 6. Quality Management Nodes (QM) ───────────────────────────────────────
MERGE (m:SAPTable {table_name:"QALS"}) SET m.module="QM", m.domain="quality_management", m.description="Inspection Lot Master", m.key_columns=["QALS","MANDT"], m.bridge=true;
MERGE (m:SAPTable {table_name:"QAVE"}) SET m.module="QM", m.domain="quality_management", m.description="Usage Decision (Inspection Characteristics)", m.key_columns=["QALS","QUNUM","QUPOS"], m.bridge=false;
MERGE (m:SAPTable {table_name:"QAMV"}) SET m.module="QM", m.domain="quality_management", m.description="Inspection History / Usage Decision Records", m.key_columns=["QALS","QUNUM"], m.bridge=false;
MERGE (m:SAPTable {table_name:"MAPL"}) SET m.module="QM", m.domain="quality_management", m.description="Assignment of Task Lists to Materials", m.key_columns=["WERKS","PLNTY","PLNNR","MATNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"PLMK"}) SET m.module="QM", m.domain="quality_management", m.description="Inspection Master Data (Task List - Characteristics)", m.key_columns=["PLNTY","PLNNR","PLNKN","KNNUM"], m.bridge=false;
MERGE (m:SAPTable {table_name:"PLPO"}) SET m.module="QM", m.domain="quality_management", m.description="Task List Operations / Process Steps", m.key_columns=["PLNTY","PLNNR","PLNKN","TOLERANCE_KEY"], m.bridge=false;

-- ── 7. Project System / Controlling Nodes (PS / CO) ─────────────────────────
MERGE (m:SAPTable {table_name:"PROJ"}) SET m.module="PS", m.domain="project_system", m.description="Project Definition", m.key_columns=["PSPNR"], m.bridge=true;
MERGE (m:SAPTable {table_name:"PRPS"}) SET m.module="PS", m.domain="project_system", m.description="Work Breakdown Structure (WBS) Element", m.key_columns=["PSPNR"], m.bridge=true;
MERGE (m:SAPTable {table_name:"AFVC"}) SET m.module="PS", m.domain="project_system", m.description="Activity at Work Center (Network Node)", m.key_columns=["NPLNR","POSNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"AFVV"}) SET m.module="PS", m.domain="project_system", m.description="Operation/Cost Data for Activities", m.key_columns=["NPLNR","POSNR","VORNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"CSKS"}) SET m.module="CO", m.domain="project_system", m.description="Cost Center Master", m.key_columns=["KOKRS","DATAB","DATBI","KOSTL"], m.bridge=true;
MERGE (m:SAPTable {table_name:"CSSL"}) SET m.module="CO", m.domain="project_system", m.description="Cost Center Group / Cost Element", m.key_columns=["KOKRS","DATAB","DATBI","KSTAR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"COSP"}) SET m.module="CO", m.domain="project_system", m.description="CO Object: Cost Totals (Actual)", m.key_columns=["OBJNR","GJAHR","PERBL"], m.bridge=true;
MERGE (m:SAPTable {table_name:"COSS"}) SET m.module="CO", m.domain="project_system", m.description="CO Object: Cost Totals (Plan)", m.key_columns=["OBJNR","GJAHR","PERBL"], m.bridge=true;
MERGE (m:SAPTable {table_name:"ANLA"}) SET m.module="FI", m.domain="real_estate", m.description="Asset Master Record (Investment Accounting)", m.key_columns=["ANLN1","BUKRS"], m.bridge=false;
MERGE (m:SAPTable {table_name:"ANEP"}) SET m.module="FI", m.domain="real_estate", m.description="Asset Accounting Document Line Items", m.key_columns=["ANLN1","BUKRS","AJAHR","BELNR","BUZEI"], m.bridge=false;

-- ── 8. Warehouse Management Nodes (WM) ──────────────────────────────────────
MERGE (m:SAPTable {table_name:"LEU4"}) SET m.module="WM", m.domain="warehouse_management", m.description="Transfer Order Header", m.key_columns=["TONUM"], m.bridge=false;
MERGE (m:SAPTable {table_name:"LTBP"}) SET m.module="WM", m.domain="warehouse_management", m.description="Transfer Order Item (Batch-managed)", m.key_columns=["TONUM","TQLFD"], m.bridge=false;
MERGE (m:SAPTable {table_name:"LQUA"}) SET m.module="WM", m.domain="warehouse_management", m.description="Quant (WM) — Physical Stock Record", m.key_columns=["MATNR","WERKS","LGORT","LENUM"], m.bridge=true;
MERGE (m:SAPTable {table_name:"LAGP"}) SET m.module="WM", m.domain="warehouse_management", m.description="Storage Type (Warehouse Management)", m.key_columns=["WERKS","LGTYP"], m.bridge=false;
MERGE (m:SAPTable {table_name:"LDCP"}) SET m.module="WM", m.domain="warehouse_management", m.description="Storage Bin (Warehouse Management)", m.key_columns=["WERKS","LGTYP","LGPLA"], m.bridge=false;

-- ── 9. Transportation / Logistics Nodes (TM) ──────────────────────────────
MERGE (m:SAPTable {table_name:"VTTK"}) SET m.module="TM", m.domain="transportation", m.description="Transportation Order / Shipment Header", m.key_columns=["TKNUM"], m.bridge=true;
MERGE (m:SAPTable {table_name:"VTLP"}) SET m.module="TM", m.domain="transportation", m.description="Transportation Order / Shipment Leg", m.key_columns=["TKNUM","TPLNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"VTFA"}) SET m.module="TM", m.domain="transportation", m.description="Transportation Order / Shipment Stage", m.key_columns=["TKNUM","TDFORMAT"], m.bridge=false;

-- ── 10. Customer Service / PM Nodes (CS / PM) ──────────────────────────────
MERGE (m:SAPTable {table_name:"ASMD"}) SET m.module="CS", m.domain="customer_service", m.description="Service Order / Service Notification", m.key_columns=["QMNUM","ITEAM"], m.bridge=false;
MERGE (m:SAPTable {table_name:"IHPA"}) SET m.module="CS", m.domain="customer_service", m.description="Business Partner Relationships (for Service)", m.key_columns=["OBJNR","PARVW","PARNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"DRAD"}) SET m.module="CS", m.domain="customer_service", m.description="Document-Item Assignment (GOS attachments)", m.key_columns=["RADBNR","DOKNR","DOKAR","DOKTL","DOKOB"], m.bridge=false;
MERGE (m:SAPTable {table_name:"IHK6"}) SET m.module="PM", m.domain="customer_service", m.description="Equipment Master Record (Functional Location/Tech Obj)", m.key_columns=["EQUNR","TPLNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"EQUI"}) SET m.module="PM", m.domain="customer_service", m.description="Equipment Master Data", m.key_columns=["EQUNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"IFLOT"}) SET m.module="PM", m.domain="customer_service", m.description="Fleet / Technical Object Master", m.key_columns=["OBJNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"ILOA"}) SET m.module="PM", m.domain="customer_service", m.description="Technical Object Location / Address Assignment", m.key_columns=["ILOAN","ADRNR"], m.bridge=false;

-- ── 11. Business Partner Central Master (BUT000) ────────────────────────────
MERGE (m:SAPTable {table_name:"BUT000"}) SET m.module="BP", m.domain="business_partner", m.description="Business Partner: General Data I (Central BP Master)", m.key_columns=["PARTNER"], m.bridge=true;
MERGE (m:SAPTable {table_name:"BUT020"}) SET m.module="BP", m.domain="business_partner", m.description="Business Partner: Address Management", m.key_columns=["PARTNER","ADDRNUMBER"], m.bridge=false;
MERGE (m:SAPTable {table_name:"BUT050"}) SET m.module="BP", m.domain="business_partner", m.description="Business Partner: Customer/Vendor Link (Role Relationships)", m.key_columns=["PARTNER","RELATION","PARTNER2"], m.bridge=false;

-- ── 12. Industry Solutions & Additional Domains ──────────────────────────────
-- HR
MERGE (m:SAPTable {table_name:"PA0001"}) SET m.module="HR", m.domain="human_resources", m.description="HR Master Record: Organization Assignment", m.key_columns=["PERNR","ORGEH","PLANS","STELL"], m.bridge=false;
MERGE (m:SAPTable {table_name:"PA0008"}) SET m.module="HR", m.domain="human_resources", m.description="HR Master Record: Pay / Wage Type", m.key_columns=["PERNR","FPFAS"], m.bridge=false;
-- India Tax
MERGE (m:SAPTable {table_name:"J_1IG_HSN_SAC"}) SET m.module="TAX", m.domain="taxation_india", m.description="India: HSN Codes for Materials / SAC Codes for Services", m.key_columns=["STEGR","SUBSTCODE"], m.bridge=false;
MERGE (m:SAPTable {table_name:"J_1BBRANCH"}) SET m.module="TAX", m.domain="taxation_india", m.description="India: Branch/Plant Registration for GST", m.key_columns=["BUKRS","BRANCH"], m.bridge=false;
-- Real Estate
MERGE (m:SAPTable {table_name:"VIMONI"}) SET m.module="RE", m.domain="real_estate", m.description="Real Estate Contract / Rent Index", m.key_columns=["VKONT"], m.bridge=false;
MERGE (m:SAPTable {table_name:"VIBDT"}) SET m.module="RE", m.domain="real_estate", m.description="Real Estate Business Partner Link", m.key_columns=["KUNNR","LAND1","STCEG"], m.bridge=false;
-- GTS
MERGE (m:SAPTable {table_name:"/SAPSLL/POD"}) SET m.module="GTS", m.domain="gts", m.description="GTS: Proof of Delivery / Export Control", m.key_columns=["PODHANDLE"], m.bridge=false;
MERGE (m:SAPTable {table_name:"/SAPSLL/PNTPR"}) SET m.module="GTS", m.domain="gts", m.description="GTS: Partner Master Data (Trade Compliance)", m.key_columns=["PARNR","PARKZ"], m.bridge=false;
-- IS-OIL
MERGE (m:SAPTable {table_name:"OIB_A04"}) SET m.module="IS-OIL", m.domain="is_oil", m.description="Oil & Gas: Tank Farm / Storage Location Data", m.key_columns=["TPLNR","TATYP"], m.bridge=false;
MERGE (m:SAPTable {table_name:"OIG_V"}) SET m.module="IS-OIL", m.domain="is_oil", m.description="Oil & Gas: Volume / Measurement Data", m.key_columns=["OIBNR","VPRGSNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"T8JV"}) SET m.module="IS-OIL", m.domain="is_oil", m.description="Oil & Gas: Joint Venture Partner Codes", m.key_columns=["JVCD"], m.bridge=false;
-- IS-Utilities
MERGE (m:SAPTable {table_name:"EVBS"}) SET m.module="IS-UTILITY", m.domain="is_utilities", m.description="Utilities: Device Installation (Field Service)", m.key_columns=["GERNR","ANLAGE"], m.bridge=false;
MERGE (m:SAPTable {table_name:"EANL"}) SET m.module="IS-UTILITY", m.domain="is_utilities", m.description="Utilities: Equipment Master (Installation Point)", m.key_columns=["ANLAGE","EQUNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"EGERR"}) SET m.module="IS-UTILITY", m.domain="is_utilities", m.description="Utilities: Device Register / Error Register", m.key_columns=["FEGRP","FETYP","FENUM"], m.bridge=false;
-- IS-Retail
MERGE (m:SAPTable {table_name:"WRS1"}) SET m.module="IS-RETAIL", m.domain="is_retail", m.description="Retail: Replenishment Proposal / Buying Line", m.key_columns=["BWONNR","EPOID"], m.bridge=false;
MERGE (m:SAPTable {table_name:"SETY"}) SET m.module="IS-RETAIL", m.domain="is_retail", m.description="Retail: Assortment Module / Range Planning", m.key_columns=["SRTID","SETID"], m.bridge=false;
-- IS-Health
MERGE (m:SAPTable {table_name:"NPAT"}) SET m.module="IS-HEALTH", m.domain="is_health", m.description="Healthcare: Patient Master / Coverage", m.key_columns=["PATNR","SUBJNR"], m.bridge=false;
MERGE (m:SAPTable {table_name:"NBEW"}) SET m.module="IS-HEALTH", m.domain="is_health", m.description="Healthcare: Care Beneficiary (Insurance/Billing)", m.key_columns=["PATNR","VKONT"], m.bridge=false;
MERGE (m:SAPTable {table_name:"NPNZ"}) SET m.module="IS-HEALTH", m.domain="is_health", m.description="Healthcare: Care Plan / Care Activity Records", m.key_columns=["NPANR","PPNVP"], m.bridge=false;
-- Variant Configuration
MERGE (m:SAPTable {table_name:"CABN"}) SET m.module="LO-VC", m.domain="variant_configuration", m.description="Configuration: Characteristic (Feature) Master", m.key_columns=["ATINN","ATZHL"], m.bridge=false;
MERGE (m:SAPTable {table_name:"KLAH"}) SET m.module="LO-VC", m.domain="variant_configuration", m.description="Configuration: Class Master (Product Class)", m.key_columns=["CLINT","KLART"], m.bridge=false;
MERGE (m:SAPTable {table_name:"CUOBJ"}) SET m.module="LO-VC", m.domain="variant_configuration", m.description="Configuration: Configuration (Internal Object Key)", m.key_columns=["CUOBJ","CLINT"], m.bridge=false;
MERGE (m:SAPTable {table_name:"INOB"}) SET m.module="LO-VC", m.domain="variant_configuration", m.description="Allocation: Material to Configuration (Long Text)", m.key_columns=["OBJEK","OBTYP"], m.bridge=false;

-- ── 13. FK Relationships — Material Master (Internal) ───────────────────────
MATCH (a:SAPTable {table_name:"MARA"}), (b:SAPTable {table_name:"MARC"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARA.MATNR = MARC.MATNR", cardinality:"1:N", bridge_type:"internal", notes:"Material → Plant-specific data"}]->(b);
MATCH (a:SAPTable {table_name:"MARA"}), (b:SAPTable {table_name:"MAKT"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARA.MATNR = MAKT.MATNR AND MAKT.SPRAS = 'E'", cardinality:"1:N", bridge_type:"internal", notes:"Material → Description (English)"}]->(b);
MATCH (a:SAPTable {table_name:"MARA"}), (b:SAPTable {table_name:"MARM"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARA.MATNR = MARM.MATNR", cardinality:"1:N", bridge_type:"internal", notes:"Material → Alternate UoM conversions"}]->(b);
MATCH (a:SAPTable {table_name:"MARC"}), (b:SAPTable {table_name:"MARD"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARC.MATNR = MARD.MATNR AND MARC.WERKS = MARD.WERKS", cardinality:"1:N", bridge_type:"internal", notes:"Material-Plant → Storage Location stock"}]->(b);
MATCH (a:SAPTable {table_name:"MARC"}), (b:SAPTable {table_name:"MBEW"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARC.MATNR = MBEW.MATNR AND MARC.WERKS = MBEW.BWKEY", cardinality:"1:N", bridge_type:"internal", notes:"Material-Plant → Valuation (BWKEY maps to WERKS)"}]->(b);
MATCH (a:SAPTable {table_name:"MARC"}), (b:SAPTable {table_name:"MVKE"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARC.MATNR = MVKE.MATNR", cardinality:"1:N", bridge_type:"internal", notes:"Material → Sales organization sales data"}]->(b);
MATCH (a:SAPTable {table_name:"MARD"}), (b:SAPTable {table_name:"MLGN"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARD.MATNR = MLGN.MATNR AND MARD.WERKS = MLGN.WERKS AND MARD.LGORT = MLGN.LGORT", cardinality:"1:N", bridge_type:"internal", notes:"Storage Location → WM storage-type view"}]->(b);
MATCH (a:SAPTable {table_name:"MLGN"}), (b:SAPTable {table_name:"MLGT"}) MERGE (a)-[:FOREIGN_KEY {condition:"MLGN.MATNR = MLGT.MATNR AND MLGN.WERKS = MLGT.WERKS AND MLGN.LGORT = MLGT.LGORT AND MLGN.LGTYP = MLGT.LGTYP", cardinality:"1:N", bridge_type:"internal", notes:"Storage Type → WM storage-bin view"}]->(b);
MATCH (a:SAPTable {table_name:"MARD"}), (b:SAPTable {table_name:"LQUA"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARD.MATNR = LQUA.MATNR AND MARD.WERKS = LQUA.WERKS AND MARD.LGORT = LQUA.LGORT", cardinality:"1:N", bridge_type:"internal", notes:"Storage Location → WM Quant (physical stock)"}]->(b);
MATCH (a:SAPTable {table_name:"MCHA"}), (b:SAPTable {table_name:"MCH1"}) MERGE (a)-[:FOREIGN_KEY {condition:"MCHA.MATNR = MCH1.MATNR AND MCHA.CHARG = MCH1.CHARG", cardinality:"1:N", bridge_type:"internal", notes:"Batch master → Batch stock quantities"}]->(b);
MATCH (a:SAPTable {table_name:"MCHA"}), (b:SAPTable {table_name:"QALS"}) MERGE (a)-[:FOREIGN_KEY {condition:"MCHA.MATNR = QALS.MATNR AND MCHA.CHARG = QALS.CHARG", cardinality:"1:N", bridge_type:"internal", notes:"Batch → QM Inspection Lot by batch"}]->(b);
MATCH (a:SAPTable {table_name:"MARC"}), (b:SAPTable {table_name:"MAPL"}) MERGE (a)-[:FOREIGN_KEY {condition:"MARC.MATNR = MAPL.MATNR AND MARC.WERKS = MAPL.WERKS", cardinality:"1:N", bridge_type:"internal", notes:"Material-Plant → QM task list assignment"}]->(b);
MATCH (a:SAPTable {table_name:"MAPL"}), (b:SAPTable {table_name:"PLMK"}) MERGE (a)-[:FOREIGN_KEY {condition:"MAPL.PLNTY = PLMK.PLNTY AND MAPL.PLNNR = PLMK.PLNNR AND MAPL.PLNKN = PLMK.PLNKN", cardinality:"1:N", bridge_type:"internal", notes:"Task List Assignment → QM Inspection Characteristics"}]->(b);
MATCH (a:SAPTable {table_name:"PLMK"}), (b:SAPTable {table_name:"PLPO"}) MERGE (a)-[:FOREIGN_KEY {condition:"PLMK.PLNTY = PLPO.PLNTY AND PLMK.PLNNR = PLPO.PLNNR AND PLMK.PLNKN = PLPO.PLNKN", cardinality:"1:N", bridge_type:"internal", notes:"QM Characteristics → Operations/Process Steps"}]->(b);
MATCH (a:SAPTable {table_name:"QALS"}), (b:SAPTable {table_name:"QAVE"}) MERGE (a)-[:FOREIGN_KEY {condition:"QALS.QALS = QAVE.QALS AND QALS.QUNUM = QAVE.QUNUM", cardinality:"1:1", bridge_type:"internal", notes:"Inspection Lot → Usage Decision"}]->(b);

-- ── 14. FK Relationships — Vendor / Purchasing ────────────────────────────────
MATCH (a:SAPTable {table_name:"LFA1"}), (b:SAPTable {table_name:"LFB1"}) MERGE (a)-[:FOREIGN_KEY {condition:"LFA1.LIFNR = LFB1.LIFNR", cardinality:"1:1", bridge_type:"internal", notes:"Vendor general → Company-code data"}]->(b);
MATCH (a:SAPTable {table_name:"LFA1"}), (b:SAPTable {table_name:"LFBK"}) MERGE (a)-[:FOREIGN_KEY {condition:"LFA1.LIFNR = LFBK.LIFNR", cardinality:"1:N", bridge_type:"internal", notes:"Vendor → Bank details"}]->(b);
MATCH (a:SAPTable {table_name:"LFA1"}), (b:SAPTable {table_name:"EINA"}) MERGE (a)-[:FOREIGN_KEY {condition:"LFA1.LIFNR = EINA.LIFNR", cardinality:"1:N", bridge_type:"cross_module", notes:"Vendor → Purchasing Info Records"}]->(b);
MATCH (a:SAPTable {table_name:"EINA"}), (b:SAPTable {table_name:"EINE"}) MERGE (a)-[:FOREIGN_KEY {condition:"EINA.INFNR = EINE.INFNR AND EINA.LIFNR = EINE.LIFNR AND EINA.EKORG = EINE.EKORG", cardinality:"1:1", bridge_type:"internal", notes:"Info Record (General) → Purchasing Org data"}]->(b);
MATCH (a:SAPTable {table_name:"EINA"}), (b:SAPTable {table_name:"EORD"}) MERGE (a)-[:FOREIGN_KEY {condition:"EINA.LIFNR = EORD.LIFNR AND EINA.MATNR = EORD.MATNR", cardinality:"1:N", bridge_type:"cross_module", notes:"Info Record → Source List (by vendor-material)"}]->(b);
MATCH (a:SAPTable {table_name:"EKKO"}), (b:SAPTable {table_name:"EKPO"}) MERGE (a)-[:FOREIGN_KEY {condition:"EKKO.EBELN = EKPO.EBELN", cardinality:"1:N", bridge_type:"internal", notes:"PO Header → PO Items"}]->(b);
MATCH (a:SAPTable {table_name:"EKPO"}), (b:SAPTable {table_name:"EKKN"}) MERGE (a)-[:FOREIGN_KEY {condition:"EKPO.EBELN = EKKN.EBELN AND EKPO.EBELP = EKKN.EBELP", cardinality:"1:N", bridge_type:"internal", notes:"PO Item → Account Assignment"}]->(b);
MATCH (a:SAPTable {table_name:"EKKO"}), (b:SAPTable {table_name:"EKES"}) MERGE (a)-[:FOREIGN_KEY {condition:"EKKO.EBELN = EKES.EBELN AND EKKO.LIFNR = EKES.LIFNR", cardinality:"1:N", bridge_type:"internal", notes:"PO Header → Vendor Confirmations (scheduling agmt)"}]->(b);

-- ── 15. Cross-Module Bridges (Sample — extend from graph_store.py) ──────────
-- These are the high-value cross-module paths that Graph RAG solves
MATCH (a:SAPTable {table_name:"EINA"}), (b:SAPTable {table_name:"MARA"}) MERGE (a)-[:FOREIGN_KEY {condition:"EINA.MATNR = MARA.MATNR", cardinality:"N:1", bridge_type:"cross_module", notes:"Purchasing Info Record → Material master"}]->(b);
MATCH (a:SAPTable {table_name:"EKPO"}), (b:SAPTable {table_name:"MARA"}) MERGE (a)-[:FOREIGN_KEY {condition:"EKPO.MATNR = MARA.MATNR", cardinality:"N:1", bridge_type:"cross_module", notes:"PO Item → Material"}]->(b);
MATCH (a:SAPTable {table_name:"EKKO"}), (b:SAPTable {table_name:"LFA1"}) MERGE (a)-[:FOREIGN_KEY {condition:"EKKO.LIFNR = LFA1.LIFNR", cardinality:"N:1", bridge_type:"cross_module", notes:"PO Header → Vendor master"}]->(b);
MATCH (a:SAPTable {table_name:"VBAP"}), (b:SAPTable {table_name:"MARA"}) MERGE (a)-[:FOREIGN_KEY {condition:"VBAP.MATNR = MARA.MATNR", cardinality:"N:1", bridge_type:"cross_module", notes:"Sales Order Item → Material"}]->(b);
MATCH (a:SAPTable {table_name:"VBAK"}), (b:SAPTable {table_name:"KNA1"}) MERGE (a)-[:FOREIGN_KEY {condition:"VBAK.KUNNR = KNA1.KUNNR", cardinality:"N:1", bridge_type:"cross_module", notes:"Sales Order → Customer master"}]->(b);
MATCH (a:SAPTable {table_name:"BSEG"}), (b:SAPTable {table_name:"LFA1"}) MERGE (a)-[:FOREIGN_KEY {condition:"BSEG.LIFNR = LFA1.LIFNR", cardinality:"N:1", bridge_type:"cross_module", notes:"FI Line Item → Vendor (vendor invoices)"}]->(b);
MATCH (a:SAPTable {table_name:"QALS"}), (b:SAPTable {table_name:"MARA"}) MERGE (a)-[:FOREIGN_KEY {condition:"QALS.MATNR = MARA.MATNR", cardinality:"N:1", bridge_type:"cross_module", notes:"Inspection Lot → Material"}]->(b);
MATCH (a:SAPTable {table_name:"LQUA"}), (b:SAPTable {table_name:"MARA"}) MERGE (a)-[:FOREIGN_KEY {condition:"LQUA.MATNR = MARA.MATNR", cardinality:"N:1", bridge_type:"cross_module", notes:"WM Quant → Material"}]->(b);
MATCH (a:SAPTable {table_name:"VBRK"}), (b:SAPTable {table_name:"BKPF"}) MERGE (a)-[:FOREIGN_KEY {condition:"VBRK.BELNR = BKPF.BELNR AND VBRK.FKIMG > 0", cardinality:"N:1", bridge_type:"cross_module", notes:"Billing Document → FI Accounting Document"}]->(b);
MATCH (a:SAPTable {table_name:"BUT000"}), (b:SAPTable {table_name:"LFA1"}) MERGE (a)-[:FOREIGN_KEY {condition:"BUT000.PARTNER = LFA1.LIFNR", cardinality:"1:1", bridge_type:"cross_module", notes:"BP Central Master → Vendor (CVI link)"}]->(b);
MATCH (a:SAPTable {table_name:"BUT000"}), (b:SAPTable {table_name:"KNA1"}) MERGE (a)-[:FOREIGN_KEY {condition:"BUT000.PARTNER = KNA1.KUNNR", cardinality:"1:1", bridge_type:"cross_module", notes:"BP Central Master → Customer (CVI link)"}]->(b);
MATCH (a:SAPTable {table_name:"BUT000"}), (b:SAPTable {table_name:"BUT020"}) MERGE (a)-[:FOREIGN_KEY {condition:"BUT000.PARTNER = BUT020.PARTNER", cardinality:"1:N", bridge_type:"cross_module", notes:"BP → BP Address"}]->(b);
MATCH (a:SAPTable {table_name:"BUT020"}), (b:SAPTable {table_name:"ADRC"}) MERGE (a)-[:FOREIGN_KEY {condition:"BUT020.ADDRNUMBER = ADRC.ADDRNUMBER", cardinality:"N:1", bridge_type:"cross_module", notes:"BP Address → Central Address Management"}]->(b);
MATCH (a:SAPTable {table_name:"LFA1"}), (b:SAPTable {table_name:"ADRC"}) MERGE (a)-[:FOREIGN_KEY {condition:"LFA1.ADRNR = ADRC.ADDRNUMBER", cardinality:"N:1", bridge_type:"cross_module", notes:"Vendor → Central Address"}]->(b);
MATCH (a:SAPTable {table_name:"KNA1"}), (b:SAPTable {table_name:"ADRC"}) MERGE (a)-[:FOREIGN_KEY {condition:"KNA1.ADRNR = ADRC.ADDRNUMBER", cardinality:"N:1", bridge_type:"cross_module", notes:"Customer → Central Address"}]->(b);
MATCH (a:SAPTable {table_name:"LIKP"}), (b:SAPTable {table_name:"VTTK"}) MERGE (a)-[:FOREIGN_KEY {condition:"LIKP.TKNUM = VTTK.TKNUM", cardinality:"N:1", bridge_type:"cross_module", notes:"Delivery → Transportation Order (TM integration)"}]->(b);
MATCH (a:SAPTable {table_name:"BKPF"}), (b:SAPTable {table_name:"BSEG"}) MERGE (a)-[:FOREIGN_KEY {condition:"BKPF.BELNR = BSEG.BELNR AND BKPF.GJAHR = BSEG.GJAHR AND BKPF.BUKRS = BSEG.BUKRS", cardinality:"1:N", bridge_type:"internal", notes:"FI Document Header → Line Items"}]->(b);
MATCH (a:SAPTable {table_name:"BSEG"}), (b:SAPTable {table_name:"BSIK"}) MERGE (a)-[:FOREIGN_KEY {condition:"BSEG.BELNR = BSIK.BELNR AND BSEG.GJAHR = BSIK.GJAHR AND BSEG.BUKRS = BSIK.BUKRS AND BSEG.BUZEI = BSIK.BUZEI", cardinality:"1:1", bridge_type:"internal", notes:"FI Line Item → Vendor Open Items index"}]->(b);
MATCH (a:SAPTable {table_name:"BSEG"}), (b:SAPTable {table_name:"BSAK"}) MERGE (a)-[:FOREIGN_KEY {condition:"BSEG.BELNR = BSAK.BELNR AND BSEG.GJAHR = BSAK.GJAHR AND BSEG.BUKRS = BSAK.BUKRS AND BSEG.BUZEI = BSAK.BUZEI", cardinality:"1:1", bridge_type:"internal", notes:"FI Line Item → Vendor Cleared Items index"}]->(b);
MATCH (a:SAPTable {table_name:"VBAK"}), (b:SAPTable {table_name:"LIKP"}) MERGE (a)-[:FOREIGN_KEY {condition:"VBAK.VBELN = LIKP.VGBEL AND LIKP.VGTYP = 'C'", cardinality:"1:N", bridge_type:"cross_module", notes:"Sales Order → Outbound Delivery (via reference)"}]->(b);
MATCH (a:SAPTable {table_name:"LIKP"}), (b:SAPTable {table_name:"LIPS"}) MERGE (a)-[:FOREIGN_KEY {condition:"LIKP.VBELN = LIPS.VBELN", cardinality:"1:N", bridge_type:"internal", notes:"Delivery Header → Delivery Items"}]->(b);
MATCH (a:SAPTable {table_name:"PRPS"}), (b:SAPTable {table_name:"PROJ"}) MERGE (a)-[:FOREIGN_KEY {condition:"PRPS.PSPHI = PROJ.PSPNR", cardinality:"N:1", bridge_type:"cross_module", notes:"WBS Element → Project Definition"}]->(b);
MATCH (a:SAPTable {table_name:"COSP"}), (b:SAPTable {table_name:"PRPS"}) MERGE (a)-[:FOREIGN_KEY {condition:"COSP.OBJNR = PRPS.OBJNR", cardinality:"N:1", bridge_type:"cross_module", notes:"CO Actual Costs → WBS Element"}]->(b);
MATCH (a:SAPTable {table_name:"ANLA"}), (b:SAPTable {table_name:"T001"}) MERGE (a)-[:FOREIGN_KEY {condition:"ANLA.BUKRS = T001.BUKRS", cardinality:"N:1", bridge_type:"cross_module", notes:"Asset Master → Company Code"}]->(b);

-- ── 16. Compute and store structural properties ──────────────────────────────
-- After all nodes and edges are loaded, compute centrality in Memgraph Lab or Python:
--
-- FROM Memgraph Lab Console:
--   MATCH (t:SAPTable)
--   WITH collect(t) AS tables
--   UNWIND tables AS t1
--   UNWIND tables AS t2
--   WITH t1, t2, tables
--   WHERE t1 <> t2 AND (t1)-[:FOREIGN_KEY*]->(t2)
--   WITH t1, count(*) AS outDeg
--   SET t1.degree_centrality = outDeg
--
-- Or via Python after loading:
--   graph.compute_centrality()   # ← from memgraph_adapter.py

-- ── Verify ────────────────────────────────────────────────────────────────────
RETURN 'SAP Masters graph loaded: ' + 
       toString(count{(:SAPTable)}) + ' nodes, ' + 
       toString(count{(a)-[:FOREIGN_KEY]->(b)}) + ' edges' AS status;
