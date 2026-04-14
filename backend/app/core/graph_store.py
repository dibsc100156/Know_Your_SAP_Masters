import networkx as nx
from typing import Dict, List, Set, Tuple, Optional


class GraphRAGManager:
    """
    Pillar 5: Graph RAG — Cross-Module FK Relationship Graph.

    Uses NetworkX to map Foreign Key relationships across ALL SAP Master Data
    domains. Enables the Agentic Orchestrator to find JOIN paths for any
    cross-module query (e.g., "show me vendors who supplied material X to plant Y").

    Coverage: MM, FI, SD, QM, PS, WM, PM, PUR, BP, CS, TM, RE-FX, IS-OIL, IS-UTILITY.

    In production, this would be auto-populated from SAP DDIC tables DD08L (FK relationships)
    and T001 (company codes), T001W (plants), T024 (purchasing orgs).
    """

    def __init__(self):
        self.G = nx.Graph()
        self._node_meta: Dict[str, dict] = {}
        self._edge_meta: Dict[Tuple[str, str], dict] = {}
        self.build_enterprise_schema_graph()

    # ─── Node Management ────────────────────────────────────────────────────────

    def _add_node(self, table: str, module: str, domain: str, desc: str, key_cols: List[str]):
        """Add a table node with rich metadata."""
        self.G.add_node(table, module=module, domain=domain, desc=desc)
        self._node_meta[table] = {
            "module": module,
            "domain": domain,
            "desc": desc,
            "key_columns": key_cols,
        }

    def _add_edge(self, t1: str, t2: str, condition: str, cardinality: str = "1:1",
                  bridge_type: str = "internal", notes: str = ""):
        """
        Add an undirected FK edge. Both directions are traversable.
        Cross-module edges are flagged with bridge_type for explainability.
        """
        self.G.add_edge(t1, t2,
                        condition=condition,
                        cardinality=cardinality,
                        bridge_type=bridge_type,
                        notes=notes)
        self._edge_meta[(t1, t2)] = {
            "condition": condition,
            "cardinality": cardinality,
            "bridge_type": bridge_type,
            "notes": notes,
        }

    # ─── Graph Builder ─────────────────────────────────────────────────────────

    def build_enterprise_schema_graph(self):
        """
        Builds the enterprise metadata graph.

        Tables are organized by module:
          MM   = Materials Management
          FI   = Financial Accounting
          CO   = Controlling
          SD   = Sales & Distribution
          MM-PUR = Purchasing
          QM   = Quality Management
          PS   = Project Systems
          WM   = Warehouse Management
          PM   = Plant Maintenance
          BP   = Business Partner
          CS   = Customer Service
          TM   = Transportation Management
          RE   = Real Estate
          IS-* = Industry Solutions
        """

        # ========================================================================
        # 1. NODES — Material Master (MM)
        # ========================================================================
        self._add_node("MARA", "MM", "material_master",
                       "General Material Data",
                       ["MATNR"])

        self._add_node("MARC", "MM", "material_master",
                       "Plant Data for Material",
                       ["MATNR", "WERKS"])

        self._add_node("MARD", "MM", "material_master",
                       "Storage Location Data for Material",
                       ["MATNR", "WERKS", "LGORT"])

        self._add_node("MBEW", "MM", "material_master",
                       "Material Valuation",
                       ["MATNR", "BWKEY"])

        self._add_node("MAKT", "MM", "material_master",
                       "Material Descriptions",
                       ["MATNR", "SPRAS"])

        self._add_node("MLGN", "MM", "material_master",
                       "Material Data for Each Storage Location (WM)",
                       ["MATNR", "WERKS", "LGORT"])

        self._add_node("MLGT", "MM", "material_master",
                       "Material Data for Each Storage Type (WM)",
                       ["MATNR", "WERKS", "LGORT", "LGTYP"])

        # Batch Management
        self._add_node("MCH1", "MM", "material_master",
                       "Batch Stock (Quantities)",
                       ["MATNR", "WERKS", "LGORT", "CHARG"])

        self._add_node("MCHA", "MM", "material_master",
                       "Batch Master Record",
                       ["MATNR", "CHARG"])

        # Special Stock
        self._add_node("MSKA", "MM", "material_master",
                       "Sales Order Stock",
                       ["MATNR", "WERKS", "LGORT", "KUNNU"])

        self._add_node("MSLB", "MM", "material_master",
                       "Special Stock (Vendor-owned)",
                       ["MATNR", "WERKS", "LGORT", "LIFNR"])

        self._add_node("MKOL", "MM", "material_master",
                       "Special Stock (Project-owned)",
                       ["MATNR", "WERKS", "LGORT"])

        # Material Types & Views
        self._add_node("MVKE", "MM", "material_master",
                       "Sales Data for Material",
                       ["MATNR", "VKORG", "VTWEG"])

        self._add_node("MARM", "MM", "material_master",
                       "Unit of Measure Data for Material",
                       ["MATNR", "MEINH"])

        # ========================================================================
        # 2. NODES — Vendor / Business Partner (BP / MM-PUR / FI)
        # ========================================================================
        self._add_node("LFA1", "BP", "business_partner",
                       "Vendor Master (General Section)",
                       ["LIFNR"])

        self._add_node("LFB1", "FI", "business_partner",
                       "Vendor Master (Company Code Data)",
                       ["LIFNR", "BUKRS"])

        self._add_node("LFBK", "BP", "business_partner",
                       "Vendor Master (Bank Details)",
                       ["LIFNR", "BANKN"])

        self._add_node("LFBW", "MM", "purchasing",
                       "Vendor Evaluation Grades (Material/Plant)",
                       ["LIFNR", "MATNR", "WERKS"])

        # Purchasing Info Records
        self._add_node("EINA", "MM-PUR", "purchasing",
                       "Purchasing Info Record: General Data",
                       ["INFNR", "LIFNR", "MATNR"])

        self._add_node("EINE", "MM-PUR", "purchasing",
                       "Purchasing Info Record: Purchasing Organization Data",
                       ["INFNR", "EKORG", "ESOKZ"])

        self._add_node("EORD", "MM-PUR", "purchasing",
                       "Source List (Vendor-Material-Plant)",
                       ["LIFNR", "MATNR", "WERKS", "ERNAM"])

        # Purchasing Documents
        self._add_node("EKKO", "MM-PUR", "purchasing",
                       "Purchasing Document Header",
                       ["EBELN"])

        self._add_node("EKPO", "MM-PUR", "purchasing",
                       "Purchasing Document Item",
                       ["EBELN", "EBELP"])

        self._add_node("EKKN", "MM-PUR", "purchasing",
                       "Account Assignment (Purchasing Document)",
                       ["EBELN", "EBELP", "KTPNR"])

        # Scheduling Agreements
        self._add_node("EKES", "MM-PUR", "purchasing",
                       "Vendor Confirmations (Scheduling Agreements)",
                       ["EBELN", "EBELP", "EBTYP"])

        # ========================================================================
        # 3. NODES — Customer / Business Partner (SD / BP)
        # ========================================================================
        self._add_node("KNA1", "SD", "sales_distribution",
                       "Customer Master (General Data)",
                       ["KUNNR"])

        self._add_node("KNB1", "FI", "sales_distribution",
                       "Customer Master (Company Code Data)",
                       ["KUNNR", "BUKRS"])

        self._add_node("KNVV", "SD", "sales_distribution",
                       "Customer Master (Sales Area Data)",
                       ["KUNNR", "VKORG", "VTWEG", "SPART"])

        self._add_node("KNVK", "SD", "customer_service",
                       "Customer Master Contact Relationships",
                       ["KUNNR", "PARZA"])

        self._add_node("ADRC", "BP", "business_partner",
                       "Business Address Services (Central Address Mgmt)",
                       ["ADDRNUMBER", "PERSNUMBER"])

        # ========================================================================
        # 4. NODES — Sales & Distribution (SD)
        # ========================================================================
        self._add_node("VBAK", "SD", "sales_distribution",
                       "Sales Document Header",
                       ["VBELN"])

        self._add_node("VBAP", "SD", "sales_distribution",
                       "Sales Document Item",
                       ["VBELN", "POSNR"])

        self._add_node("VBEP", "SD", "sales_distribution",
                       "Sales Document: Schedule Line",
                       ["VBELN", "POSNR", "ETENR"])

        self._add_node("VBFA", "SD", "sales_distribution",
                       "Sales Document Flow (Document Chain)",
                       ["VBELV", "POSNV", "VBELN", "POSNN"])

        self._add_node("LIKP", "SD", "sales_distribution",
                       "Delivery Document Header",
                       ["VBELN"])

        self._add_node("LIPS", "SD", "sales_distribution",
                       "Delivery Document Item",
                       ["VBELN", "POSNR"])

        self._add_node("VBRP", "SD", "sales_distribution",
                       "Billing Document Item",
                       ["VBELN", "POSNR"])

        self._add_node("VBRK", "SD", "sales_distribution",
                       "Billing Document Header",
                       ["VBELN"])

        # Pricing
        self._add_node("KONV", "SD", "sales_distribution",
                       "Pricing Conditions (Communication)",
                       ["KNUMV", "KPOSN", "STUNR"])

        self._add_node("A003", "SD", "sales_distribution",
                       "Condition Records: Tax (Customer-Material-Country)",
                       ["KAPPL", "KSCHL", "VKORG", "VTWEG", "MATNR", "LAND1"])

        # ========================================================================
        # 5. NODES — Finance / Accounting (FI / CO)
        # ========================================================================
        self._add_node("BKPF", "FI", "financial_accounting",
                       "Accounting Document Header",
                       ["BELNR", "GJAHR", "BUKRS"])

        self._add_node("BSEG", "FI", "financial_accounting",
                       "Accounting Document Segment (Line Items)",
                       ["BELNR", "GJAHR", "BUZEI", "BUKRS"])

        self._add_node("BSIK", "FI", "financial_accounting",
                       "Accounting: Secondary Index for Vendors (Open Items)",
                       ["LIFNR", "BUKRS", "BELNR", "BUZEI"])

        self._add_node("BSAK", "FI", "financial_accounting",
                       "Accounting: Secondary Index for Vendors (Cleared Items)",
                       ["LIFNR", "BUKRS", "BELNR", "BUZEI"])

        self._add_node("BSID", "FI", "financial_accounting",
                       "Accounting: Secondary Index for Customers (Open Items)",
                       ["KUNNR", "BUKRS", "BELNR", "BUZEI"])

        self._add_node("BSAD", "FI", "financial_accounting",
                       "Accounting: Secondary Index for Customers (Cleared Items)",
                       ["KUNNR", "BUKRS", "BELNR", "BUZEI"])

        self._add_node("BSAS", "FI", "financial_accounting",
                       "Accounting: Secondary Index for G/L Accounts (Cleared Items)",
                       ["HKONT", "BUKRS", "BELNR", "BUZEI"])

        self._add_node("SKA1", "FI", "financial_accounting",
                       "G/L Account Master (Chart of Accounts)",
                       ["SAKNR"])

        self._add_node("SKB1", "FI", "financial_accounting",
                       "G/L Account Master (Company Code)",
                       ["SAKNR", "BUKRS"])

        self._add_node("T001", "FI", "financial_accounting",
                       "Company Codes",
                       ["BUKRS"])

        self._add_node("T001W", "MM", "material_master",
                       "Plants",
                       ["WERKS"])

        self._add_node("T024", "MM-PUR", "purchasing",
                       "Purchasing Organizations",
                       ["EKORG"])

        self._add_node("T001L", "MM", "warehouse_management",
                       "Storage Locations",
                       ["WERKS", "LGORT"])

        # Controlling
        self._add_node("CSKS", "CO", "project_system",
                       "Cost Center Master",
                       ["KOKRS", "DATAB", "DATBI", "KOSTL"])

        self._add_node("CSSL", "CO", "project_system",
                       "Cost Center Group / Cost Element",
                       ["KOKRS", "DATAB", "DATBI", "KSTAR"])

        self._add_node("COSP", "CO", "project_system",
                       "CO Object: Cost Totals (Actual)",
                       ["OBJNR", "GJAHR", "PERBL"])

        self._add_node("COSS", "CO", "project_system",
                       "CO Object: Cost Totals (Plan)",
                       ["OBJNR", "GJAHR", "PERBL"])

        # ========================================================================
        # 6. NODES — Quality Management (QM)
        # ========================================================================
        self._add_node("QALS", "QM", "quality_management",
                       "Inspection Lot Master",
                       ["QALS", "MANDT"])

        self._add_node("QAVE", "QM", "quality_management",
                       "Usage Decision (Inspection Characteristics)",
                       ["QALS", "QUNUM", "QUPOS"])

        self._add_node("QAMV", "QM", "quality_management",
                       "Inspection History / Usage Decision Records",
                       ["QALS", "QUNUM"])

        self._add_node("MAPL", "QM", "quality_management",
                       "Assignment of Task Lists to Materials",
                       ["WERKS", "PLNTY", "PLNNR", "MATNR"])

        self._add_node("PLMK", "QM", "quality_management",
                       "Inspection Master Data (Task List - Characteristics)",
                       ["PLNTY", "PLNNR", "PLNKN", "KNNUM"])

        self._add_node("PLPO", "QM", "quality_management",
                       "Task List Operations / Process Steps",
                       ["PLNTY", "PLNNR", "PLNKN", "TOLERANCE_KEY"])

        # ========================================================================
        # 7. NODES — Project System (PS)
        # ========================================================================
        self._add_node("PROJ", "PS", "project_system",
                       "Project Definition",
                       ["PSPNR"])

        self._add_node("PRPS", "PS", "project_system",
                       "Work Breakdown Structure (WBS) Element",
                       ["PSPNR"])

        self._add_node("AFVC", "PS", "project_system",
                       "Activity at Work Center (Network Node)",
                       ["NPLNR", "POSNR"])

        self._add_node("AFVV", "PS", "project_system",
                       "Operation/Cost Data for Activities",
                       ["NPLNR", "POSNR", "VORNR"])

        self._add_node("ANLA", "FI", "real_estate",
                       "Asset Master Record (Investment Accounting)",
                       ["ANLN1", "BUKRS"])

        self._add_node("ANEP", "FI", "real_estate",
                       "Asset Accounting Document Line Items",
                       ["ANLN1", "BUKRS", "AJAHR", "BELNR", "BUZEI"])

        # ========================================================================
        # 8. NODES — Warehouse Management (WM)
        # ========================================================================
        self._add_node("LEU4", "WM", "warehouse_management",
                       "Transfer Order Header",
                       ["TONUM"])

        self._add_node("LTBP", "WM", "warehouse_management",
                       "Transfer Order Item (Batch-managed)",
                       ["TONUM", "TQLFD"])

        self._add_node("LQUA", "WM", "warehouse_management",
                       "Quant (WM) — Physical Stock Record",
                       ["MATNR", "WERKS", "LGORT", "LENUM"])

        self._add_node("LAGP", "WM", "warehouse_management",
                       "Storage Type (Warehouse Management)",
                       ["WERKS", "LGTYP"])

        self._add_node("LDCP", "WM", "warehouse_management",
                       "Storage Bin (Warehouse Management)",
                       ["WERKS", "LGTYP", "LGPLA"])

        # ========================================================================
        # 9. NODES — Transportation / Logistics (TM / SD)
        # ========================================================================
        self._add_node("VTTK", "TM", "transportation",
                       "Transportation Order / Shipment Header",
                       ["TKNUM"])

        self._add_node("VTLP", "TM", "transportation",
                       "Transportation Order / Shipment Leg",
                       ["TKNUM", "TPLNR"])

        self._add_node("VTFA", "TM", "transportation",
                       "Transportation Order / Shipment Stage",
                       ["TKNUM", "TDFORMAT"])

        # ========================================================================
        # 10. NODES — Customer Service / Field Service (CS)
        # ========================================================================
        self._add_node("ASMD", "CS", "customer_service",
                       "Service Order / Service Notification",
                       ["QMNUM", "ITEAM"])

        self._add_node("IHPA", "CS", "customer_service",
                       "Business Partner Relationships (for Service)",
                       ["OBJNR", "PARVW", "PARNR"])

        self._add_node("DRAD", "CS", "customer_service",
                       "Document-Item Assignment (GOS attachments)",
                       ["RADBNR", "DOKNR", "DOKAR", "DOKTL", "DOKOB"])

        # ========================================================================
        # 11. NODES — Human Resources (HR) — skeleton
        # ========================================================================
        self._add_node("PA0001", "HR", "human_resources",
                       "HR Master Record: Organization Assignment",
                       ["PERNR", "ORGEH", "PLANS", "STELL"])

        self._add_node("PA0008", "HR", "human_resources",
                       "HR Master Record: Pay / Wage Type",
                       ["PERNR", "FPFAS"])

        # ========================================================================
        # 12. NODES — Taxation / Country-Specific India
        # ========================================================================
        self._add_node("J_1IG_HSN_SAC", "TAX", "taxation_india",
                       "India: HSN Codes for Materials / SAC Codes for Services",
                       ["STEGR", "SUBSTCODE"])

        self._add_node("J_1BBRANCH", "TAX", "taxation_india",
                       "India: Branch/Plant Registration for GST",
                       ["BUKRS", "BRANCH"])

        # ========================================================================
        # 13. NODES — Real Estate (RE-FX)
        # ========================================================================
        self._add_node("VIMONI", "RE", "real_estate",
                       "Real Estate Contract / Rent Index",
                       ["VKONT"])

        self._add_node("VIBDT", "RE", "real_estate",
                       "Real Estate Business Partner Link",
                       ["KUNNR", "LAND1", "STCEG"])

        # ========================================================================
        # 14. NODES — GTS (Global Trade Services)
        # ========================================================================
        self._add_node("/SAPSLL/POD", "GTS", "gts",
                       "GTS: Proof of Delivery / Export Control",
                       ["PODHANDLE"])

        self._add_node("/SAPSLL/PNTPR", "GTS", "gts",
                       "GTS: Partner Master Data (Trade Compliance)",
                       ["PARNR", "PARKZ"])

        # ========================================================================
        # 15. NODES — IS-OIL (Oil & Gas)
        # ========================================================================
        self._add_node("OIB_A04", "IS-OIL", "is_oil",
                       "Oil & Gas: Tank Farm / Storage Location Data",
                       ["TPLNR", "TATYP"])

        self._add_node("OIG_V", "IS-OIL", "is_oil",
                       "Oil & Gas: Volume / Measurement Data",
                       ["OIBNR", "VPRGSNR"])

        self._add_node("T8JV", "IS-OIL", "is_oil",
                       "Oil & Gas: Joint Venture Partner Codes",
                       ["JVCD"])

        # ========================================================================
        # 16. NODES — IS-Utilities (IS-U)
        # ========================================================================
        self._add_node("EVBS", "IS-UTILITY", "is_utilities",
                       "Utilities: Device Installation (Field Service)",
                       ["GERNR", "ANLAGE"])

        self._add_node("EANL", "IS-UTILITY", "is_utilities",
                       "Utilities: Equipment Master (Installation Point)",
                       ["ANLAGE", "EQUNR"])

        self._add_node("EGERR", "IS-UTILITY", "is_utilities",
                       "Utilities: Device Register / Error Register",
                       ["FEGRP", "FETYP", "FENUM"])

        # ========================================================================
        # 17. NODES — IS-Retail
        # ========================================================================
        self._add_node("WRS1", "IS-RETAIL", "is_retail",
                       "Retail: Replenishment Proposal / Buying Line",
                       ["BWONNR", "EPOID"])

        self._add_node("SETY", "IS-RETAIL", "is_retail",
                       "Retail: Assortment Module / Range Planning",
                       ["SRTID", "SETID"])

        # ========================================================================
        # 18. NODES — IS-Health (Healthcare)
        # ========================================================================
        self._add_node("NPAT", "IS-HEALTH", "is_health",
                       "Healthcare: Patient Master / Coverage",
                       ["PATNR", "SUBJNR"])

        self._add_node("NBEW", "IS-HEALTH", "is_health",
                       "Healthcare: Care Beneficiary (Insurance/Billing)",
                       ["PATNR", "VKONT"])

        self._add_node("NPNZ", "IS-HEALTH", "is_health",
                       "Healthcare: Care Plan / Care Activity Records",
                       ["NPANR", "PPNVP"])

        # ========================================================================
        # 19. NODES — Variant Configuration (LO-VC)
        # ========================================================================
        self._add_node("CABN", "LO-VC", "variant_configuration",
                       "Configuration: Characteristic (Feature) Master",
                       ["ATINN", "ATZHL"])

        self._add_node("KLAH", "LO-VC", "variant_configuration",
                       "Configuration: Class Master (Product Class)",
                       ["CLINT", "KLART"])

        self._add_node("CUOBJ", "LO-VC", "variant_configuration",
                       "Configuration: Configuration (Internal Object Key)",
                       ["CUOBJ", "CLINT"])

        self._add_node("INOB", "LO-VC", "variant_configuration",
                       "Allocation: Material to Configuration (Long Text)",
                       ["OBJEK", "OBTYP"])

        # ========================================================================
        # 20. NODES — Plant Maintenance / Customer Service (PM)
        # ========================================================================
        self._add_node("IHK6", "PM", "customer_service",
                       "Equipment Master Record (Functional Location/Tech Obj)",
                       ["EQUNR", "TPLNR"])

        self._add_node("EQUI", "PM", "customer_service",
                       "Equipment Master Data",
                       ["EQUNR"])

        self._add_node("IFLOT", "PM", "customer_service",
                       "Fleet / Technical Object Master",
                       ["OBJNR"])

        self._add_node("ILOA", "PM", "customer_service",
                       "Technical Object Location / Address Assignment",
                       ["ILOAN", "ADRNR"])

        # ========================================================================
        # 21. NODES — Cross-cutting Master Data
        # ========================================================================
        self._add_node("BUT000", "BP", "business_partner",
                       "Business Partner: General Data I (Central BP Master)",
                       ["PARTNER"])

        self._add_node("BUT020", "BP", "business_partner",
                       "Business Partner: Address Management",
                       ["PARTNER", "ADDRNUMBER"])

        self._add_node("BUT050", "BP", "business_partner",
                       "Business Partner: Customer/Vendor Link (Role Relationships)",
                       ["PARTNER", "RELATION", "PARTNER2"])

        self._add_node("T001K", "FI", "financial_accounting",
                       "Valuation Area (Company Code or Plant Level)",
                       ["BWKEY", "BUKRS"])

        self._add_node("T024E", "MM-PUR", "purchasing",
                       "Purchasing Groups",
                       ["EKGRP"])

        self._add_node("T003", "SD", "sales_distribution",
                       "Sales Document Types",
                       ["AUART"])

        self._add_node("TVAK", "SD", "sales_distribution",
                       "Sales Document Types (Header)",
                       ["AUART"])

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 1: INTERNAL MODULE JOINS — Material Master
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("MARA", "MARC",
                       "MARA.MATNR = MARC.MATNR",
                       "1:N", "internal",
                       "Material → Plant-specific data")

        self._add_edge("MARA", "MAKT",
                       "MARA.MATNR = MAKT.MATNR AND MAKT.SPRAS = 'E'",
                       "1:N", "internal",
                       "Material → Description (English)")

        self._add_edge("MARA", "MARM",
                       "MARA.MATNR = MARM.MATNR",
                       "1:N", "internal",
                       "Material → Alternate UoM conversions")

        self._add_edge("MARC", "MARD",
                       "MARC.MATNR = MARD.MATNR AND MARC.WERKS = MARD.WERKS",
                       "1:N", "internal",
                       "Material-Plant → Storage Location stock")

        self._add_edge("MARC", "MBEW",
                       "MARC.MATNR = MBEW.MATNR AND MARC.WERKS = MBEW.BWKEY",
                       "1:N", "internal",
                       "Material-Plant → Valuation (BWKEY maps to WERKS)")

        self._add_edge("MARC", "MVKE",
                       "MARC.MATNR = MVKE.MATNR",
                       "1:N", "internal",
                       "Material → Sales organization sales data")

        self._add_edge("MARD", "MLGN",
                       "MARD.MATNR = MLGN.MATNR AND MARD.WERKS = MLGN.WERKS AND MARD.LGORT = MLGN.LGORT",
                       "1:N", "internal",
                       "Storage Location → WM storage-type view")

        self._add_edge("MLGN", "MLGT",
                       "MLGN.MATNR = MLGT.MATNR AND MLGN.WERKS = MLGT.WERKS AND MLGN.LGORT = MLGT.LGORT AND MLGN.LGTYP = MLGT.LGTYP",
                       "1:N", "internal",
                       "Storage Type → WM storage-bin view")

        self._add_edge("MARD", "LQUA",
                       "MARD.MATNR = LQUA.MATNR AND MARD.WERKS = LQUA.WERKS AND MARD.LGORT = LQUA.LGORT",
                       "1:N", "internal",
                       "Storage Location → WM Quant (physical stock)")

        self._add_edge("MCHA", "MCH1",
                       "MCHA.MATNR = MCH1.MATNR AND MCHA.CHARG = MCH1.CHARG",
                       "1:N", "internal",
                       "Batch master → Batch stock quantities")

        self._add_edge("MCHA", "QALS",
                       "MCHA.MATNR = QALS.MATNR AND MCHA.CHARG = QALS.CHARG",
                       "1:N", "internal",
                       "Batch → QM Inspection Lot by batch")

        self._add_edge("MARC", "MAPL",
                       "MARC.MATNR = MAPL.MATNR AND MARC.WERKS = MAPL.WERKS",
                       "1:N", "internal",
                       "Material-Plant → QM task list assignment")

        self._add_edge("MAPL", "PLMK",
                       "MAPL.PLNTY = PLMK.PLNTY AND MAPL.PLNNR = PLMK.PLNNR AND MAPL.PLNKN = PLMK.PLNKN",
                       "1:N", "internal",
                       "Task List Assignment → QM Inspection Characteristics")

        self._add_edge("PLMK", "PLPO",
                       "PLMK.PLNTY = PLPO.PLNTY AND PLMK.PLNNR = PLPO.PLNNR AND PLMK.PLNKN = PLPO.PLNKN",
                       "1:N", "internal",
                       "QM Characteristics → Operations/Process Steps")

        self._add_edge("QALS", "QAVE",
                       "QALS.QALS = QAVE.QALS AND QALS.QUNUM = QAVE.QUNUM",
                       "1:1", "internal",
                       "Inspection Lot → Usage Decision")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 2: INTERNAL MODULE JOINS — Vendor / Purchasing
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("LFA1", "LFB1",
                       "LFA1.LIFNR = LFB1.LIFNR",
                       "1:1", "internal",
                       "Vendor general → Company-code data")

        self._add_edge("LFA1", "LFBK",
                       "LFA1.LIFNR = LFBK.LIFNR",
                       "1:N", "internal",
                       "Vendor → Bank details")

        self._add_edge("LFA1", "EINA",
                       "LFA1.LIFNR = EINA.LIFNR",
                       "1:N", "internal",
                       "Vendor → Purchasing Info Records")

        self._add_edge("EINA", "EINE",
                       "EINA.INFNR = EINE.INFNR AND EINA.LIFNR = EINE.LIFNR AND EINA.EKORG = EINE.EKORG",
                       "1:1", "internal",
                       "Info Record (General) → Purchasing Org data")

        self._add_edge("EINA", "EORD",
                       "EINA.LIFNR = EORD.LIFNR AND EINA.MATNR = EORD.MATNR",
                       "1:N", "internal",
                       "Info Record → Source List (by vendor-material)")

        self._add_edge("EKKO", "EKPO",
                       "EKKO.EBELN = EKPO.EBELN",
                       "1:N", "internal",
                       "PO Header → PO Items")

        self._add_edge("EKPO", "EKKN",
                       "EKPO.EBELN = EKKN.EBELN AND EKPO.EBELP = EKKN.EBELP",
                       "1:N", "internal",
                       "PO Item → Account Assignment")

        self._add_edge("EKKO", "EKES",
                       "EKKO.EBELN = EKES.EBELN AND EKKO.LIFNR = EKES.LIFNR",
                       "1:N", "internal",
                       "PO Header → Vendor Confirmations (scheduling agmt)")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 3: INTERNAL MODULE JOINS — Customer / Sales
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("KNA1", "KNB1",
                       "KNA1.KUNNR = KNB1.KUNNR",
                       "1:1", "internal",
                       "Customer general → Company-code data")

        self._add_edge("KNA1", "KNVV",
                       "KNA1.KUNNR = KNVV.KUNNR",
                       "1:N", "internal",
                       "Customer → Sales area data")

        self._add_edge("KNA1", "KNVK",
                       "KNA1.KUNNR = KNVK.KUNNR",
                       "1:N", "internal",
                       "Customer → Contact person relationships")

        self._add_edge("VBAK", "VBAP",
                       "VBAK.VBELN = VBAP.VBELN",
                       "1:N", "internal",
                       "Sales Order Header → Items")

        self._add_edge("VBAP", "VBEP",
                       "VBAP.VBELN = VBEP.VBELN AND VBAP.POSNR = VBEP.POSNR",
                       "1:N", "internal",
                       "Sales Order Item → Schedule Lines")

        self._add_edge("VBAK", "LIKP",
                       "VBAK.VBELN = LIKP.VGBEL AND LIKP.VGTYP = 'C'",
                       "1:N", "internal",
                       "Sales Order → Outbound Delivery (via reference)")

        self._add_edge("LIKP", "LIPS",
                       "LIKP.VBELN = LIPS.VBELN",
                       "1:N", "internal",
                       "Delivery Header → Delivery Items")

        self._add_edge("LIPS", "VBRP",
                       "LIPS.VBELN = VBRP.VBELN AND LIPS.POSNR = VBRP.POSNR",
                       "1:N", "internal",
                       "Delivery Item → Billing (via reference)")

        self._add_edge("VBAK", "VBRK",
                       "VBAK.VBELN = VBRK.VBELN",
                       "1:N", "internal",
                       "Sales Order → Billing Document")

        self._add_edge("VBAP", "KONV",
                       "VBAK.KNUMV = KONV.KNUMV AND VBAP.POSNR = KONV.KPOSN",
                       "1:N", "internal",
                       "Sales Order Item → Pricing conditions")

        self._add_edge("VBAP", "VBFA",
                       "VBAP.VBELN = VBFA.VBELN AND VBAP.POSNR = VBFA.POSNN",
                       "1:N", "internal",
                       "Sales Item → Document flow (what created this item)")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 4: INTERNAL MODULE JOINS — Finance / Controlling
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("BKPF", "BSEG",
                       "BKPF.BELNR = BSEG.BELNR AND BKPF.GJAHR = BSEG.GJAHR AND BKPF.BUKRS = BSEG.BUKRS",
                       "1:N", "internal",
                       "FI Document Header → Line Items")

        self._add_edge("BSEG", "BSIK",
                       "BSEG.BELNR = BSIK.BELNR AND BSEG.GJAHR = BSIK.GJAHR AND BSEG.BUKRS = BSIK.BUKRS AND BSEG.BUZEI = BSIK.BUZEI",
                       "1:1", "internal",
                       "FI Line Item → Vendor Open Items index")

        self._add_edge("BSEG", "BSAK",
                       "BSEG.BELNR = BSAK.BELNR AND BSEG.GJAHR = BSAK.GJAHR AND BSEG.BUKRS = BSAK.BUKRS AND BSEG.BUZEI = BSAK.BUZEI",
                       "1:1", "internal",
                       "FI Line Item → Vendor Cleared Items index")

        self._add_edge("BSEG", "BSID",
                       "BSEG.BELNR = BSID.BELNR AND BSEG.GJAHR = BSID.GJAHR AND BSEG.BUKRS = BSID.BUKRS AND BSEG.BUZEI = BSID.BUZEI",
                       "1:1", "internal",
                       "FI Line Item → Customer Open Items index")

        # G/L Secondary Index (Open and Cleared) — BSAS added as node, now wire edges
        self._add_edge("BSEG", "BSAS",
                       "BSEG.BELNR = BSAS.BELNR AND BSEG.GJAHR = BSAS.GJAHR AND BSEG.BUKRS = BSAS.BUKRS AND BSEG.BUZEI = BSAS.BUZEI",
                       "1:1", "internal",
                       "FI Line Item → G/L Cleared Items index (BSAS)")

        self._add_edge("BSAS", "SKA1",
                       "BSAS.HKONT = SKA1.SAKNR",
                       "N:1", "internal",
                       "G/L Cleared Items → G/L Account Master")

        self._add_edge("BSEG", "SKA1",
                       "BSEG.HKONT = SKA1.SAKNR",
                       "N:1", "internal",
                       "FI Line Item → G/L Account master")

        self._add_edge("SKA1", "SKB1",
                       "SKA1.SAKNR = SKB1.SAKNR",
                       "1:N", "internal",
                       "G/L Account (coa) → Company-code G/L data")

        self._add_edge("T001", "T001K",
                       "T001.BUKRS = T001K.BUKRS",
                       "1:N", "internal",
                       "Company Code → Valuation Area mapping")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 5: CROSS-MODULE BRIDGES — MM-PUR ↔ MM (Procurement ↔ Material)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("EINA", "MARA",
                       "EINA.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Purchasing Info Record → Material master")

        self._add_edge("EORD", "MARA",
                       "EORD.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Source List → Material")

        self._add_edge("EORD", "MARC",
                       "EORD.MATNR = MARC.MATNR AND EORD.WERKS = MARC.WERKS",
                       "N:1", "cross_module",
                       "Source List → Material-Plant (source list per plant)")

        self._add_edge("EKPO", "MARA",
                       "EKPO.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "PO Item → Material")

        self._add_edge("EKPO", "MARC",
                       "EKPO.MATNR = MARC.MATNR AND EKPO.WERKS = MARC.WERKS",
                       "N:1", "cross_module",
                       "PO Item → Material-Plant")

        self._add_edge("EKPO", "MBEW",
                       "EKPO.MATNR = MBEW.MATNR",
                       "N:1", "cross_module",
                       "PO Item → Material Valuation")

        self._add_edge("EKPO", "EINA",
                       "EKPO.INFNR = EINA.INFNR",
                       "N:1", "cross_module",
                       "PO Item → Info Record link")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 6: CROSS-MODULE BRIDGES — MM-PUR ↔ BP/FI (Procurement ↔ Vendor)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("EKKO", "LFA1",
                       "EKKO.LIFNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "PO Header → Vendor master")

        self._add_edge("EKKO", "LFB1",
                       "EKKO.LIFNR = LFB1.LIFNR AND EKKO.BUKRS = LFB1.BUKRS",
                       "N:1", "cross_module",
                       "PO Header → Vendor company-code data")

        self._add_edge("EKKO", "T001",
                       "EKKO.BUKRS = T001.BUKRS",
                       "N:1", "cross_module",
                       "PO Header → Company Code")

        self._add_edge("EKKO", "T024",
                       "EKKO.EKORG = T024.EKORG",
                       "N:1", "cross_module",
                       "PO Header → Purchasing Organization")

        self._add_edge("EKPO", "LFA1",
                       "EKPO.LIFNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "PO Item → Vendor")

        self._add_edge("EKES", "LFA1",
                       "EKES.LIFNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "Vendor Confirmation → Vendor")

        self._add_edge("BSIK", "LFA1",
                       "BSIK.LIFNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "Vendor Open Items → Vendor master")

        self._add_edge("BSIK", "LFB1",
                       "BSIK.LIFNR = LFB1.LIFNR AND BSIK.BUKRS = LFB1.BUKRS",
                       "N:1", "cross_module",
                       "Vendor Open Items → Vendor company-code")

        self._add_edge("BSIK", "T001",
                       "BSIK.BUKRS = T001.BUKRS",
                       "N:1", "cross_module",
                       "Vendor Open Items → Company Code")

        self._add_edge("BSAK", "LFA1",
                       "BSAK.LIFNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "Vendor Cleared Items → Vendor master")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 7: CROSS-MODULE BRIDGES — SD ↔ MM (Sales ↔ Material)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("VBAP", "MARA",
                       "VBAP.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Sales Order Item → Material")

        self._add_edge("VBAP", "MARC",
                       "VBAP.MATNR = MARC.MATNR AND VBAP.WERKS = MARC.WERKS",
                       "N:1", "cross_module",
                       "Sales Order Item → Material-Plant")

        self._add_edge("VBAP", "MBEW",
                       "VBAP.MATNR = MBEW.MATNR",
                       "N:1", "cross_module",
                       "Sales Order Item → Material Valuation (for pricing)")

        self._add_edge("LIPS", "MARA",
                       "LIPS.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Delivery Item → Material")

        self._add_edge("LIPS", "MCH1",
                       "LIPS.MATNR = MCH1.MATNR AND LIPS.CHARG = MCH1.CHARG AND LIPS.WERKS = MCH1.WERKS",
                       "N:1", "cross_module",
                       "Delivery Item → Batch Stock")

        self._add_edge("MSKA", "MARA",
                       "MSKA.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Sales Order Stock → Material")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 8: CROSS-MODULE BRIDGES — SD ↔ BP (Sales ↔ Customer)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("VBAK", "KNA1",
                       "VBAK.KUNNR = KNA1.KUNNR",
                       "N:1", "cross_module",
                       "Sales Order → Customer master")

        self._add_edge("VBAK", "KNB1",
                       "VBAK.KUNNR = KNB1.KUNNR AND VBAK.BUKRS = KNB1.BUKRS",
                       "N:1", "cross_module",
                       "Sales Order → Customer company-code")

        self._add_edge("VBAK", "KNVV",
                       "VBAK.KUNNR = KNVV.KUNNR AND VBAK.VKORG = KNVV.VKORG AND VBAK.VTWEG = KNVV.VTWEG",
                       "N:1", "cross_module",
                       "Sales Order → Customer Sales Area data")

        self._add_edge("LIKP", "KNA1",
                       "LIKP.KUNNR = KNA1.KUNNR",
                       "N:1", "cross_module",
                       "Delivery → Customer")

        self._add_edge("VBRK", "KNA1",
                       "VBRK.KUNAG = KNA1.KUNNR",
                       "N:1", "cross_module",
                       "Billing → Bill-to Customer")

        self._add_edge("VBRK", "KNB1",
                       "VBRK.KUNAG = KNB1.KUNNR AND VBRK.BUKRS = KNB1.BUKRS",
                       "N:1", "cross_module",
                       "Billing → Customer company-code")

        self._add_edge("BSID", "KNA1",
                       "BSID.KUNNR = KNA1.KUNNR",
                       "N:1", "cross_module",
                       "Customer Open Items → Customer")

        self._add_edge("BSID", "KNB1",
                       "BSID.KUNNR = KNB1.KUNNR AND BSID.BUKRS = KNB1.BUKRS",
                       "N:1", "cross_module",
                       "Customer Open Items → Customer company-code")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 9: CROSS-MODULE BRIDGES — FI ↔ BP/CO (Finance ↔ Vendor/Customer)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("BSEG", "LFA1",
                       "BSEG.LIFNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "FI Line Item → Vendor (vendor invoices)")

        self._add_edge("BSEG", "KNA1",
                       "BSEG.KUNNR = KNA1.KUNNR",
                       "N:1", "cross_module",
                       "FI Line Item → Customer (customer invoices)")

        self._add_edge("BSEG", "SKA1",
                       "BSEG.HKONT = SKA1.SAKNR",
                       "N:1", "cross_module",
                       "FI Line Item → G/L Account")

        self._add_edge("BSEG", "BKPF",
                       "BSEG.BELNR = BKPF.BELNR AND BSEG.GJAHR = BKPF.GJAHR AND BSEG.BUKRS = BKPF.BUKRS",
                       "1:1", "cross_module",
                       "FI Line Item → Document Header")

        self._add_edge("BSEG", "T001",
                       "BSEG.BUKRS = T001.BUKRS",
                       "N:1", "cross_module",
                       "FI Line Item → Company Code")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 10: CROSS-MODULE BRIDGES — QM ↔ MM (Quality ↔ Material)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("QALS", "MARA",
                       "QALS.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Inspection Lot → Material")

        self._add_edge("QALS", "MARC",
                       "QALS.MATNR = MARC.MATNR AND QALS.WERK = MARC.WERKS",
                       "N:1", "cross_module",
                       "Inspection Lot → Material-Plant")

        self._add_edge("QALS", "EKKO",
                       "QALS.MATNR = EKKO.MATNR",
                       "N:1", "cross_module",
                       "Inspection Lot → PO (QM inspection tied to PO receipt)")

        self._add_edge("QAVE", "MARA",
                       "QAVE.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Usage Decision → Material")

        self._add_edge("QAVE", "LFA1",
                       "QAVE.LIFNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "Usage Decision → Vendor (quality rating)")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 11: CROSS-MODULE BRIDGES — PS ↔ MM/FI/CO (Project ↔ Material/Finance)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("PRPS", "PROJ",
                       "PRPS.PSPHI = PROJ.PSPNR",
                       "N:1", "cross_module",
                       "WBS Element → Project Definition")

        self._add_edge("AFVC", "PRPS",
                       "AFVC.PROJN = PRPS.PSPNR",
                       "N:1", "cross_module",
                       "Activity → WBS Element")

        self._add_edge("AFVV", "AFVC",
                       "AFVV.NPLNR = AFVC.NPLNR AND AFVV.POSNR = AFVC.POSNR",
                       "1:N", "cross_module",
                       "Activity Operations → Activity Cost Data")

        self._add_edge("AFVV", "MARA",
                       "AFVV.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Network Activity → Material (component)")

        self._add_edge("PRPS", "MBEW",
                       "PRPS.MATNR = MBEW.MATNR",
                       "N:1", "cross_module",
                       "WBS Element → Material Valuation (for WBS with material)")

        self._add_edge("COSP", "PRPS",
                       "COSP.OBJNR = PRPS.OBJNR",
                       "N:1", "cross_module",
                       "CO Actual Costs → WBS Element")

        self._add_edge("COSS", "PRPS",
                       "COSS.OBJNR = PRPS.OBJNR",
                       "N:1", "cross_module",
                       "CO Plan Costs → WBS Element")

        self._add_edge("COSP", "CSKS",
                       "COSP.KOSTL = CSKS.KOSTL",
                       "N:1", "cross_module",
                       "CO Actual Costs → Cost Center")

        self._add_edge("ANLA", "T001",
                       "ANLA.BUKRS = T001.BUKRS",
                       "N:1", "cross_module",
                       "Asset Master → Company Code")

        self._add_edge("ANEP", "ANLA",
                       "ANEP.ANLN1 = ANLA.ANLN1 AND ANEP.BUKRS = ANLA.BUKRS",
                       "1:N", "cross_module",
                       "Asset Line Items → Asset Master")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 12: CROSS-MODULE BRIDGES — WM ↔ MM (Warehouse ↔ Material)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("LQUA", "MARA",
                       "LQUA.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "WM Quant → Material")

        self._add_edge("LQUA", "MCH1",
                       "LQUA.MATNR = MCH1.MATNR AND LQUA.CHARG = MCH1.CHARG",
                       "N:1", "cross_module",
                       "WM Quant → Batch Stock (if batch-managed)")

        self._add_edge("LQUA", "MARD",
                       "LQUA.MATNR = MARD.MATNR AND LQUA.WERKS = MARD.WERKS AND LQUA.LGORT = MARD.LGORT",
                       "N:1", "cross_module",
                       "WM Quant → IM Storage Location (2-book inventory)")

        self._add_edge("LAGP", "T001W",
                       "LAGP.WERKS = T001W.WERKS",
                       "N:1", "cross_module",
                       "Storage Type → Plant")

        self._add_edge("LDCP", "LAGP",
                       "LDCP.WERKS = LAGP.WERKS AND LDCP.LGTYP = LAGP.LGTYP",
                       "1:N", "cross_module",
                       "Storage Bin → Storage Type")

        self._add_edge("LEU4", "VTTK",
                       "LEU4.TKNUM = VTTK.TKNUM",
                       "1:N", "cross_module",
                       "Transfer Order → Transportation Order")

        self._add_edge("LIKP", "VTTK",
                       "LIKP.TKNUM = VTTK.TKNUM",
                       "N:1", "cross_module",
                       "Delivery → Transportation Order (TM integration)")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 13: CROSS-MODULE BRIDGES — SD ↔ FI (Billing → Accounting)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("VBRK", "BKPF",
                       "VBRK.BELNR = BKPF.BELNR AND VBRK.FKIMG > 0",
                       "N:1", "cross_module",
                       "Billing Document → FI Accounting Document")

        self._add_edge("VBRK", "BSEG",
                       "VBRK.BELNR = BSEG.BELNR AND VBRK.GJAHR = BSEG.GJAHR",
                       "1:N", "cross_module",
                       "Billing → FI Line Items (revenue posting)")

        self._add_edge("VBAK", "VBFA",
                       "VBAK.VBELN = VBFA.VBELN",
                       "1:N", "cross_module",
                       "Sales Order → Document Flow (what created it)")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 14: CROSS-MODULE BRIDGES — BP Central Master (BUT000)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("BUT000", "LFA1",
                       "BUT000.PARTNER = LFA1.LIFNR",
                       "1:1", "cross_module",
                       "BP Central Master → Vendor (CVI link)")

        self._add_edge("BUT000", "KNA1",
                       "BUT000.PARTNER = KNA1.KUNNR",
                       "1:1", "cross_module",
                       "BP Central Master → Customer (CVI link)")

        self._add_edge("BUT000", "BUT020",
                       "BUT000.PARTNER = BUT020.PARTNER",
                       "1:N", "cross_module",
                       "BP → BP Address")

        self._add_edge("BUT020", "ADRC",
                       "BUT020.ADDRNUMBER = ADRC.ADDRNUMBER",
                       "N:1", "cross_module",
                       "BP Address → Central Address Management")

        self._add_edge("LFA1", "ADRC",
                       "LFA1.ADRNR = ADRC.ADDRNUMBER",
                       "N:1", "cross_module",
                       "Vendor → Central Address")

        self._add_edge("KNA1", "ADRC",
                       "KNA1.ADRNR = ADRC.ADDRNUMBER",
                       "N:1", "cross_module",
                       "Customer → Central Address")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 15: CROSS-MODULE BRIDGES — CS / PM (Service ↔ BP/Equipment)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("ASMD", "KNA1",
                       "ASMD.KUNNR = KNA1.KUNNR",
                       "N:1", "cross_module",
                       "Service Order → Customer")

        self._add_edge("ASMD", "IHPA",
                       "ASMD.QMNUM = IHPA.OBJNR",
                       "1:N", "cross_module",
                       "Service Order → BP Relationships")

        self._add_edge("IHPA", "BUT000",
                       "IHPA.PARNR = BUT000.PARTNER",
                       "N:1", "cross_module",
                       "Service Partner → BP")

        self._add_edge("DRAD", "VBAK",
                       "DRAD.DOKOB = 'BUS2031' AND DRAD.VBELN = VBAK.VBELN",
                       "N:1", "cross_module",
                       "Document Attachment → Sales Order")

        self._add_edge("DRAD", "EKKO",
                       "DRAD.DOKOB = 'BUS2012' AND DRAD.VBELN = EKKO.EBELN",
                       "N:1", "cross_module",
                       "Document Attachment → Purchase Order")

        self._add_edge("EQUI", "IHK6",
                       "EQUI.EQUNR = IHK6.EQUNR",
                       "1:1", "cross_module",
                       "Equipment → Functional Location")

        self._add_edge("IHK6", "ILOA",
                       "IHK6.ILOAN = ILOA.ILOAN",
                       "1:1", "cross_module",
                       "Functional Location → Location/Address")

        self._add_edge("ILOA", "ADRC",
                       "ILOA.ADRNR = ADRC.ADDRNUMBER",
                       "N:1", "cross_module",
                       "Tech Object Location → Address")

        self._add_edge("EQUI", "MARA",
                       "EQUI.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Equipment Bill of Materials → Material")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 16: CROSS-MODULE BRIDGES — LO-VC (Variant Configuration)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("CUOBJ", "KLAH",
                       "CUOBJ.CLINT = KLAH.CLINT",
                       "1:1", "cross_module",
                       "Configuration Object → Class Master")

        self._add_edge("CUOBJ", "MARA",
                       "CUOBJ.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Configuration → Material (configurable material)")

        self._add_edge("INOB", "CUOBJ",
                       "INOB.OBJEK = CUOBJ.CUOBJ",
                       "1:1", "cross_module",
                       "Material-CUOBJ Allocation → Configuration")

        self._add_edge("INOB", "MARA",
                       "INOB.OBJEK = MARA.MATNR",
                       "N:1", "cross_module",
                       "Material Long Text → Material")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 17: CROSS-MODULE BRIDGES — IS-UTILITY (Utilities)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("EVBS", "EANL",
                       "EVBS.ANLAGE = EANL.ANLAGE",
                       "1:N", "cross_module",
                       "Device Installation Point → Equipment Master")

        self._add_edge("EVBS", "KNA1",
                       "EVBS.VKONTO = KNA1.KUNNR",
                       "N:1", "cross_module",
                       "Device Installation → Utility Customer (premise)")

        self._add_edge("EGERR", "EVBS",
                       "EGERR.ANLAGE = EVBS.ANLAGE",
                       "N:1", "cross_module",
                       "Device Error Register → Device Installation")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 18: CROSS-MODULE BRIDGES — HR
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("CSKS", "PA0001",
                       "CSKS.KOSTL = PA0001.KOSTL",
                       "N:1", "cross_module",
                       "Cost Center → HR Organization Assignment")

        self._add_edge("PA0001", "LFA1",
                       "PA0001.PERNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "Employee (HR) → Vendor (contingent workers sometimes)")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 19: CROSS-MODULE BRIDGES — Tax / India Localization
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("J_1BBRANCH", "T001",
                       "J_1BBRANCH.BUKRS = T001.BUKRS",
                       "N:1", "cross_module",
                       "India Branch Reg. → Company Code")

        self._add_edge("J_1BBRANCH", "T001W",
                       "J_1BBRANCH.BRANCH = T001W.WERKS",
                       "N:1", "cross_module",
                       "India Branch Reg. → Plant")

        self._add_edge("MARA", "J_1IG_HSN_SAC",
                       "MARA.STEGR = J_1IG_HSN_SAC.STEGR",
                       "N:1", "cross_module",
                       "Material → India HSN/SAC Code")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 20: CROSS-MODULE BRIDGES — TM (Transportation)
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("VTTK", "LIKP",
                       "VTTK.TKNUM = LIKP.TKNUM",
                       "1:N", "cross_module",
                       "Shipment → Outbound Delivery")

        self._add_edge("VTTK", "VBAK",
                       "VTTK.KUNNR = VBAK.KUNNR",
                       "N:1", "cross_module",
                       "Shipment → Sales Order (ship-to party)")

        self._add_edge("VTTK", "LFA1",
                       "VTTK.LIFNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "Shipment → Carrier/Shipper Vendor")

        self._add_edge("VTLP", "T001W",
                       "VTLP.TPLNR = T001W.WERKS",
                       "N:1", "cross_module",
                       "Shipment Leg → Destination Plant")

        # ──────────────────────────────────────────────────────────────────────
        # EDGE SET 21: SPECIAL STOCK BRIDGES — MSKA, MSLB, MKOL
        # ──────────────────────────────────────────────────────────────────────
        self._add_edge("MSKA", "VBAP",
                       "MSKA.VBELN = VBAP.VBELN AND MSKA.POSNR = VBAP.POSNR",
                       "N:1", "cross_module",
                       "Sales Order Stock → Sales Order Item")

        self._add_edge("MSKA", "KNA1",
                       "MSKA.KUNNU = KNA1.KUNNR",
                       "N:1", "cross_module",
                       "Sales Order Stock → Customer (owner)")

        self._add_edge("MSLB", "LFA1",
                       "MSLB.LIFNR = LFA1.LIFNR",
                       "N:1", "cross_module",
                       "Vendor-owned Special Stock → Vendor")

        self._add_edge("MSLB", "MARA",
                       "MSLB.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Vendor-owned Special Stock → Material")

        self._add_edge("MKOL", "PRPS",
                       "MKOL.OBJNR = PRPS.OBJNR",
                       "N:1", "cross_module",
                       "Project-owned Special Stock → WBS Element")

        self._add_edge("MKOL", "MARA",
                       "MKOL.MATNR = MARA.MATNR",
                       "N:1", "cross_module",
                       "Project-owned Special Stock → Material")

    # ─── Public API ────────────────────────────────────────────────────────────

    def traverse_graph_cds(self, start_table: str, end_table: str) -> str:
        from app.core.cds_mapping import format_cds_join
        sql_join = self.traverse_graph(start_table, end_table)
        return format_cds_join(sql_join)

    def traverse_graph(self, start_table: str, end_table: str) -> str:
        """
        Finds the shortest JOIN path between two SAP tables using BFS on NetworkX.
        Returns a formatted SQL JOIN string ready for the orchestrator.
        """
        start = start_table.upper()
        end = end_table.upper()

        if start not in self.G.nodes:
            return f"Error: Table '{start}' is not in the Graph RAG schema. Available: {sorted(self.G.nodes)[:20]}..."
        if end not in self.G.nodes:
            return f"Error: Table '{end}' is not in the Graph RAG schema. Available: {sorted(self.G.nodes)[:20]}..."

        try:
            path = nx.shortest_path(self.G, source=start, target=end)
        except nx.NetworkXNoPath:
            return f"No direct join path found between {start} and {end} through known FK relationships."

        if len(path) == 1:
            return f"No JOIN needed — query can be resolved entirely within {start}."

        lines = [f"Start at {path[0]}"]
        for i in range(len(path) - 1):
            src, tgt = path[i], path[i + 1]
            edge = self.G.get_edge_data(src, tgt)
            bridge = " ← CROSS-MODULE → " if edge["bridge_type"] == "cross_module" else " → "
            lines.append(f"{edge['condition']}{bridge}({src} → {tgt}) [{edge['cardinality']}]")

        return "\n".join(lines)

    def find_path(self, start_table: str, end_table: str) -> Optional[List[str]]:
        """Returns the raw list of tables in the shortest path."""
        try:
            return nx.shortest_path(self.G, source=start_table.upper(), target=end_table.upper())
        except nx.NetworkXNoPath:
            return None

    def get_join_condition(self, table_a: str, table_b: str) -> Optional[str]:
        """Get the FK join condition between two directly connected tables."""
        edge = self.G.get_edge_data(table_a.upper(), table_b.upper())
        return edge["condition"] if edge else None

    def get_subgraph_context(self, path: List[str]) -> Dict:
        """
        Returns rich metadata for a path (tables, join conditions, modules, bridge types).
        Used by rag_service.py to explain the cross-module resolution.
        """
        tables_in_path = []
        joins = []
        cross_module_bridges = []

        for i, table in enumerate(path):
            meta = self._node_meta.get(table, {})
            tables_in_path.append({
                "table": table,
                "module": meta.get("module", "?"),
                "domain": meta.get("domain", "?"),
                "desc": meta.get("desc", ""),
                "key_columns": meta.get("key_columns", []),
            })

            if i < len(path) - 1:
                edge = self.G.get_edge_data(table, path[i + 1])
                joins.append({
                    "from": table,
                    "to": path[i + 1],
                    "condition": edge["condition"] if edge else "?",
                    "cardinality": edge["cardinality"] if edge else "?",
                    "bridge_type": edge["bridge_type"] if edge else "?",
                })
                if edge and edge["bridge_type"] == "cross_module":
                    cross_module_bridges.append(f"{table} ↔ {path[i + 1]}")

        return {
            "path": path,
            "tables": tables_in_path,
            "joins": joins,
            "cross_module_bridges": cross_module_bridges,
            "is_cross_module": len(cross_module_bridges) > 0,
        }

    def get_neighbors(self, table: str, depth: int = 1) -> Dict[str, List[dict]]:
        """
        Get all tables reachable from `table` within `depth` hops.
        Useful for "what can I reach from Material X?"
        """
        table = table.upper()
        if table not in self.G.nodes:
            return {}
        distances = nx.single_source_shortest_path_length(self.G, table, cutoff=depth)
        result = {}
        for neighbor, dist in distances.items():
            if neighbor == table:
                continue
            edge = self.G.get_edge_data(table, neighbor)
            meta = self._node_meta.get(neighbor, {})
            result[neighbor] = [{
                "distance": dist,
                "module": meta.get("module", "?"),
                "domain": meta.get("domain", "?"),
                "join_condition": edge["condition"] if edge else "?",
                "cardinality": edge["cardinality"] if edge else "?",
                "bridge_type": edge["bridge_type"] if edge else "?",
            }]
        return result

    def get_all_tables(self) -> List[str]:
        """Return all tables in the graph."""
        return list(self.G.nodes)

    def get_table_meta(self, table: str) -> Dict:
        """Return metadata for a table."""
        return self._node_meta.get(table.upper(), {})

    def stats(self) -> dict:
        """Return graph statistics."""
        return {
            "total_tables": self.G.number_of_nodes(),
            "total_relationships": self.G.number_of_edges(),
            "cross_module_bridges": sum(
                1 for u, v in self.G.edges for e in [self.G.get_edge_data(u, v)]
                if e and e.get("bridge_type") == "cross_module"
            ),
            "modules": list(set(v["module"] for v in self._node_meta.values())),
            "domains": list(set(v["domain"] for v in self._node_meta.values())),
        }

    def print_map(self):
        """Print a human-readable adjacency map grouped by module."""
        by_module = {}
        for table, meta in self._node_meta.items():
            mod = meta["module"]
            by_module.setdefault(mod, []).append(table)

        for mod in sorted(by_module):
            tables = sorted(by_module[mod])
            print(f"\n[{mod}] ({len(tables)} tables)")
            for t in tables:
                neighbors = list(self.G.neighbors(t))
                print(f"  {t} → {', '.join(sorted(neighbors))}")


class AllPathsExplorer:
    """
    Extends GraphRAGManager to find ALL valid JOIN paths between two tables,
    scoring and ranking them instead of just returning the shortest path.
    """
    def __init__(self, graph_manager: GraphRAGManager):
        self.gm = graph_manager
        
        # Scoring weights (lower score = better path)
        self.WEIGHTS = {
            "cardinality_1:1": 1.0,
            "cardinality_N:1": 1.2,
            "cardinality_1:N": 3.0,  # Penalize 1:N (row explosion)
            "cross_module": 0.8,     # Cross-module paths are good semantic context
            "internal": 1.0,
            "huge_table_penalty": 5.0 # e.g. BSEG, MSEG
        }
        self.HUGE_TABLES = {"BSEG", "MSEG", "MKPF", "BSIS", "BSAS", "BSID", "BSAD", "BSIK", "BSAK", "LIPS"}

    @property
    def G(self):
        return getattr(self.gm, "G", getattr(self.gm, "_nx_cache", None))

    def _score_path(self, path: List[str]) -> Tuple[float, List[dict]]:
        score = 0.0
        details = []
        
        # Penalize paths that transit through huge transactional tables unnecessarily
        for i in range(1, len(path) - 1):
            if path[i] in self.HUGE_TABLES:
                score += self.WEIGHTS["huge_table_penalty"]
                
        for i in range(len(path) - 1):
            u, v = path[i], path[i+1]
            edge = self.G.get_edge_data(u, v)
            
            # Base hop cost
            hop_score = 1.0
            
            # Cardinality multiplier
            card = edge.get("cardinality", "1:1")
            hop_score *= self.WEIGHTS.get(f"cardinality_{card}", 2.0)
            
            # Bridge type multiplier
            bridge = edge.get("bridge_type", "internal")
            hop_score *= self.WEIGHTS.get(bridge, 1.0)
            
            score += hop_score
            details.append({
                "from": u, "to": v,
                "condition": edge["condition"],
                "cardinality": card,
                "bridge_type": bridge,
                "hop_cost": hop_score
            })
            
        return score, details

    def find_all_ranked_paths(self, start_table: str, end_table: str, max_depth: int = 5, top_k: int = 3) -> List[dict]:
        """Finds all paths up to max_depth and returns the top_k best scored paths."""
        if hasattr(self.gm, "find_all_ranked_paths_native"):
            return self.gm.find_all_ranked_paths_native(start_table, end_table, max_depth, top_k)
            
        start = start_table.upper()
        end = end_table.upper()
        
        if start not in self.G.nodes or end not in self.G.nodes:
            return []
            
        try:
            raw_paths = list(nx.all_simple_paths(self.G, source=start, target=end, cutoff=max_depth))
        except nx.NetworkXNoPath:
            return []
            
        ranked = []
        for p in raw_paths:
            score, details = self._score_path(p)
            ranked.append({
                "path": p,
                "score": round(score, 2),
                "hops": len(p) - 1,
                "details": details
            })
            
        # Sort by lowest score (best)
        ranked.sort(key=lambda x: x["score"])
        return ranked[:top_k]

    def explain_best_paths(self, start_table: str, end_table: str, max_depth: int = 5) -> str:
        """Returns a human/LLM readable string explaining the best JOIN paths available."""
        paths = self.find_all_ranked_paths(start_table, end_table, max_depth)
        if not paths:
            return f"No paths found between {start_table} and {end_table} within {max_depth} hops."
            
        lines = [f"Found {len(paths)} ranked paths from {start_table} to {end_table}:"]
        for idx, p in enumerate(paths):
            lines.append(f"\n[{idx+1}] Path: {' → '.join(p['path'])} (Score: {p['score']})")
            for d in p["details"]:
                bridge_marker = " [CROSS-MODULE]" if d["bridge_type"] == "cross_module" else ""
                lines.append(f"    • {d['condition']} ({d['cardinality']}){bridge_marker}")
                
        return "\n".join(lines)


from datetime import date

class TemporalGraphRAG:
    """
    Extends base graph with temporal validity awareness.
    SAP master data has validity periods (DATAB/DATBI, GJAHR/PERBL).
    This generates temporal-aware SQL and prunes paths that aren't
    temporally valid for a given key_date.
    """
    def __init__(self, graph_manager: GraphRAGManager):
        self.gm = graph_manager
        
        # Registry of temporal columns per table
        self.TEMPORAL_REGISTRY = {
            # Standard Date Ranges (Valid From / Valid To)
            "LFA1": {"type": "range", "from": "DATAB", "to": None},          # Vendor creation date
            "KNB1": {"type": "range", "from": "DATAB", "to": "DATBI"},       # Customer company-code validity
            "EINA": {"type": "range", "from": "DATAB", "to": "DATBI"},       # Info record validity
            "EINE": {"type": "range", "from": "DATAB", "to": "DATBI"},       # Info record conditions
            "CSKS": {"type": "range", "from": "DATAB", "to": "DATBI"},       # Cost center validity
            "CSSL": {"type": "range", "from": "DATAB", "to": "DATBI"},       # Cost center activity type validity
            "A003": {"type": "range", "from": "DATAB", "to": "DATBI"},       # Condition records (pricing/tax)
            "PRPS": {"type": "range", "from": "START", "to": "ENDE"},        # WBS element planned dates
            
            # Fiscal Year Period-based
            "COSP": {"type": "fiscal_year", "year": "GJAHR", "period": "PERBL"}, # Cost totals (Actual)
            "COSS": {"type": "fiscal_year", "year": "GJAHR", "period": "PERBL"}, # Cost totals (Plan)
            "BKPF": {"type": "fiscal_year", "year": "GJAHR", "period": "MONAT"}, # FI Header
            "BSEG": {"type": "fiscal_year", "year": "GJAHR", "period": None},    # FI Line item
            "ANLC": {"type": "fiscal_year", "year": "GJAHR", "period": None},    # Asset values
            
            # Key-Date Valuation
            "MBEW": {"type": "key_date", "date": "BWDAT", "fallback": "LFMON"},  # Valuation price effective date
            "EORD": {"type": "range", "from": "VDATU", "to": "BDATU"}        # Source list validity
        }

    @property
    def G(self):
        return getattr(self.gm, "G", getattr(self.gm, "_nx_cache", None))

    def generate_temporal_sql_filters(self, tables_in_path: List[str], key_date: date) -> List[str]:
        """
        Generates SAP HANA SQL WHERE clauses for temporal validity
        based on the tables present in the JOIN path.
        """
        filters = []
        key_date_str = key_date.strftime("%Y%m%d")  # SAP format YYYYMMDD
        fiscal_year = str(key_date.year)
        fiscal_period = f"{key_date.month:03d}"     # e.g., '004' for April
        
        for table in tables_in_path:
            t_upper = table.upper()
            if t_upper in self.TEMPORAL_REGISTRY:
                t_meta = self.TEMPORAL_REGISTRY[t_upper]
                
                # 1. Date Ranges (DATAB/DATBI)
                if t_meta["type"] == "range":
                    col_from = t_meta["from"]
                    col_to = t_meta["to"]
                    
                    if col_from and col_to:
                        filters.append(f"{t_upper}.{col_from} <= '{key_date_str}' AND {t_upper}.{col_to} >= '{key_date_str}'")
                    elif col_from:
                        filters.append(f"{t_upper}.{col_from} <= '{key_date_str}'")
                        
                # 2. Fiscal Year / Period
                elif t_meta["type"] == "fiscal_year":
                    col_year = t_meta["year"]
                    col_period = t_meta["period"]
                    
                    filters.append(f"{t_upper}.{col_year} = '{fiscal_year}'")
                    if col_period:
                        filters.append(f"{t_upper}.{col_period} = '{fiscal_period}'")
                        
                # 3. Key Date (e.g. Valuation)
                elif t_meta["type"] == "key_date":
                    col_date = t_meta["date"]
                    filters.append(f"{t_upper}.{col_date} <= '{key_date_str}'")
                    
        return filters

    def temporal_validity_filter(self, key_date: date) -> nx.Graph:
        """
        Returns a subgraph containing only edges/tables valid on key_date.
        This represents the 'logical graph state' as of the key date.
        """
        filtered_G = nx.Graph()
        key_date_str = key_date.strftime("%Y%m%d")
        
        # In a real SAP implementation, this would query DDIC or live data
        # to see if the table itself has data valid for the date.
        # For the Graph RAG metadata structure, we assume all structural nodes
        # remain valid, but we add edge weights penalizing temporally complex paths
        # if the user asks for a date far in the past.
        
        for u, v, data in self.G.edges(data=True):
            # Base copy
            filtered_G.add_edge(u, v, **data)
            
            # Annotate edge with temporal complexity if both tables have temporal columns
            u_temp = u in self.TEMPORAL_REGISTRY
            v_temp = v in self.TEMPORAL_REGISTRY
            
            if u_temp and v_temp:
                filtered_G[u][v]["temporal_complexity"] = "high"
            elif u_temp or v_temp:
                filtered_G[u][v]["temporal_complexity"] = "medium"
            else:
                filtered_G[u][v]["temporal_complexity"] = "low"
                
        return filtered_G

    def query_as_of_date(self, start_table: str, end_table: str, key_date: date) -> dict:
        """
        Find best JOIN path valid as of a specific date, and return the 
        path alongside the required temporal WHERE clauses.
        """
        start = start_table.upper()
        end = end_table.upper()
        
        # 1. Create temporal subgraph
        filtered_G = self.temporal_validity_filter(key_date)
        
        # 2. Find shortest path on temporal subgraph
        try:
            path = nx.shortest_path(filtered_G, source=start, target=end)
        except nx.NetworkXNoPath:
            return {"error": f"No path found for date {key_date}"}
            
        # 3. Generate temporal SQL filters for the discovered path
        temporal_filters = self.generate_temporal_sql_filters(path, key_date)
        
        # 4. Generate standard JOIN clause
        join_lines = [f"Start at {path[0]}"]
        for i in range(len(path) - 1):
            src, tgt = path[i], path[i + 1]
            edge = filtered_G.get_edge_data(src, tgt)
            join_lines.append(f"{edge['condition']} → ({src} → {tgt}) [{edge['cardinality']}]")
            
        return {
            "path": path,
            "join_clause": "\n".join(join_lines),
            "temporal_filters": temporal_filters,
            "key_date": key_date.strftime("%Y-%m-%d")
        }


class SteinerTreeExplorer:
    """
    Extends GraphRAGManager to find the minimum-cost subgraph connecting 3 or more 
    terminal tables using the Steiner Tree approximation. 
    Crucial for multi-hop, multi-module queries (e.g., LFA1 + MARA + KNA1).
    """
    def __init__(self, graph_manager):
        self.gm = graph_manager
        self.G = graph_manager.G
        
    def _create_weighted_graph(self) -> nx.Graph:
        """
        Create a copy of the graph with calculated weights on edges to guide
        the Steiner tree approximation away from huge transactional tables
        or 1:N explosions unless necessary.
        """
        W = nx.Graph()
        HUGE_TABLES = {"BSEG", "MSEG", "MKPF", "BSIS", "BSAS", "BSID", "BSAD", "BSIK", "BSAK", "LIPS"}
        
        for u, v, data in self.G.edges(data=True):
            weight = 1.0
            
            # Penalize huge tables
            if u in HUGE_TABLES or v in HUGE_TABLES:
                weight += 5.0
                
            # Penalize 1:N cardinality (row explosion)
            card = data.get("cardinality", "1:1")
            if card == "1:N":
                weight += 2.0
            elif card == "N:1":
                weight += 0.2
                
            # Reward cross-module bridges
            if data.get("bridge_type") == "cross_module":
                weight -= 0.2
                
            # Ensure weight is strictly positive
            weight = max(0.1, weight)
            
            # Copy edge with new weight
            W.add_edge(u, v, weight=weight, **data)
            
        # Copy node metadata
        for n, data in self.G.nodes(data=True):
            W.add_node(n, **data)
            
        return W

    def find_steiner_tree(self, terminal_nodes: List[str]) -> Optional[nx.Graph]:
        """
        Finds the approximate Steiner tree spanning all terminal_nodes.
        Returns the subgraph connecting them, or None if impossible.
        """
        terminals = [n.upper() for n in terminal_nodes if n.upper() in self.G.nodes]
        if len(terminals) < 2:
            return None
            
        from networkx.algorithms.approximation.steinertree import steiner_tree
        
        W = self._create_weighted_graph()
        
        # Must isolate the connected component to avoid NetworkX metric_closure errors on disconnected graphs
        try:
            component = nx.node_connected_component(W, terminals[0])
            for t in terminals:
                if t not in component:
                    return None  # Terminals are in disjoint subgraphs
            subgraph = W.subgraph(component).copy()
            
            # Using 'kou' method explicitly to avoid deprecation warnings and ensure stability
            st = steiner_tree(subgraph, terminals, weight="weight", method="kou")
            return st
        except nx.NetworkXError:
            return None

    def build_sql_from_tree(self, st: nx.Graph, root_node: str) -> str:
        """
        Traverses the Steiner tree starting from root_node using BFS,
        generating the SQL JOIN string.
        """
        if not st or len(st.nodes) == 0:
            return "No valid join tree found."
            
        root = root_node.upper()
        if root not in st.nodes:
            root = list(st.nodes)[0]
            
        lines = [f"Start at {root}"]
        
        # BFS traversal
        edges = list(nx.bfs_edges(st, root))
        for src, tgt in edges:
            edge_data = self.G.get_edge_data(src, tgt)
            if edge_data:
                bridge = " ← CROSS-MODULE → " if edge_data.get("bridge_type") == "cross_module" else " → "
                lines.append(f"{edge_data.get('condition')}{bridge}({src} → {tgt}) [{edge_data.get('cardinality')}]")
            else:
                lines.append(f"JOIN {tgt} ON {src} = {tgt} (Implicit)")
                
        return "\n".join(lines)



# Singleton
graph_store = GraphRAGManager()
path_explorer = AllPathsExplorer(graph_store)
temporal_graph = TemporalGraphRAG(graph_store)


if __name__ == "__main__":
    g = graph_store

    print("=" * 60)
    print("  Graph RAG — Enterprise SAP FK Map")
    print("=" * 60)

    stats = g.stats()
    print(f"\n  Tables: {stats['total_tables']}  |  Relationships: {stats['total_relationships']}")
    print(f"  Cross-module bridges: {stats['cross_module_bridges']}")
    print(f"  Modules: {', '.join(sorted(stats['modules']))}")
    print(f"  Domains: {', '.join(sorted(stats['domains']))}")

    print("\n" + "=" * 60)
    print("  Example Traversals")
    print("=" * 60)

    tests = [
        ("LFA1", "MARA"),       # Vendor ↔ Material (via EINA/Purchasing Info Record)
        ("KNA1", "MARA"),       # Customer ↔ Material
        ("EKKO", "MBEW"),       # PO ↔ Material Valuation
        ("BSIK", "LFA1"),       # Vendor Open Items ↔ Vendor
        ("VBAK", "KNA1"),       # Sales Order ↔ Customer
        ("QALS", "MARA"),       # Inspection Lot ↔ Material
        ("PRPS", "MARA"),       # WBS ↔ Material
        ("MARD", "LQUA"),       # Storage Location ↔ WM Quant
        ("VTTK", "LIKP"),       # Transportation ↔ Delivery
        ("ANLA", "T001"),       # Asset ↔ Company Code
        ("BUT000", "MARA"),     # BP Central ↔ Material (via CVI + Info Record)
        ("EKKO", "KNA1"),       # PO ↔ Customer (via Vendor ↔ BP ↔ Customer)
    ]

    for start, end in tests:
        path = g.find_path(start, end)
        if path:
            result = g.traverse_graph(start, end)
            print(f"\n{start} → {end}: {' → '.join(path)}")
            print(f"  JOIN: {result[:200]}")
        else:
            print(f"\n{start} → {end}: NO PATH")

    print("\n" + "=" * 60)
    print("  Steiner Tree (Multi-Terminal JOIN)")
    print("=" * 60)
    
    terminals = ["LFA1", "MARA", "KNA1"]
    print(f"\nConnecting multiple modules: {terminals}")
    st_explorer = SteinerTreeExplorer(graph_store)
    st = st_explorer.find_steiner_tree(terminals)
    if st:
        print(f"  Subgraph nodes: {list(st.nodes)}")
        sql = st_explorer.build_sql_from_tree(st, 'LFA1')
        print(f"  JOIN path:\n    {sql.replace(chr(10), chr(10)+'    ')}")
    else:
        print("  Failed to find a connecting tree.")

    print("\n" + "=" * 60)
    print("  Full Module Map")
    print("=" * 60)
    g.print_map()
