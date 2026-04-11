"""
AUTO-GENERATED SAP SQL PATTERNS
Generated from Graph Store. Total Patterns: 251
"""

# ======================================================================
# MODULE: MM (61 patterns)
# ======================================================================

MM_AUTO_PATTERNS = [
    {
        "intent": "Retrieve General Material Data (MARA)",
        "business_use_case": "Basic data retrieval for General Material Data",
        "tables": ["MARA"],
        "sql": """
SELECT * 
FROM 
    MARA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Plant Data for Material (MARC)",
        "business_use_case": "Basic data retrieval for Plant Data for Material",
        "tables": ["MARC"],
        "sql": """
SELECT * 
FROM 
    MARC
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Storage Location Data for Material (MARD)",
        "business_use_case": "Basic data retrieval for Storage Location Data for Material",
        "tables": ["MARD"],
        "sql": """
SELECT * 
FROM 
    MARD
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Material Valuation (MBEW)",
        "business_use_case": "Basic data retrieval for Material Valuation",
        "tables": ["MBEW"],
        "sql": """
SELECT * 
FROM 
    MBEW
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Material Descriptions (MAKT)",
        "business_use_case": "Basic data retrieval for Material Descriptions",
        "tables": ["MAKT"],
        "sql": """
SELECT * 
FROM 
    MAKT
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Material Data for Each Storage Location (WM) (MLGN)",
        "business_use_case": "Basic data retrieval for Material Data for Each Storage Location (WM)",
        "tables": ["MLGN"],
        "sql": """
SELECT * 
FROM 
    MLGN
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Material Data for Each Storage Type (WM) (MLGT)",
        "business_use_case": "Basic data retrieval for Material Data for Each Storage Type (WM)",
        "tables": ["MLGT"],
        "sql": """
SELECT * 
FROM 
    MLGT
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Batch Stock (Quantities) (MCH1)",
        "business_use_case": "Basic data retrieval for Batch Stock (Quantities)",
        "tables": ["MCH1"],
        "sql": """
SELECT * 
FROM 
    MCH1
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Batch Master Record (MCHA)",
        "business_use_case": "Basic data retrieval for Batch Master Record",
        "tables": ["MCHA"],
        "sql": """
SELECT * 
FROM 
    MCHA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Sales Order Stock (MSKA)",
        "business_use_case": "Basic data retrieval for Sales Order Stock",
        "tables": ["MSKA"],
        "sql": """
SELECT * 
FROM 
    MSKA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Special Stock (Vendor-owned) (MSLB)",
        "business_use_case": "Basic data retrieval for Special Stock (Vendor-owned)",
        "tables": ["MSLB"],
        "sql": """
SELECT * 
FROM 
    MSLB
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Special Stock (Project-owned) (MKOL)",
        "business_use_case": "Basic data retrieval for Special Stock (Project-owned)",
        "tables": ["MKOL"],
        "sql": """
SELECT * 
FROM 
    MKOL
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Sales Data for Material (MVKE)",
        "business_use_case": "Basic data retrieval for Sales Data for Material",
        "tables": ["MVKE"],
        "sql": """
SELECT * 
FROM 
    MVKE
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Unit of Measure Data for Material (MARM)",
        "business_use_case": "Basic data retrieval for Unit of Measure Data for Material",
        "tables": ["MARM"],
        "sql": """
SELECT * 
FROM 
    MARM
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Vendor Evaluation Grades (Material/Plant) (LFBW)",
        "business_use_case": "Basic data retrieval for Vendor Evaluation Grades (Material/Plant)",
        "tables": ["LFBW"],
        "sql": """
SELECT * 
FROM 
    LFBW
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Plants (T001W)",
        "business_use_case": "Basic data retrieval for Plants",
        "tables": ["T001W"],
        "sql": """
SELECT * 
FROM 
    T001W
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Storage Locations (T001L)",
        "business_use_case": "Basic data retrieval for Storage Locations",
        "tables": ["T001L"],
        "sql": """
SELECT * 
FROM 
    T001L
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MARA and MARC (General Material Data to Plant Data for Material)",
        "business_use_case": "Combine data from MARA and MARC using standard SAP foreign keys.",
        "tables": ["MARA", "MARC"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    MARC b ON a.MATNR = b.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MARA and MAKT (General Material Data to Material Descriptions)",
        "business_use_case": "Combine data from MARA and MAKT using standard SAP foreign keys.",
        "tables": ["MARA", "MAKT"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    MAKT b ON a.MATNR = b.MATNR AND b.SPRAS = 'E'
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MARA and MARM (General Material Data to Unit of Measure Data for Material)",
        "business_use_case": "Combine data from MARA and MARM using standard SAP foreign keys.",
        "tables": ["MARA", "MARM"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    MARM b ON a.MATNR = b.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and EINA (General Material Data to Purchasing Info Record: General Data)",
        "business_use_case": "Combine data from MARA and EINA using standard SAP foreign keys.",
        "tables": ["MARA", "EINA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    EINA b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and EORD (General Material Data to Source List (Vendor-Material-Plant))",
        "business_use_case": "Combine data from MARA and EORD using standard SAP foreign keys.",
        "tables": ["MARA", "EORD"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    EORD b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and EKPO (General Material Data to Purchasing Document Item)",
        "business_use_case": "Combine data from MARA and EKPO using standard SAP foreign keys.",
        "tables": ["MARA", "EKPO"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    EKPO b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and VBAP (General Material Data to Sales Document Item)",
        "business_use_case": "Combine data from MARA and VBAP using standard SAP foreign keys.",
        "tables": ["MARA", "VBAP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    VBAP b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and LIPS (General Material Data to Delivery Document Item)",
        "business_use_case": "Combine data from MARA and LIPS using standard SAP foreign keys.",
        "tables": ["MARA", "LIPS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    LIPS b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and MSKA (General Material Data to Sales Order Stock)",
        "business_use_case": "Combine data from MARA and MSKA using standard SAP foreign keys.",
        "tables": ["MARA", "MSKA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    MSKA b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and QALS (General Material Data to Inspection Lot Master)",
        "business_use_case": "Combine data from MARA and QALS using standard SAP foreign keys.",
        "tables": ["MARA", "QALS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    QALS b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and QAVE (General Material Data to Usage Decision (Inspection Characteristics))",
        "business_use_case": "Combine data from MARA and QAVE using standard SAP foreign keys.",
        "tables": ["MARA", "QAVE"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    QAVE b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and AFVV (General Material Data to Operation/Cost Data for Activities)",
        "business_use_case": "Combine data from MARA and AFVV using standard SAP foreign keys.",
        "tables": ["MARA", "AFVV"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    AFVV b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and LQUA (General Material Data to Quant (WM) — Physical Stock Record)",
        "business_use_case": "Combine data from MARA and LQUA using standard SAP foreign keys.",
        "tables": ["MARA", "LQUA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    LQUA b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and EQUI (General Material Data to Equipment Master Data)",
        "business_use_case": "Combine data from MARA and EQUI using standard SAP foreign keys.",
        "tables": ["MARA", "EQUI"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    EQUI b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and CUOBJ (General Material Data to Configuration: Configuration (Internal Object Key))",
        "business_use_case": "Combine data from MARA and CUOBJ using standard SAP foreign keys.",
        "tables": ["MARA", "CUOBJ"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    CUOBJ b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and INOB (General Material Data to Allocation: Material to Configuration (Long Text))",
        "business_use_case": "Combine data from MARA and INOB using standard SAP foreign keys.",
        "tables": ["MARA", "INOB"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    INOB b ON b.OBJEK = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and J_1IG_HSN_SAC (General Material Data to India: HSN Codes for Materials / SAC Codes for Services)",
        "business_use_case": "Combine data from MARA and J_1IG_HSN_SAC using standard SAP foreign keys.",
        "tables": ["MARA", "J_1IG_HSN_SAC"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    J_1IG_HSN_SAC b ON a.STEGR = b.STEGR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and MSLB (General Material Data to Special Stock (Vendor-owned))",
        "business_use_case": "Combine data from MARA and MSLB using standard SAP foreign keys.",
        "tables": ["MARA", "MSLB"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    MSLB b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARA and MKOL (General Material Data to Special Stock (Project-owned))",
        "business_use_case": "Combine data from MARA and MKOL using standard SAP foreign keys.",
        "tables": ["MARA", "MKOL"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARA a
JOIN 
    MKOL b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MARC and MARD (Plant Data for Material to Storage Location Data for Material)",
        "business_use_case": "Combine data from MARC and MARD using standard SAP foreign keys.",
        "tables": ["MARC", "MARD"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARC a
JOIN 
    MARD b ON a.MATNR = b.MATNR AND a.WERKS = b.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MARC and MBEW (Plant Data for Material to Material Valuation)",
        "business_use_case": "Combine data from MARC and MBEW using standard SAP foreign keys.",
        "tables": ["MARC", "MBEW"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARC a
JOIN 
    MBEW b ON a.MATNR = b.MATNR AND a.WERKS = b.BWKEY
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MARC and MVKE (Plant Data for Material to Sales Data for Material)",
        "business_use_case": "Combine data from MARC and MVKE using standard SAP foreign keys.",
        "tables": ["MARC", "MVKE"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARC a
JOIN 
    MVKE b ON a.MATNR = b.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MARC and MAPL (Plant Data for Material to Assignment of Task Lists to Materials)",
        "business_use_case": "Combine data from MARC and MAPL using standard SAP foreign keys.",
        "tables": ["MARC", "MAPL"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARC a
JOIN 
    MAPL b ON a.MATNR = b.MATNR AND a.WERKS = b.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARC and EORD (Plant Data for Material to Source List (Vendor-Material-Plant))",
        "business_use_case": "Combine data from MARC and EORD using standard SAP foreign keys.",
        "tables": ["MARC", "EORD"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARC a
JOIN 
    EORD b ON b.MATNR = a.MATNR AND b.WERKS = a.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARC and EKPO (Plant Data for Material to Purchasing Document Item)",
        "business_use_case": "Combine data from MARC and EKPO using standard SAP foreign keys.",
        "tables": ["MARC", "EKPO"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARC a
JOIN 
    EKPO b ON b.MATNR = a.MATNR AND b.WERKS = a.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARC and VBAP (Plant Data for Material to Sales Document Item)",
        "business_use_case": "Combine data from MARC and VBAP using standard SAP foreign keys.",
        "tables": ["MARC", "VBAP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARC a
JOIN 
    VBAP b ON b.MATNR = a.MATNR AND b.WERKS = a.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARC and QALS (Plant Data for Material to Inspection Lot Master)",
        "business_use_case": "Combine data from MARC and QALS using standard SAP foreign keys.",
        "tables": ["MARC", "QALS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARC a
JOIN 
    QALS b ON b.MATNR = a.MATNR AND b.WERK = a.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MARD and MLGN (Storage Location Data for Material to Material Data for Each Storage Location (WM))",
        "business_use_case": "Combine data from MARD and MLGN using standard SAP foreign keys.",
        "tables": ["MARD", "MLGN"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARD a
JOIN 
    MLGN b ON a.MATNR = b.MATNR AND a.WERKS = b.WERKS AND a.LGORT = b.LGORT
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MARD and LQUA (Storage Location Data for Material to Quant (WM) — Physical Stock Record)",
        "business_use_case": "Combine data from MARD and LQUA using standard SAP foreign keys.",
        "tables": ["MARD", "LQUA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MARD a
JOIN 
    LQUA b ON b.MATNR = a.MATNR AND b.WERKS = a.WERKS AND b.LGORT = a.LGORT
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MBEW and EKPO (Material Valuation to Purchasing Document Item)",
        "business_use_case": "Combine data from MBEW and EKPO using standard SAP foreign keys.",
        "tables": ["MBEW", "EKPO"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MBEW a
JOIN 
    EKPO b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MBEW and VBAP (Material Valuation to Sales Document Item)",
        "business_use_case": "Combine data from MBEW and VBAP using standard SAP foreign keys.",
        "tables": ["MBEW", "VBAP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MBEW a
JOIN 
    VBAP b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MBEW and PRPS (Material Valuation to Work Breakdown Structure (WBS) Element)",
        "business_use_case": "Combine data from MBEW and PRPS using standard SAP foreign keys.",
        "tables": ["MBEW", "PRPS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MBEW a
JOIN 
    PRPS b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MLGN and MLGT (Material Data for Each Storage Location (WM) to Material Data for Each Storage Type (WM))",
        "business_use_case": "Combine data from MLGN and MLGT using standard SAP foreign keys.",
        "tables": ["MLGN", "MLGT"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MLGN a
JOIN 
    MLGT b ON a.MATNR = b.MATNR AND a.WERKS = b.WERKS AND a.LGORT = b.LGORT AND a.LGTYP = b.LGTYP
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MCH1 and MCHA (Batch Stock (Quantities) to Batch Master Record)",
        "business_use_case": "Combine data from MCH1 and MCHA using standard SAP foreign keys.",
        "tables": ["MCH1", "MCHA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MCH1 a
JOIN 
    MCHA b ON b.MATNR = a.MATNR AND b.CHARG = a.CHARG
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MCH1 and LIPS (Batch Stock (Quantities) to Delivery Document Item)",
        "business_use_case": "Combine data from MCH1 and LIPS using standard SAP foreign keys.",
        "tables": ["MCH1", "LIPS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MCH1 a
JOIN 
    LIPS b ON b.MATNR = a.MATNR AND b.CHARG = a.CHARG AND b.WERKS = a.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MCH1 and LQUA (Batch Stock (Quantities) to Quant (WM) — Physical Stock Record)",
        "business_use_case": "Combine data from MCH1 and LQUA using standard SAP foreign keys.",
        "tables": ["MCH1", "LQUA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MCH1 a
JOIN 
    LQUA b ON b.MATNR = a.MATNR AND b.CHARG = a.CHARG
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MCHA and QALS (Batch Master Record to Inspection Lot Master)",
        "business_use_case": "Combine data from MCHA and QALS using standard SAP foreign keys.",
        "tables": ["MCHA", "QALS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MCHA a
JOIN 
    QALS b ON a.MATNR = b.MATNR AND a.CHARG = b.CHARG
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MSKA and VBAP (Sales Order Stock to Sales Document Item)",
        "business_use_case": "Combine data from MSKA and VBAP using standard SAP foreign keys.",
        "tables": ["MSKA", "VBAP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MSKA a
JOIN 
    VBAP b ON a.VBELN = b.VBELN AND a.POSNR = b.POSNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MSKA and KNA1 (Sales Order Stock to Customer Master (General Data))",
        "business_use_case": "Combine data from MSKA and KNA1 using standard SAP foreign keys.",
        "tables": ["MSKA", "KNA1"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MSKA a
JOIN 
    KNA1 b ON a.KUNNU = b.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MSLB and LFA1 (Special Stock (Vendor-owned) to Vendor Master (General Section))",
        "business_use_case": "Combine data from MSLB and LFA1 using standard SAP foreign keys.",
        "tables": ["MSLB", "LFA1"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MSLB a
JOIN 
    LFA1 b ON a.LIFNR = b.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join MKOL and PRPS (Special Stock (Project-owned) to Work Breakdown Structure (WBS) Element)",
        "business_use_case": "Combine data from MKOL and PRPS using standard SAP foreign keys.",
        "tables": ["MKOL", "PRPS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MKOL a
JOIN 
    PRPS b ON a.OBJNR = b.OBJNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join T001W and LAGP (Plants to Storage Type (Warehouse Management))",
        "business_use_case": "Combine data from T001W and LAGP using standard SAP foreign keys.",
        "tables": ["T001W", "LAGP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    T001W a
JOIN 
    LAGP b ON b.WERKS = a.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join T001W and J_1BBRANCH (Plants to India: Branch/Plant Registration for GST)",
        "business_use_case": "Combine data from T001W and J_1BBRANCH using standard SAP foreign keys.",
        "tables": ["T001W", "J_1BBRANCH"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    T001W a
JOIN 
    J_1BBRANCH b ON b.BRANCH = a.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join T001W and VTLP (Plants to Transportation Order / Shipment Leg)",
        "business_use_case": "Combine data from T001W and VTLP using standard SAP foreign keys.",
        "tables": ["T001W", "VTLP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    T001W a
JOIN 
    VTLP b ON b.TPLNR = a.WERKS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: BP (23 patterns)
# ======================================================================

BP_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Vendor Master (General Section) (LFA1)",
        "business_use_case": "Basic data retrieval for Vendor Master (General Section)",
        "tables": ["LFA1"],
        "sql": """
SELECT * 
FROM 
    LFA1
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Vendor Master (Bank Details) (LFBK)",
        "business_use_case": "Basic data retrieval for Vendor Master (Bank Details)",
        "tables": ["LFBK"],
        "sql": """
SELECT * 
FROM 
    LFBK
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Business Address Services (Central Address Mgmt) (ADRC)",
        "business_use_case": "Basic data retrieval for Business Address Services (Central Address Mgmt)",
        "tables": ["ADRC"],
        "sql": """
SELECT * 
FROM 
    ADRC
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Business Partner: General Data I (Central BP Master) (BUT000)",
        "business_use_case": "Basic data retrieval for Business Partner: General Data I (Central BP Master)",
        "tables": ["BUT000"],
        "sql": """
SELECT * 
FROM 
    BUT000
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Business Partner: Address Management (BUT020)",
        "business_use_case": "Basic data retrieval for Business Partner: Address Management",
        "tables": ["BUT020"],
        "sql": """
SELECT * 
FROM 
    BUT020
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Business Partner: Customer/Vendor Link (Role Relationships) (BUT050)",
        "business_use_case": "Basic data retrieval for Business Partner: Customer/Vendor Link (Role Relationships)",
        "tables": ["BUT050"],
        "sql": """
SELECT * 
FROM 
    BUT050
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join LFA1 and LFB1 (Vendor Master (General Section) to Vendor Master (Company Code Data))",
        "business_use_case": "Combine data from LFA1 and LFB1 using standard SAP foreign keys.",
        "tables": ["LFA1", "LFB1"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    LFB1 b ON a.LIFNR = b.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join LFA1 and LFBK (Vendor Master (General Section) to Vendor Master (Bank Details))",
        "business_use_case": "Combine data from LFA1 and LFBK using standard SAP foreign keys.",
        "tables": ["LFA1", "LFBK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    LFBK b ON a.LIFNR = b.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join LFA1 and EINA (Vendor Master (General Section) to Purchasing Info Record: General Data)",
        "business_use_case": "Combine data from LFA1 and EINA using standard SAP foreign keys.",
        "tables": ["LFA1", "EINA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    EINA b ON a.LIFNR = b.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and EKKO (Vendor Master (General Section) to Purchasing Document Header)",
        "business_use_case": "Combine data from LFA1 and EKKO using standard SAP foreign keys.",
        "tables": ["LFA1", "EKKO"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    EKKO b ON b.LIFNR = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and EKPO (Vendor Master (General Section) to Purchasing Document Item)",
        "business_use_case": "Combine data from LFA1 and EKPO using standard SAP foreign keys.",
        "tables": ["LFA1", "EKPO"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    EKPO b ON b.LIFNR = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and EKES (Vendor Master (General Section) to Vendor Confirmations (Scheduling Agreements))",
        "business_use_case": "Combine data from LFA1 and EKES using standard SAP foreign keys.",
        "tables": ["LFA1", "EKES"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    EKES b ON b.LIFNR = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and BSIK (Vendor Master (General Section) to Accounting: Secondary Index for Vendors (Open Items))",
        "business_use_case": "Combine data from LFA1 and BSIK using standard SAP foreign keys.",
        "tables": ["LFA1", "BSIK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    BSIK b ON b.LIFNR = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and BSAK (Vendor Master (General Section) to Accounting: Secondary Index for Vendors (Cleared Items))",
        "business_use_case": "Combine data from LFA1 and BSAK using standard SAP foreign keys.",
        "tables": ["LFA1", "BSAK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    BSAK b ON b.LIFNR = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and BSEG (Vendor Master (General Section) to Accounting Document Segment (Line Items))",
        "business_use_case": "Combine data from LFA1 and BSEG using standard SAP foreign keys.",
        "tables": ["LFA1", "BSEG"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    BSEG b ON b.LIFNR = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and QAVE (Vendor Master (General Section) to Usage Decision (Inspection Characteristics))",
        "business_use_case": "Combine data from LFA1 and QAVE using standard SAP foreign keys.",
        "tables": ["LFA1", "QAVE"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    QAVE b ON b.LIFNR = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and BUT000 (Vendor Master (General Section) to Business Partner: General Data I (Central BP Master))",
        "business_use_case": "Combine data from LFA1 and BUT000 using standard SAP foreign keys.",
        "tables": ["LFA1", "BUT000"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    BUT000 b ON b.PARTNER = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and ADRC (Vendor Master (General Section) to Business Address Services (Central Address Mgmt))",
        "business_use_case": "Combine data from LFA1 and ADRC using standard SAP foreign keys.",
        "tables": ["LFA1", "ADRC"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    ADRC b ON a.ADRNR = b.ADDRNUMBER
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and PA0001 (Vendor Master (General Section) to HR Master Record: Organization Assignment)",
        "business_use_case": "Combine data from LFA1 and PA0001 using standard SAP foreign keys.",
        "tables": ["LFA1", "PA0001"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    PA0001 b ON b.PERNR = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFA1 and VTTK (Vendor Master (General Section) to Transportation Order / Shipment Header)",
        "business_use_case": "Combine data from LFA1 and VTTK using standard SAP foreign keys.",
        "tables": ["LFA1", "VTTK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFA1 a
JOIN 
    VTTK b ON b.LIFNR = a.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join ADRC and BUT020 (Business Address Services (Central Address Mgmt) to Business Partner: Address Management)",
        "business_use_case": "Combine data from ADRC and BUT020 using standard SAP foreign keys.",
        "tables": ["ADRC", "BUT020"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    ADRC a
JOIN 
    BUT020 b ON b.ADDRNUMBER = a.ADDRNUMBER
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join ADRC and ILOA (Business Address Services (Central Address Mgmt) to Technical Object Location / Address Assignment)",
        "business_use_case": "Combine data from ADRC and ILOA using standard SAP foreign keys.",
        "tables": ["ADRC", "ILOA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    ADRC a
JOIN 
    ILOA b ON b.ADRNR = a.ADDRNUMBER
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join BUT000 and BUT020 (Business Partner: General Data I (Central BP Master) to Business Partner: Address Management)",
        "business_use_case": "Combine data from BUT000 and BUT020 using standard SAP foreign keys.",
        "tables": ["BUT000", "BUT020"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BUT000 a
JOIN 
    BUT020 b ON a.PARTNER = b.PARTNER
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: FI (34 patterns)
# ======================================================================

FI_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Vendor Master (Company Code Data) (LFB1)",
        "business_use_case": "Basic data retrieval for Vendor Master (Company Code Data)",
        "tables": ["LFB1"],
        "sql": """
SELECT * 
FROM 
    LFB1
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Customer Master (Company Code Data) (KNB1)",
        "business_use_case": "Basic data retrieval for Customer Master (Company Code Data)",
        "tables": ["KNB1"],
        "sql": """
SELECT * 
FROM 
    KNB1
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Accounting Document Header (BKPF)",
        "business_use_case": "Basic data retrieval for Accounting Document Header",
        "tables": ["BKPF"],
        "sql": """
SELECT * 
FROM 
    BKPF
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Accounting Document Segment (Line Items) (BSEG)",
        "business_use_case": "Basic data retrieval for Accounting Document Segment (Line Items)",
        "tables": ["BSEG"],
        "sql": """
SELECT * 
FROM 
    BSEG
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Accounting: Secondary Index for Vendors (Open Items) (BSIK)",
        "business_use_case": "Basic data retrieval for Accounting: Secondary Index for Vendors (Open Items)",
        "tables": ["BSIK"],
        "sql": """
SELECT * 
FROM 
    BSIK
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Accounting: Secondary Index for Vendors (Cleared Items) (BSAK)",
        "business_use_case": "Basic data retrieval for Accounting: Secondary Index for Vendors (Cleared Items)",
        "tables": ["BSAK"],
        "sql": """
SELECT * 
FROM 
    BSAK
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Accounting: Secondary Index for Customers (Open Items) (BSID)",
        "business_use_case": "Basic data retrieval for Accounting: Secondary Index for Customers (Open Items)",
        "tables": ["BSID"],
        "sql": """
SELECT * 
FROM 
    BSID
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Accounting: Secondary Index for Customers (Cleared Items) (BSAD)",
        "business_use_case": "Basic data retrieval for Accounting: Secondary Index for Customers (Cleared Items)",
        "tables": ["BSAD"],
        "sql": """
SELECT * 
FROM 
    BSAD
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Accounting: Secondary Index for G/L Accounts (Cleared Items) (BSAS)",
        "business_use_case": "Basic data retrieval for Accounting: Secondary Index for G/L Accounts (Cleared Items)",
        "tables": ["BSAS"],
        "sql": """
SELECT * 
FROM 
    BSAS
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve G/L Account Master (Chart of Accounts) (SKA1)",
        "business_use_case": "Basic data retrieval for G/L Account Master (Chart of Accounts)",
        "tables": ["SKA1"],
        "sql": """
SELECT * 
FROM 
    SKA1
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve G/L Account Master (Company Code) (SKB1)",
        "business_use_case": "Basic data retrieval for G/L Account Master (Company Code)",
        "tables": ["SKB1"],
        "sql": """
SELECT * 
FROM 
    SKB1
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Company Codes (T001)",
        "business_use_case": "Basic data retrieval for Company Codes",
        "tables": ["T001"],
        "sql": """
SELECT * 
FROM 
    T001
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Asset Master Record (Investment Accounting) (ANLA)",
        "business_use_case": "Basic data retrieval for Asset Master Record (Investment Accounting)",
        "tables": ["ANLA"],
        "sql": """
SELECT * 
FROM 
    ANLA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Asset Accounting Document Line Items (ANEP)",
        "business_use_case": "Basic data retrieval for Asset Accounting Document Line Items",
        "tables": ["ANEP"],
        "sql": """
SELECT * 
FROM 
    ANEP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Valuation Area (Company Code or Plant Level) (T001K)",
        "business_use_case": "Basic data retrieval for Valuation Area (Company Code or Plant Level)",
        "tables": ["T001K"],
        "sql": """
SELECT * 
FROM 
    T001K
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFB1 and EKKO (Vendor Master (Company Code Data) to Purchasing Document Header)",
        "business_use_case": "Combine data from LFB1 and EKKO using standard SAP foreign keys.",
        "tables": ["LFB1", "EKKO"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFB1 a
JOIN 
    EKKO b ON b.LIFNR = a.LIFNR AND b.BUKRS = a.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LFB1 and BSIK (Vendor Master (Company Code Data) to Accounting: Secondary Index for Vendors (Open Items))",
        "business_use_case": "Combine data from LFB1 and BSIK using standard SAP foreign keys.",
        "tables": ["LFB1", "BSIK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LFB1 a
JOIN 
    BSIK b ON b.LIFNR = a.LIFNR AND b.BUKRS = a.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNB1 and VBAK (Customer Master (Company Code Data) to Sales Document Header)",
        "business_use_case": "Combine data from KNB1 and VBAK using standard SAP foreign keys.",
        "tables": ["KNB1", "VBAK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNB1 a
JOIN 
    VBAK b ON b.KUNNR = a.KUNNR AND b.BUKRS = a.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNB1 and VBRK (Customer Master (Company Code Data) to Billing Document Header)",
        "business_use_case": "Combine data from KNB1 and VBRK using standard SAP foreign keys.",
        "tables": ["KNB1", "VBRK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNB1 a
JOIN 
    VBRK b ON b.KUNAG = a.KUNNR AND b.BUKRS = a.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNB1 and BSID (Customer Master (Company Code Data) to Accounting: Secondary Index for Customers (Open Items))",
        "business_use_case": "Combine data from KNB1 and BSID using standard SAP foreign keys.",
        "tables": ["KNB1", "BSID"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNB1 a
JOIN 
    BSID b ON b.KUNNR = a.KUNNR AND b.BUKRS = a.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join BKPF and BSEG (Accounting Document Header to Accounting Document Segment (Line Items))",
        "business_use_case": "Combine data from BKPF and BSEG using standard SAP foreign keys.",
        "tables": ["BKPF", "BSEG"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BKPF a
JOIN 
    BSEG b ON b.BELNR = a.BELNR AND b.GJAHR = a.GJAHR AND b.BUKRS = a.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join BSEG and BSIK (Accounting Document Segment (Line Items) to Accounting: Secondary Index for Vendors (Open Items))",
        "business_use_case": "Combine data from BSEG and BSIK using standard SAP foreign keys.",
        "tables": ["BSEG", "BSIK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BSEG a
JOIN 
    BSIK b ON a.BELNR = b.BELNR AND a.GJAHR = b.GJAHR AND a.BUKRS = b.BUKRS AND a.BUZEI = b.BUZEI
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join BSEG and BSAK (Accounting Document Segment (Line Items) to Accounting: Secondary Index for Vendors (Cleared Items))",
        "business_use_case": "Combine data from BSEG and BSAK using standard SAP foreign keys.",
        "tables": ["BSEG", "BSAK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BSEG a
JOIN 
    BSAK b ON a.BELNR = b.BELNR AND a.GJAHR = b.GJAHR AND a.BUKRS = b.BUKRS AND a.BUZEI = b.BUZEI
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join BSEG and BSID (Accounting Document Segment (Line Items) to Accounting: Secondary Index for Customers (Open Items))",
        "business_use_case": "Combine data from BSEG and BSID using standard SAP foreign keys.",
        "tables": ["BSEG", "BSID"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BSEG a
JOIN 
    BSID b ON a.BELNR = b.BELNR AND a.GJAHR = b.GJAHR AND a.BUKRS = b.BUKRS AND a.BUZEI = b.BUZEI
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join BSEG and BSAS (Accounting Document Segment (Line Items) to Accounting: Secondary Index for G/L Accounts (Cleared Items))",
        "business_use_case": "Combine data from BSEG and BSAS using standard SAP foreign keys.",
        "tables": ["BSEG", "BSAS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BSEG a
JOIN 
    BSAS b ON a.BELNR = b.BELNR AND a.GJAHR = b.GJAHR AND a.BUKRS = b.BUKRS AND a.BUZEI = b.BUZEI
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join BSEG and SKA1 (Accounting Document Segment (Line Items) to G/L Account Master (Chart of Accounts))",
        "business_use_case": "Combine data from BSEG and SKA1 using standard SAP foreign keys.",
        "tables": ["BSEG", "SKA1"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BSEG a
JOIN 
    SKA1 b ON a.HKONT = b.SAKNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join BSEG and T001 (Accounting Document Segment (Line Items) to Company Codes)",
        "business_use_case": "Combine data from BSEG and T001 using standard SAP foreign keys.",
        "tables": ["BSEG", "T001"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BSEG a
JOIN 
    T001 b ON a.BUKRS = b.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join BSIK and T001 (Accounting: Secondary Index for Vendors (Open Items) to Company Codes)",
        "business_use_case": "Combine data from BSIK and T001 using standard SAP foreign keys.",
        "tables": ["BSIK", "T001"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BSIK a
JOIN 
    T001 b ON a.BUKRS = b.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join BSAS and SKA1 (Accounting: Secondary Index for G/L Accounts (Cleared Items) to G/L Account Master (Chart of Accounts))",
        "business_use_case": "Combine data from BSAS and SKA1 using standard SAP foreign keys.",
        "tables": ["BSAS", "SKA1"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    BSAS a
JOIN 
    SKA1 b ON a.HKONT = b.SAKNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join SKA1 and SKB1 (G/L Account Master (Chart of Accounts) to G/L Account Master (Company Code))",
        "business_use_case": "Combine data from SKA1 and SKB1 using standard SAP foreign keys.",
        "tables": ["SKA1", "SKB1"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    SKA1 a
JOIN 
    SKB1 b ON a.SAKNR = b.SAKNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join T001 and T001K (Company Codes to Valuation Area (Company Code or Plant Level))",
        "business_use_case": "Combine data from T001 and T001K using standard SAP foreign keys.",
        "tables": ["T001", "T001K"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    T001 a
JOIN 
    T001K b ON a.BUKRS = b.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join T001 and ANLA (Company Codes to Asset Master Record (Investment Accounting))",
        "business_use_case": "Combine data from T001 and ANLA using standard SAP foreign keys.",
        "tables": ["T001", "ANLA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    T001 a
JOIN 
    ANLA b ON b.BUKRS = a.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join T001 and J_1BBRANCH (Company Codes to India: Branch/Plant Registration for GST)",
        "business_use_case": "Combine data from T001 and J_1BBRANCH using standard SAP foreign keys.",
        "tables": ["T001", "J_1BBRANCH"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    T001 a
JOIN 
    J_1BBRANCH b ON b.BUKRS = a.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join ANLA and ANEP (Asset Master Record (Investment Accounting) to Asset Accounting Document Line Items)",
        "business_use_case": "Combine data from ANLA and ANEP using standard SAP foreign keys.",
        "tables": ["ANLA", "ANEP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    ANLA a
JOIN 
    ANEP b ON b.ANLN1 = a.ANLN1 AND b.BUKRS = a.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: MM-PUR (19 patterns)
# ======================================================================

MM_PUR_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Purchasing Info Record: General Data (EINA)",
        "business_use_case": "Basic data retrieval for Purchasing Info Record: General Data",
        "tables": ["EINA"],
        "sql": """
SELECT * 
FROM 
    EINA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Purchasing Info Record: Purchasing Organization Data (EINE)",
        "business_use_case": "Basic data retrieval for Purchasing Info Record: Purchasing Organization Data",
        "tables": ["EINE"],
        "sql": """
SELECT * 
FROM 
    EINE
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Source List (Vendor-Material-Plant) (EORD)",
        "business_use_case": "Basic data retrieval for Source List (Vendor-Material-Plant)",
        "tables": ["EORD"],
        "sql": """
SELECT * 
FROM 
    EORD
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Purchasing Document Header (EKKO)",
        "business_use_case": "Basic data retrieval for Purchasing Document Header",
        "tables": ["EKKO"],
        "sql": """
SELECT * 
FROM 
    EKKO
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Purchasing Document Item (EKPO)",
        "business_use_case": "Basic data retrieval for Purchasing Document Item",
        "tables": ["EKPO"],
        "sql": """
SELECT * 
FROM 
    EKPO
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Account Assignment (Purchasing Document) (EKKN)",
        "business_use_case": "Basic data retrieval for Account Assignment (Purchasing Document)",
        "tables": ["EKKN"],
        "sql": """
SELECT * 
FROM 
    EKKN
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Vendor Confirmations (Scheduling Agreements) (EKES)",
        "business_use_case": "Basic data retrieval for Vendor Confirmations (Scheduling Agreements)",
        "tables": ["EKES"],
        "sql": """
SELECT * 
FROM 
    EKES
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Purchasing Organizations (T024)",
        "business_use_case": "Basic data retrieval for Purchasing Organizations",
        "tables": ["T024"],
        "sql": """
SELECT * 
FROM 
    T024
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Purchasing Groups (T024E)",
        "business_use_case": "Basic data retrieval for Purchasing Groups",
        "tables": ["T024E"],
        "sql": """
SELECT * 
FROM 
    T024E
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join EINA and EINE (Purchasing Info Record: General Data to Purchasing Info Record: Purchasing Organization Data)",
        "business_use_case": "Combine data from EINA and EINE using standard SAP foreign keys.",
        "tables": ["EINA", "EINE"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EINA a
JOIN 
    EINE b ON a.INFNR = b.INFNR AND a.LIFNR = b.LIFNR AND a.EKORG = b.EKORG
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join EINA and EORD (Purchasing Info Record: General Data to Source List (Vendor-Material-Plant))",
        "business_use_case": "Combine data from EINA and EORD using standard SAP foreign keys.",
        "tables": ["EINA", "EORD"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EINA a
JOIN 
    EORD b ON a.LIFNR = b.LIFNR AND a.MATNR = b.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join EINA and EKPO (Purchasing Info Record: General Data to Purchasing Document Item)",
        "business_use_case": "Combine data from EINA and EKPO using standard SAP foreign keys.",
        "tables": ["EINA", "EKPO"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EINA a
JOIN 
    EKPO b ON b.INFNR = a.INFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join EKKO and EKPO (Purchasing Document Header to Purchasing Document Item)",
        "business_use_case": "Combine data from EKKO and EKPO using standard SAP foreign keys.",
        "tables": ["EKKO", "EKPO"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EKKO a
JOIN 
    EKPO b ON a.EBELN = b.EBELN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join EKKO and EKES (Purchasing Document Header to Vendor Confirmations (Scheduling Agreements))",
        "business_use_case": "Combine data from EKKO and EKES using standard SAP foreign keys.",
        "tables": ["EKKO", "EKES"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EKKO a
JOIN 
    EKES b ON a.EBELN = b.EBELN AND a.LIFNR = b.LIFNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join EKKO and T001 (Purchasing Document Header to Company Codes)",
        "business_use_case": "Combine data from EKKO and T001 using standard SAP foreign keys.",
        "tables": ["EKKO", "T001"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EKKO a
JOIN 
    T001 b ON a.BUKRS = b.BUKRS
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join EKKO and T024 (Purchasing Document Header to Purchasing Organizations)",
        "business_use_case": "Combine data from EKKO and T024 using standard SAP foreign keys.",
        "tables": ["EKKO", "T024"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EKKO a
JOIN 
    T024 b ON a.EKORG = b.EKORG
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join EKKO and QALS (Purchasing Document Header to Inspection Lot Master)",
        "business_use_case": "Combine data from EKKO and QALS using standard SAP foreign keys.",
        "tables": ["EKKO", "QALS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EKKO a
JOIN 
    QALS b ON b.MATNR = a.MATNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join EKKO and DRAD (Purchasing Document Header to Document-Item Assignment (GOS attachments))",
        "business_use_case": "Combine data from EKKO and DRAD using standard SAP foreign keys.",
        "tables": ["EKKO", "DRAD"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EKKO a
JOIN 
    DRAD b ON b.DOKOB = 'BUS2012' AND b.VBELN = a.EBELN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join EKPO and EKKN (Purchasing Document Item to Account Assignment (Purchasing Document))",
        "business_use_case": "Combine data from EKPO and EKKN using standard SAP foreign keys.",
        "tables": ["EKPO", "EKKN"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EKPO a
JOIN 
    EKKN b ON a.EBELN = b.EBELN AND a.EBELP = b.EBELP
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: SD (42 patterns)
# ======================================================================

SD_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Customer Master (General Data) (KNA1)",
        "business_use_case": "Basic data retrieval for Customer Master (General Data)",
        "tables": ["KNA1"],
        "sql": """
SELECT * 
FROM 
    KNA1
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Customer Master (Sales Area Data) (KNVV)",
        "business_use_case": "Basic data retrieval for Customer Master (Sales Area Data)",
        "tables": ["KNVV"],
        "sql": """
SELECT * 
FROM 
    KNVV
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Customer Master Contact Relationships (KNVK)",
        "business_use_case": "Basic data retrieval for Customer Master Contact Relationships",
        "tables": ["KNVK"],
        "sql": """
SELECT * 
FROM 
    KNVK
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Sales Document Header (VBAK)",
        "business_use_case": "Basic data retrieval for Sales Document Header",
        "tables": ["VBAK"],
        "sql": """
SELECT * 
FROM 
    VBAK
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Sales Document Item (VBAP)",
        "business_use_case": "Basic data retrieval for Sales Document Item",
        "tables": ["VBAP"],
        "sql": """
SELECT * 
FROM 
    VBAP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Sales Document: Schedule Line (VBEP)",
        "business_use_case": "Basic data retrieval for Sales Document: Schedule Line",
        "tables": ["VBEP"],
        "sql": """
SELECT * 
FROM 
    VBEP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Sales Document Flow (Document Chain) (VBFA)",
        "business_use_case": "Basic data retrieval for Sales Document Flow (Document Chain)",
        "tables": ["VBFA"],
        "sql": """
SELECT * 
FROM 
    VBFA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Delivery Document Header (LIKP)",
        "business_use_case": "Basic data retrieval for Delivery Document Header",
        "tables": ["LIKP"],
        "sql": """
SELECT * 
FROM 
    LIKP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Delivery Document Item (LIPS)",
        "business_use_case": "Basic data retrieval for Delivery Document Item",
        "tables": ["LIPS"],
        "sql": """
SELECT * 
FROM 
    LIPS
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Billing Document Item (VBRP)",
        "business_use_case": "Basic data retrieval for Billing Document Item",
        "tables": ["VBRP"],
        "sql": """
SELECT * 
FROM 
    VBRP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Billing Document Header (VBRK)",
        "business_use_case": "Basic data retrieval for Billing Document Header",
        "tables": ["VBRK"],
        "sql": """
SELECT * 
FROM 
    VBRK
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Pricing Conditions (Communication) (KONV)",
        "business_use_case": "Basic data retrieval for Pricing Conditions (Communication)",
        "tables": ["KONV"],
        "sql": """
SELECT * 
FROM 
    KONV
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Condition Records: Tax (Customer-Material-Country) (A003)",
        "business_use_case": "Basic data retrieval for Condition Records: Tax (Customer-Material-Country)",
        "tables": ["A003"],
        "sql": """
SELECT * 
FROM 
    A003
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Sales Document Types (T003)",
        "business_use_case": "Basic data retrieval for Sales Document Types",
        "tables": ["T003"],
        "sql": """
SELECT * 
FROM 
    T003
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Sales Document Types (Header) (TVAK)",
        "business_use_case": "Basic data retrieval for Sales Document Types (Header)",
        "tables": ["TVAK"],
        "sql": """
SELECT * 
FROM 
    TVAK
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join KNA1 and KNB1 (Customer Master (General Data) to Customer Master (Company Code Data))",
        "business_use_case": "Combine data from KNA1 and KNB1 using standard SAP foreign keys.",
        "tables": ["KNA1", "KNB1"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    KNB1 b ON a.KUNNR = b.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join KNA1 and KNVV (Customer Master (General Data) to Customer Master (Sales Area Data))",
        "business_use_case": "Combine data from KNA1 and KNVV using standard SAP foreign keys.",
        "tables": ["KNA1", "KNVV"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    KNVV b ON a.KUNNR = b.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join KNA1 and KNVK (Customer Master (General Data) to Customer Master Contact Relationships)",
        "business_use_case": "Combine data from KNA1 and KNVK using standard SAP foreign keys.",
        "tables": ["KNA1", "KNVK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    KNVK b ON a.KUNNR = b.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNA1 and VBAK (Customer Master (General Data) to Sales Document Header)",
        "business_use_case": "Combine data from KNA1 and VBAK using standard SAP foreign keys.",
        "tables": ["KNA1", "VBAK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    VBAK b ON b.KUNNR = a.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNA1 and LIKP (Customer Master (General Data) to Delivery Document Header)",
        "business_use_case": "Combine data from KNA1 and LIKP using standard SAP foreign keys.",
        "tables": ["KNA1", "LIKP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    LIKP b ON b.KUNNR = a.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNA1 and VBRK (Customer Master (General Data) to Billing Document Header)",
        "business_use_case": "Combine data from KNA1 and VBRK using standard SAP foreign keys.",
        "tables": ["KNA1", "VBRK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    VBRK b ON b.KUNAG = a.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNA1 and BSID (Customer Master (General Data) to Accounting: Secondary Index for Customers (Open Items))",
        "business_use_case": "Combine data from KNA1 and BSID using standard SAP foreign keys.",
        "tables": ["KNA1", "BSID"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    BSID b ON b.KUNNR = a.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNA1 and BSEG (Customer Master (General Data) to Accounting Document Segment (Line Items))",
        "business_use_case": "Combine data from KNA1 and BSEG using standard SAP foreign keys.",
        "tables": ["KNA1", "BSEG"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    BSEG b ON b.KUNNR = a.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNA1 and BUT000 (Customer Master (General Data) to Business Partner: General Data I (Central BP Master))",
        "business_use_case": "Combine data from KNA1 and BUT000 using standard SAP foreign keys.",
        "tables": ["KNA1", "BUT000"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    BUT000 b ON b.PARTNER = a.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNA1 and ADRC (Customer Master (General Data) to Business Address Services (Central Address Mgmt))",
        "business_use_case": "Combine data from KNA1 and ADRC using standard SAP foreign keys.",
        "tables": ["KNA1", "ADRC"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    ADRC b ON a.ADRNR = b.ADDRNUMBER
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNA1 and ASMD (Customer Master (General Data) to Service Order / Service Notification)",
        "business_use_case": "Combine data from KNA1 and ASMD using standard SAP foreign keys.",
        "tables": ["KNA1", "ASMD"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    ASMD b ON b.KUNNR = a.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNA1 and EVBS (Customer Master (General Data) to Utilities: Device Installation (Field Service))",
        "business_use_case": "Combine data from KNA1 and EVBS using standard SAP foreign keys.",
        "tables": ["KNA1", "EVBS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNA1 a
JOIN 
    EVBS b ON b.VKONTO = a.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KNVV and VBAK (Customer Master (Sales Area Data) to Sales Document Header)",
        "business_use_case": "Combine data from KNVV and VBAK using standard SAP foreign keys.",
        "tables": ["KNVV", "VBAK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KNVV a
JOIN 
    VBAK b ON b.KUNNR = a.KUNNR AND b.VKORG = a.VKORG AND b.VTWEG = a.VTWEG
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join VBAK and VBAP (Sales Document Header to Sales Document Item)",
        "business_use_case": "Combine data from VBAK and VBAP using standard SAP foreign keys.",
        "tables": ["VBAK", "VBAP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBAK a
JOIN 
    VBAP b ON a.VBELN = b.VBELN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join VBAK and LIKP (Sales Document Header to Delivery Document Header)",
        "business_use_case": "Combine data from VBAK and LIKP using standard SAP foreign keys.",
        "tables": ["VBAK", "LIKP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBAK a
JOIN 
    LIKP b ON a.VBELN = b.VGBEL AND b.VGTYP = 'C'
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join VBAK and VBRK (Sales Document Header to Billing Document Header)",
        "business_use_case": "Combine data from VBAK and VBRK using standard SAP foreign keys.",
        "tables": ["VBAK", "VBRK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBAK a
JOIN 
    VBRK b ON a.VBELN = b.VBELN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join VBAK and VBFA (Sales Document Header to Sales Document Flow (Document Chain))",
        "business_use_case": "Combine data from VBAK and VBFA using standard SAP foreign keys.",
        "tables": ["VBAK", "VBFA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBAK a
JOIN 
    VBFA b ON a.VBELN = b.VBELN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join VBAK and DRAD (Sales Document Header to Document-Item Assignment (GOS attachments))",
        "business_use_case": "Combine data from VBAK and DRAD using standard SAP foreign keys.",
        "tables": ["VBAK", "DRAD"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBAK a
JOIN 
    DRAD b ON b.DOKOB = 'BUS2031' AND b.VBELN = a.VBELN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join VBAK and VTTK (Sales Document Header to Transportation Order / Shipment Header)",
        "business_use_case": "Combine data from VBAK and VTTK using standard SAP foreign keys.",
        "tables": ["VBAK", "VTTK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBAK a
JOIN 
    VTTK b ON b.KUNNR = a.KUNNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join VBAP and VBEP (Sales Document Item to Sales Document: Schedule Line)",
        "business_use_case": "Combine data from VBAP and VBEP using standard SAP foreign keys.",
        "tables": ["VBAP", "VBEP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBAP a
JOIN 
    VBEP b ON a.VBELN = b.VBELN AND a.POSNR = b.POSNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join VBAP and KONV (Sales Document Item to Pricing Conditions (Communication))",
        "business_use_case": "Combine data from VBAP and KONV using standard SAP foreign keys.",
        "tables": ["VBAP", "KONV"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBAP a
JOIN 
    KONV b ON VBAK.KNUMV = b.KNUMV AND a.POSNR = b.KPOSN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join VBAP and VBFA (Sales Document Item to Sales Document Flow (Document Chain))",
        "business_use_case": "Combine data from VBAP and VBFA using standard SAP foreign keys.",
        "tables": ["VBAP", "VBFA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBAP a
JOIN 
    VBFA b ON a.VBELN = b.VBELN AND a.POSNR = b.POSNN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join LIKP and LIPS (Delivery Document Header to Delivery Document Item)",
        "business_use_case": "Combine data from LIKP and LIPS using standard SAP foreign keys.",
        "tables": ["LIKP", "LIPS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LIKP a
JOIN 
    LIPS b ON a.VBELN = b.VBELN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LIKP and VTTK (Delivery Document Header to Transportation Order / Shipment Header)",
        "business_use_case": "Combine data from LIKP and VTTK using standard SAP foreign keys.",
        "tables": ["LIKP", "VTTK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LIKP a
JOIN 
    VTTK b ON b.TKNUM = a.TKNUM
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join LIPS and VBRP (Delivery Document Item to Billing Document Item)",
        "business_use_case": "Combine data from LIPS and VBRP using standard SAP foreign keys.",
        "tables": ["LIPS", "VBRP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LIPS a
JOIN 
    VBRP b ON a.VBELN = b.VBELN AND a.POSNR = b.POSNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join VBRK and BKPF (Billing Document Header to Accounting Document Header)",
        "business_use_case": "Combine data from VBRK and BKPF using standard SAP foreign keys.",
        "tables": ["VBRK", "BKPF"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBRK a
JOIN 
    BKPF b ON a.BELNR = b.BELNR AND a.FKIMG > 0
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join VBRK and BSEG (Billing Document Header to Accounting Document Segment (Line Items))",
        "business_use_case": "Combine data from VBRK and BSEG using standard SAP foreign keys.",
        "tables": ["VBRK", "BSEG"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    VBRK a
JOIN 
    BSEG b ON a.BELNR = b.BELNR AND a.GJAHR = b.GJAHR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: CO (8 patterns)
# ======================================================================

CO_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Cost Center Master (CSKS)",
        "business_use_case": "Basic data retrieval for Cost Center Master",
        "tables": ["CSKS"],
        "sql": """
SELECT * 
FROM 
    CSKS
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Cost Center Group / Cost Element (CSSL)",
        "business_use_case": "Basic data retrieval for Cost Center Group / Cost Element",
        "tables": ["CSSL"],
        "sql": """
SELECT * 
FROM 
    CSSL
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve CO Object: Cost Totals (Actual) (COSP)",
        "business_use_case": "Basic data retrieval for CO Object: Cost Totals (Actual)",
        "tables": ["COSP"],
        "sql": """
SELECT * 
FROM 
    COSP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve CO Object: Cost Totals (Plan) (COSS)",
        "business_use_case": "Basic data retrieval for CO Object: Cost Totals (Plan)",
        "tables": ["COSS"],
        "sql": """
SELECT * 
FROM 
    COSS
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join CSKS and COSP (Cost Center Master to CO Object: Cost Totals (Actual))",
        "business_use_case": "Combine data from CSKS and COSP using standard SAP foreign keys.",
        "tables": ["CSKS", "COSP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    CSKS a
JOIN 
    COSP b ON b.KOSTL = a.KOSTL
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join CSKS and PA0001 (Cost Center Master to HR Master Record: Organization Assignment)",
        "business_use_case": "Combine data from CSKS and PA0001 using standard SAP foreign keys.",
        "tables": ["CSKS", "PA0001"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    CSKS a
JOIN 
    PA0001 b ON a.KOSTL = b.KOSTL
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join COSP and PRPS (CO Object: Cost Totals (Actual) to Work Breakdown Structure (WBS) Element)",
        "business_use_case": "Combine data from COSP and PRPS using standard SAP foreign keys.",
        "tables": ["COSP", "PRPS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    COSP a
JOIN 
    PRPS b ON a.OBJNR = b.OBJNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join COSS and PRPS (CO Object: Cost Totals (Plan) to Work Breakdown Structure (WBS) Element)",
        "business_use_case": "Combine data from COSS and PRPS using standard SAP foreign keys.",
        "tables": ["COSS", "PRPS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    COSS a
JOIN 
    PRPS b ON a.OBJNR = b.OBJNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: QM (9 patterns)
# ======================================================================

QM_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Inspection Lot Master (QALS)",
        "business_use_case": "Basic data retrieval for Inspection Lot Master",
        "tables": ["QALS"],
        "sql": """
SELECT * 
FROM 
    QALS
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Usage Decision (Inspection Characteristics) (QAVE)",
        "business_use_case": "Basic data retrieval for Usage Decision (Inspection Characteristics)",
        "tables": ["QAVE"],
        "sql": """
SELECT * 
FROM 
    QAVE
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Inspection History / Usage Decision Records (QAMV)",
        "business_use_case": "Basic data retrieval for Inspection History / Usage Decision Records",
        "tables": ["QAMV"],
        "sql": """
SELECT * 
FROM 
    QAMV
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Assignment of Task Lists to Materials (MAPL)",
        "business_use_case": "Basic data retrieval for Assignment of Task Lists to Materials",
        "tables": ["MAPL"],
        "sql": """
SELECT * 
FROM 
    MAPL
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Inspection Master Data (Task List - Characteristics) (PLMK)",
        "business_use_case": "Basic data retrieval for Inspection Master Data (Task List - Characteristics)",
        "tables": ["PLMK"],
        "sql": """
SELECT * 
FROM 
    PLMK
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Task List Operations / Process Steps (PLPO)",
        "business_use_case": "Basic data retrieval for Task List Operations / Process Steps",
        "tables": ["PLPO"],
        "sql": """
SELECT * 
FROM 
    PLPO
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join QALS and QAVE (Inspection Lot Master to Usage Decision (Inspection Characteristics))",
        "business_use_case": "Combine data from QALS and QAVE using standard SAP foreign keys.",
        "tables": ["QALS", "QAVE"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    QALS a
JOIN 
    QAVE b ON a.QALS = b.QALS AND a.QUNUM = b.QUNUM
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join MAPL and PLMK (Assignment of Task Lists to Materials to Inspection Master Data (Task List - Characteristics))",
        "business_use_case": "Combine data from MAPL and PLMK using standard SAP foreign keys.",
        "tables": ["MAPL", "PLMK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    MAPL a
JOIN 
    PLMK b ON a.PLNTY = b.PLNTY AND a.PLNNR = b.PLNNR AND a.PLNKN = b.PLNKN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Join PLMK and PLPO (Inspection Master Data (Task List - Characteristics) to Task List Operations / Process Steps)",
        "business_use_case": "Combine data from PLMK and PLPO using standard SAP foreign keys.",
        "tables": ["PLMK", "PLPO"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    PLMK a
JOIN 
    PLPO b ON a.PLNTY = b.PLNTY AND a.PLNNR = b.PLNNR AND a.PLNKN = b.PLNKN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: PS (7 patterns)
# ======================================================================

PS_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Project Definition (PROJ)",
        "business_use_case": "Basic data retrieval for Project Definition",
        "tables": ["PROJ"],
        "sql": """
SELECT * 
FROM 
    PROJ
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Work Breakdown Structure (WBS) Element (PRPS)",
        "business_use_case": "Basic data retrieval for Work Breakdown Structure (WBS) Element",
        "tables": ["PRPS"],
        "sql": """
SELECT * 
FROM 
    PRPS
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Activity at Work Center (Network Node) (AFVC)",
        "business_use_case": "Basic data retrieval for Activity at Work Center (Network Node)",
        "tables": ["AFVC"],
        "sql": """
SELECT * 
FROM 
    AFVC
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Operation/Cost Data for Activities (AFVV)",
        "business_use_case": "Basic data retrieval for Operation/Cost Data for Activities",
        "tables": ["AFVV"],
        "sql": """
SELECT * 
FROM 
    AFVV
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join PROJ and PRPS (Project Definition to Work Breakdown Structure (WBS) Element)",
        "business_use_case": "Combine data from PROJ and PRPS using standard SAP foreign keys.",
        "tables": ["PROJ", "PRPS"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    PROJ a
JOIN 
    PRPS b ON b.PSPHI = a.PSPNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join PRPS and AFVC (Work Breakdown Structure (WBS) Element to Activity at Work Center (Network Node))",
        "business_use_case": "Combine data from PRPS and AFVC using standard SAP foreign keys.",
        "tables": ["PRPS", "AFVC"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    PRPS a
JOIN 
    AFVC b ON b.PROJN = a.PSPNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join AFVC and AFVV (Activity at Work Center (Network Node) to Operation/Cost Data for Activities)",
        "business_use_case": "Combine data from AFVC and AFVV using standard SAP foreign keys.",
        "tables": ["AFVC", "AFVV"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    AFVC a
JOIN 
    AFVV b ON b.NPLNR = a.NPLNR AND b.POSNR = a.POSNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: WM (7 patterns)
# ======================================================================

WM_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Transfer Order Header (LEU4)",
        "business_use_case": "Basic data retrieval for Transfer Order Header",
        "tables": ["LEU4"],
        "sql": """
SELECT * 
FROM 
    LEU4
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Transfer Order Item (Batch-managed) (LTBP)",
        "business_use_case": "Basic data retrieval for Transfer Order Item (Batch-managed)",
        "tables": ["LTBP"],
        "sql": """
SELECT * 
FROM 
    LTBP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Quant (WM) — Physical Stock Record (LQUA)",
        "business_use_case": "Basic data retrieval for Quant (WM) — Physical Stock Record",
        "tables": ["LQUA"],
        "sql": """
SELECT * 
FROM 
    LQUA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Storage Type (Warehouse Management) (LAGP)",
        "business_use_case": "Basic data retrieval for Storage Type (Warehouse Management)",
        "tables": ["LAGP"],
        "sql": """
SELECT * 
FROM 
    LAGP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Storage Bin (Warehouse Management) (LDCP)",
        "business_use_case": "Basic data retrieval for Storage Bin (Warehouse Management)",
        "tables": ["LDCP"],
        "sql": """
SELECT * 
FROM 
    LDCP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LEU4 and VTTK (Transfer Order Header to Transportation Order / Shipment Header)",
        "business_use_case": "Combine data from LEU4 and VTTK using standard SAP foreign keys.",
        "tables": ["LEU4", "VTTK"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LEU4 a
JOIN 
    VTTK b ON a.TKNUM = b.TKNUM
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join LAGP and LDCP (Storage Type (Warehouse Management) to Storage Bin (Warehouse Management))",
        "business_use_case": "Combine data from LAGP and LDCP using standard SAP foreign keys.",
        "tables": ["LAGP", "LDCP"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    LAGP a
JOIN 
    LDCP b ON b.WERKS = a.WERKS AND b.LGTYP = a.LGTYP
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: TM (3 patterns)
# ======================================================================

TM_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Transportation Order / Shipment Header (VTTK)",
        "business_use_case": "Basic data retrieval for Transportation Order / Shipment Header",
        "tables": ["VTTK"],
        "sql": """
SELECT * 
FROM 
    VTTK
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Transportation Order / Shipment Leg (VTLP)",
        "business_use_case": "Basic data retrieval for Transportation Order / Shipment Leg",
        "tables": ["VTLP"],
        "sql": """
SELECT * 
FROM 
    VTLP
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Transportation Order / Shipment Stage (VTFA)",
        "business_use_case": "Basic data retrieval for Transportation Order / Shipment Stage",
        "tables": ["VTFA"],
        "sql": """
SELECT * 
FROM 
    VTFA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: CS (5 patterns)
# ======================================================================

CS_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Service Order / Service Notification (ASMD)",
        "business_use_case": "Basic data retrieval for Service Order / Service Notification",
        "tables": ["ASMD"],
        "sql": """
SELECT * 
FROM 
    ASMD
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Business Partner Relationships (for Service) (IHPA)",
        "business_use_case": "Basic data retrieval for Business Partner Relationships (for Service)",
        "tables": ["IHPA"],
        "sql": """
SELECT * 
FROM 
    IHPA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Document-Item Assignment (GOS attachments) (DRAD)",
        "business_use_case": "Basic data retrieval for Document-Item Assignment (GOS attachments)",
        "tables": ["DRAD"],
        "sql": """
SELECT * 
FROM 
    DRAD
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join ASMD and IHPA (Service Order / Service Notification to Business Partner Relationships (for Service))",
        "business_use_case": "Combine data from ASMD and IHPA using standard SAP foreign keys.",
        "tables": ["ASMD", "IHPA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    ASMD a
JOIN 
    IHPA b ON a.QMNUM = b.OBJNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join IHPA and BUT000 (Business Partner Relationships (for Service) to Business Partner: General Data I (Central BP Master))",
        "business_use_case": "Combine data from IHPA and BUT000 using standard SAP foreign keys.",
        "tables": ["IHPA", "BUT000"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    IHPA a
JOIN 
    BUT000 b ON a.PARNR = b.PARTNER
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: HR (2 patterns)
# ======================================================================

HR_AUTO_PATTERNS = [
    {
        "intent": "Retrieve HR Master Record: Organization Assignment (PA0001)",
        "business_use_case": "Basic data retrieval for HR Master Record: Organization Assignment",
        "tables": ["PA0001"],
        "sql": """
SELECT * 
FROM 
    PA0001
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve HR Master Record: Pay / Wage Type (PA0008)",
        "business_use_case": "Basic data retrieval for HR Master Record: Pay / Wage Type",
        "tables": ["PA0008"],
        "sql": """
SELECT * 
FROM 
    PA0008
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: TAX (2 patterns)
# ======================================================================

TAX_AUTO_PATTERNS = [
    {
        "intent": "Retrieve India: HSN Codes for Materials / SAC Codes for Services (J_1IG_HSN_SAC)",
        "business_use_case": "Basic data retrieval for India: HSN Codes for Materials / SAC Codes for Services",
        "tables": ["J_1IG_HSN_SAC"],
        "sql": """
SELECT * 
FROM 
    J_1IG_HSN_SAC
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve India: Branch/Plant Registration for GST (J_1BBRANCH)",
        "business_use_case": "Basic data retrieval for India: Branch/Plant Registration for GST",
        "tables": ["J_1BBRANCH"],
        "sql": """
SELECT * 
FROM 
    J_1BBRANCH
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: RE (2 patterns)
# ======================================================================

RE_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Real Estate Contract / Rent Index (VIMONI)",
        "business_use_case": "Basic data retrieval for Real Estate Contract / Rent Index",
        "tables": ["VIMONI"],
        "sql": """
SELECT * 
FROM 
    VIMONI
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Real Estate Business Partner Link (VIBDT)",
        "business_use_case": "Basic data retrieval for Real Estate Business Partner Link",
        "tables": ["VIBDT"],
        "sql": """
SELECT * 
FROM 
    VIBDT
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: GTS (2 patterns)
# ======================================================================

GTS_AUTO_PATTERNS = [
    {
        "intent": "Retrieve GTS: Proof of Delivery / Export Control (/SAPSLL/POD)",
        "business_use_case": "Basic data retrieval for GTS: Proof of Delivery / Export Control",
        "tables": ["/SAPSLL/POD"],
        "sql": """
SELECT * 
FROM 
    /SAPSLL/POD
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve GTS: Partner Master Data (Trade Compliance) (/SAPSLL/PNTPR)",
        "business_use_case": "Basic data retrieval for GTS: Partner Master Data (Trade Compliance)",
        "tables": ["/SAPSLL/PNTPR"],
        "sql": """
SELECT * 
FROM 
    /SAPSLL/PNTPR
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: IS-OIL (3 patterns)
# ======================================================================

IS_OIL_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Oil & Gas: Tank Farm / Storage Location Data (OIB_A04)",
        "business_use_case": "Basic data retrieval for Oil & Gas: Tank Farm / Storage Location Data",
        "tables": ["OIB_A04"],
        "sql": """
SELECT * 
FROM 
    OIB_A04
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Oil & Gas: Volume / Measurement Data (OIG_V)",
        "business_use_case": "Basic data retrieval for Oil & Gas: Volume / Measurement Data",
        "tables": ["OIG_V"],
        "sql": """
SELECT * 
FROM 
    OIG_V
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Oil & Gas: Joint Venture Partner Codes (T8JV)",
        "business_use_case": "Basic data retrieval for Oil & Gas: Joint Venture Partner Codes",
        "tables": ["T8JV"],
        "sql": """
SELECT * 
FROM 
    T8JV
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: IS-UTILITY (5 patterns)
# ======================================================================

IS_UTILITY_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Utilities: Device Installation (Field Service) (EVBS)",
        "business_use_case": "Basic data retrieval for Utilities: Device Installation (Field Service)",
        "tables": ["EVBS"],
        "sql": """
SELECT * 
FROM 
    EVBS
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Utilities: Equipment Master (Installation Point) (EANL)",
        "business_use_case": "Basic data retrieval for Utilities: Equipment Master (Installation Point)",
        "tables": ["EANL"],
        "sql": """
SELECT * 
FROM 
    EANL
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Utilities: Device Register / Error Register (EGERR)",
        "business_use_case": "Basic data retrieval for Utilities: Device Register / Error Register",
        "tables": ["EGERR"],
        "sql": """
SELECT * 
FROM 
    EGERR
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join EVBS and EANL (Utilities: Device Installation (Field Service) to Utilities: Equipment Master (Installation Point))",
        "business_use_case": "Combine data from EVBS and EANL using standard SAP foreign keys.",
        "tables": ["EVBS", "EANL"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EVBS a
JOIN 
    EANL b ON a.ANLAGE = b.ANLAGE
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join EVBS and EGERR (Utilities: Device Installation (Field Service) to Utilities: Device Register / Error Register)",
        "business_use_case": "Combine data from EVBS and EGERR using standard SAP foreign keys.",
        "tables": ["EVBS", "EGERR"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    EVBS a
JOIN 
    EGERR b ON b.ANLAGE = a.ANLAGE
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: IS-RETAIL (2 patterns)
# ======================================================================

IS_RETAIL_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Retail: Replenishment Proposal / Buying Line (WRS1)",
        "business_use_case": "Basic data retrieval for Retail: Replenishment Proposal / Buying Line",
        "tables": ["WRS1"],
        "sql": """
SELECT * 
FROM 
    WRS1
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Retail: Assortment Module / Range Planning (SETY)",
        "business_use_case": "Basic data retrieval for Retail: Assortment Module / Range Planning",
        "tables": ["SETY"],
        "sql": """
SELECT * 
FROM 
    SETY
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: IS-HEALTH (3 patterns)
# ======================================================================

IS_HEALTH_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Healthcare: Patient Master / Coverage (NPAT)",
        "business_use_case": "Basic data retrieval for Healthcare: Patient Master / Coverage",
        "tables": ["NPAT"],
        "sql": """
SELECT * 
FROM 
    NPAT
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Healthcare: Care Beneficiary (Insurance/Billing) (NBEW)",
        "business_use_case": "Basic data retrieval for Healthcare: Care Beneficiary (Insurance/Billing)",
        "tables": ["NBEW"],
        "sql": """
SELECT * 
FROM 
    NBEW
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Healthcare: Care Plan / Care Activity Records (NPNZ)",
        "business_use_case": "Basic data retrieval for Healthcare: Care Plan / Care Activity Records",
        "tables": ["NPNZ"],
        "sql": """
SELECT * 
FROM 
    NPNZ
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: LO-VC (6 patterns)
# ======================================================================

LO_VC_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Configuration: Characteristic (Feature) Master (CABN)",
        "business_use_case": "Basic data retrieval for Configuration: Characteristic (Feature) Master",
        "tables": ["CABN"],
        "sql": """
SELECT * 
FROM 
    CABN
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Configuration: Class Master (Product Class) (KLAH)",
        "business_use_case": "Basic data retrieval for Configuration: Class Master (Product Class)",
        "tables": ["KLAH"],
        "sql": """
SELECT * 
FROM 
    KLAH
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Configuration: Configuration (Internal Object Key) (CUOBJ)",
        "business_use_case": "Basic data retrieval for Configuration: Configuration (Internal Object Key)",
        "tables": ["CUOBJ"],
        "sql": """
SELECT * 
FROM 
    CUOBJ
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Allocation: Material to Configuration (Long Text) (INOB)",
        "business_use_case": "Basic data retrieval for Allocation: Material to Configuration (Long Text)",
        "tables": ["INOB"],
        "sql": """
SELECT * 
FROM 
    INOB
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join KLAH and CUOBJ (Configuration: Class Master (Product Class) to Configuration: Configuration (Internal Object Key))",
        "business_use_case": "Combine data from KLAH and CUOBJ using standard SAP foreign keys.",
        "tables": ["KLAH", "CUOBJ"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    KLAH a
JOIN 
    CUOBJ b ON b.CLINT = a.CLINT
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join CUOBJ and INOB (Configuration: Configuration (Internal Object Key) to Allocation: Material to Configuration (Long Text))",
        "business_use_case": "Combine data from CUOBJ and INOB using standard SAP foreign keys.",
        "tables": ["CUOBJ", "INOB"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    CUOBJ a
JOIN 
    INOB b ON b.OBJEK = a.CUOBJ
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

# ======================================================================
# MODULE: PM (6 patterns)
# ======================================================================

PM_AUTO_PATTERNS = [
    {
        "intent": "Retrieve Equipment Master Record (Functional Location/Tech Obj) (IHK6)",
        "business_use_case": "Basic data retrieval for Equipment Master Record (Functional Location/Tech Obj)",
        "tables": ["IHK6"],
        "sql": """
SELECT * 
FROM 
    IHK6
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Equipment Master Data (EQUI)",
        "business_use_case": "Basic data retrieval for Equipment Master Data",
        "tables": ["EQUI"],
        "sql": """
SELECT * 
FROM 
    EQUI
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Fleet / Technical Object Master (IFLOT)",
        "business_use_case": "Basic data retrieval for Fleet / Technical Object Master",
        "tables": ["IFLOT"],
        "sql": """
SELECT * 
FROM 
    IFLOT
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Retrieve Technical Object Location / Address Assignment (ILOA)",
        "business_use_case": "Basic data retrieval for Technical Object Location / Address Assignment",
        "tables": ["ILOA"],
        "sql": """
SELECT * 
FROM 
    ILOA
WHERE 
    MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join IHK6 and EQUI (Equipment Master Record (Functional Location/Tech Obj) to Equipment Master Data)",
        "business_use_case": "Combine data from IHK6 and EQUI using standard SAP foreign keys.",
        "tables": ["IHK6", "EQUI"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    IHK6 a
JOIN 
    EQUI b ON b.EQUNR = a.EQUNR
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
    {
        "intent": "Cross-Module: Join IHK6 and ILOA (Equipment Master Record (Functional Location/Tech Obj) to Technical Object Location / Address Assignment)",
        "business_use_case": "Combine data from IHK6 and ILOA using standard SAP foreign keys.",
        "tables": ["IHK6", "ILOA"],
        "sql": """
SELECT 
    a.*, b.*
FROM 
    IHK6 a
JOIN 
    ILOA b ON a.ILOAN = b.ILOAN
WHERE 
    a.MANDT = '{MANDT}'
LIMIT 100;
"""
    },
]

