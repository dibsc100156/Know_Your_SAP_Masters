from typing import Dict, List

BUSINESS_PARTNER_TABLES = {
    "BUT000": {
        "description": "Business Partner: General Data I. Core table containing partner number, type, and grouping.",
        "columns": [
            {"name": "PARTNER", "type": "NVARCHAR(10)", "desc": "Business Partner Number (Primary Key)"},
            {"name": "TYPE", "type": "NVARCHAR(1)", "desc": "Business Partner Type (1: Person, 2: Organization, 3: Group)"},
            {"name": "BPKIND", "type": "NVARCHAR(4)", "desc": "Business Partner Type (Grouping)"},
            {"name": "BU_GROUP", "type": "NVARCHAR(4)", "desc": "Business Partner Grouping"},
            {"name": "NAME_ORG1", "type": "NVARCHAR(40)", "desc": "Name 1 of organization"},
            {"name": "NAME_ORG2", "type": "NVARCHAR(40)", "desc": "Name 2 of organization"},
            {"name": "NAME_LAST", "type": "NVARCHAR(40)", "desc": "Last name of business partner (person)"},
            {"name": "NAME_FIRST", "type": "NVARCHAR(40)", "desc": "First name of business partner (person)"},
            {"name": "CRDAT", "type": "DATE", "desc": "Date on which the object was created"},
            {"name": "CRUSR", "type": "NVARCHAR(12)", "desc": "User who created the object"},
        ],
        "primary_keys": ["PARTNER"],
        "module": "Cross-Application"
    },
    "LFA1": {
        "description": "Vendor Master (General Section). Legacy vendor table, linked to BP via CVI.",
        "columns": [
            {"name": "LIFNR", "type": "NVARCHAR(10)", "desc": "Account Number of Vendor or Creditor"},
            {"name": "NAME1", "type": "NVARCHAR(35)", "desc": "Name 1"},
            {"name": "ORT01", "type": "NVARCHAR(35)", "desc": "City"},
            {"name": "LAND1", "type": "NVARCHAR(3)", "desc": "Country Key"},
            {"name": "SPRAS", "type": "NVARCHAR(1)", "desc": "Language Key"},
            {"name": "STCD1", "type": "NVARCHAR(16)", "desc": "Tax Number 1"},
        ],
        "primary_keys": ["LIFNR"],
        "module": "MM"
    },
    "KNA1": {
        "description": "General Data in Customer Master. Legacy customer table, linked to BP via CVI.",
        "columns": [
            {"name": "KUNNR", "type": "NVARCHAR(10)", "desc": "Customer Number"},
            {"name": "NAME1", "type": "NVARCHAR(35)", "desc": "Name 1"},
            {"name": "ORT01", "type": "NVARCHAR(35)", "desc": "City"},
            {"name": "LAND1", "type": "NVARCHAR(3)", "desc": "Country Key"},
            {"name": "SPRAS", "type": "NVARCHAR(1)", "desc": "Language Key"},
        ],
        "primary_keys": ["KUNNR"],
        "module": "SD"
    },
    "ADRC": {
        "description": "Addresses (Business Address Services). Contains detailed address information for BPs, Plants, etc.",
        "columns": [
            {"name": "ADDRNUMBER", "type": "NVARCHAR(10)", "desc": "Address number"},
            {"name": "DATE_FROM", "type": "DATE", "desc": "Valid-from date - in current Release only 00010101 possible"},
            {"name": "NATION", "type": "NVARCHAR(1)", "desc": "Version ID for International Addresses"},
            {"name": "NAME1", "type": "NVARCHAR(40)", "desc": "Name 1"},
            {"name": "CITY1", "type": "NVARCHAR(40)", "desc": "City"},
            {"name": "POST_CODE1", "type": "NVARCHAR(10)", "desc": "City postal code"},
            {"name": "STREET", "type": "NVARCHAR(60)", "desc": "Street"},
            {"name": "COUNTRY", "type": "NVARCHAR(3)", "desc": "Country Key"},
            {"name": "REGION", "type": "NVARCHAR(3)", "desc": "Region (State, Province, County)"},
        ],
        "primary_keys": ["ADDRNUMBER", "DATE_FROM", "NATION"],
        "module": "Cross-Application"
    }
}

BUSINESS_PARTNER_SQL_PATTERNS = [
    {
        "intent": "Get basic details for a specific Business Partner including organization name and creation date.",
        "sql": """
SELECT 
    PARTNER, 
    TYPE, 
    NAME_ORG1, 
    NAME_ORG2, 
    CRDAT 
FROM 
    BUT000 
WHERE 
    PARTNER = '{partner_id}';
"""
    },
    {
        "intent": "Find vendors in a specific country and city.",
        "sql": """
SELECT 
    LIFNR, 
    NAME1, 
    ORT01, 
    LAND1 
FROM 
    LFA1 
WHERE 
    LAND1 = '{country_code}' 
    AND ORT01 = '{city_name}';
"""
    },
    {
        "intent": "Get the address details for a Business Partner using the CVI link to LFA1 and ADRC.",
        "sql": """
SELECT 
    bp.PARTNER,
    bp.NAME_ORG1,
    addr.STREET,
    addr.CITY1,
    addr.POST_CODE1,
    addr.COUNTRY
FROM 
    BUT000 bp
JOIN 
    LFA1 ven ON bp.PARTNER = ven.LIFNR  -- Assuming BP and Vendor ID are synchronized (CVI)
JOIN 
    ADRC addr ON ven.ADRNR = addr.ADDRNUMBER
WHERE 
    bp.PARTNER = '{partner_id}';
"""
    }
]
