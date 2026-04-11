from typing import Dict, List, Optional
from pydantic import BaseModel

class SAPAuthContext(BaseModel):
    """
    Represents the simulated SAP Authorization Profile for a given user.
    Dictates which tables, organizational units, and specific fields they can access.
    """
    role_id: str
    description: str
    
    # Pillar 1: Scope Filtering (Row-level access based on Org Structure)
    allowed_company_codes: List[str]  # e.g., BUKRS
    allowed_purchasing_orgs: List[str] # e.g., EKORG
    allowed_plants: List[str]          # e.g., WERKS
    
    # Pillar 1: Authorization Objects (Table-level access)
    denied_tables: List[str]           # e.g., "PAYR" (Payroll)
    
    # Pillar 1: Field-level Masking (Column-level redaction)
    masked_fields: Dict[str, str]      # e.g., {"LFBK-BANKN": "REDACTED", "PA0008-BET01": "REDACTED"}

    def is_table_allowed(self, table: str) -> bool:
        """Check if a table is allowed for this role."""
        return table.upper() not in [t.upper() for t in self.denied_tables]

    def is_column_masked(self, table: str, column: str) -> bool:
        """Check if a column is masked for this role."""
        key1 = f"{table}-{column}".upper()
        key2 = column.upper()
        return any(
            key.upper() in (key1, key2)
            for key in self.masked_fields.keys()
        )

    @property
    def masked_columns(self) -> List[str]:
        """Return flat list of masked column names."""
        return list(self.masked_fields.keys())

    def get_where_clauses(self) -> Dict[str, Dict[str, str]]:
        """
        Build AuthContext WHERE clause filters per table.
        Used by critique_agent and orchestrator for SQL injection.
        """
        filters = {}
        
        if self.allowed_company_codes and "*" not in self.allowed_company_codes:
            filters["LFB1"] = {"BUKRS": "IN"}
            filters["BSIK"] = {"BUKRS": "IN"}
            filters["BSAK"] = {"BUKRS": "IN"}
        
        if self.allowed_purchasing_orgs and "*" not in self.allowed_purchasing_orgs:
            filters["EKKO"] = {"EKORG": "IN"}
            filters["EKPO"] = {"EKORG": "IN"}
        
        if self.allowed_plants and "*" not in self.allowed_plants:
            filters["MARC"] = {"WERKS": "IN"}
            filters["MARD"] = {"WERKS": "IN"}
            filters["MBEW"] = {"WERKS": "IN"}
        
        return filters

# Simulated SAP Role Profiles
SAP_ROLES: Dict[str, SAPAuthContext] = {
    "AP_CLERK": SAPAuthContext(
        role_id="AP_CLERK",
        description="Accounts Payable Clerk - Limited to US Operations",
        allowed_company_codes=["1000", "1010"],  # Only US companies
        allowed_purchasing_orgs=["1000"],
        allowed_plants=["1000", "1010"],
        denied_tables=["PA0008", "PAYR", "MBEW"], # Cannot see HR Payroll or Material Valuation
        masked_fields={
            "LFBK-BANKN": "REDACTED", # Bank Account Number
            "LFBK-BANKK": "REDACTED", # Bank Key
            "LFA1-STCD1": "REDACTED"  # Tax Number 1 (SSN/EIN)
        }
    ),
    "PROCUREMENT_MANAGER_EU": SAPAuthContext(
        role_id="PROCUREMENT_MANAGER_EU",
        description="Procurement Manager - Europe",
        allowed_company_codes=["2000", "2010"], # Only EU companies
        allowed_purchasing_orgs=["2000"],
        allowed_plants=["2000", "2010"],
        denied_tables=["PA0008", "PAYR"],
        masked_fields={} # Managers can see bank details and tax IDs
    ),
    "CFO_GLOBAL": SAPAuthContext(
        role_id="CFO_GLOBAL",
        description="Global Chief Financial Officer",
        allowed_company_codes=["*"],  # All company codes
        allowed_purchasing_orgs=["*"],
        allowed_plants=["*"],
        denied_tables=["PA0008"], # Still cannot see individual HR payroll details
        masked_fields={} # Unrestricted financial view
    ),
    "HR_ADMIN": SAPAuthContext(
        role_id="HR_ADMIN",
        description="Human Resources Administrator",
        allowed_company_codes=["*"],
        allowed_purchasing_orgs=[], # No procurement access
        allowed_plants=["*"],
        denied_tables=["EKKO", "EKPO", "BSEG"], # Cannot see Purchase Orders or Journal Entries
        masked_fields={
            "BUT000-BU_GROUP": "REDACTED" # Cannot see Vendor groupings
        }
    )
}

class SecurityMesh:
    """
    Enforces the SAPAuthContext across the RAG pipeline.
    Intercepts and modifies Contexts, SQL queries, and Final Results.
    """
    
    @staticmethod
    def get_context(role_id: str) -> SAPAuthContext:
        """Fetch the SAP Auth Context for the user's role."""
        if role_id not in SAP_ROLES:
            raise ValueError(f"Unknown role: {role_id}")
        return SAP_ROLES[role_id]

    @staticmethod
    def filter_schema_context(role: SAPAuthContext, retrieved_schemas: List[Dict]) -> List[Dict]:
        """
        Pillar 1 check: Before sending schemas to the LLM, remove any tables the user 
        is explicitly denied from querying via SAP Authorization Objects.
        """
        filtered = []
        for schema in retrieved_schemas:
            table_name = schema["metadata"].get("table", "")
            if table_name in role.denied_tables:
                print(f"SECURITY: Blocking table {table_name} from LLM context (Role: {role.role_id})")
                continue
            filtered.append(schema)
        return filtered

    @staticmethod
    def inject_row_level_filters(role: SAPAuthContext, sql_query: str) -> str:
        """
        Pillar 1 check: The Orchestrator validates the LLM's generated SQL to ensure 
        it includes the necessary WHERE clauses for BUKRS/EKORG/WERKS scope.
        (In a full implementation, this uses an SQL parser like sqlglot to safely inject).
        """
        # A rudimentary check for the scaffold
        if role.allowed_company_codes != ["*"]:
            if "BUKRS" in sql_query.upper() and not any(code in sql_query for code in role.allowed_company_codes):
                 print(f"SECURITY WARNING: Query lacks allowed BUKRS scope for {role.role_id}")
                 # For the scaffold, we just warn. A real system would hard-inject: 
                 # `AND BUKRS IN ('1000', '1010')`
        return sql_query

    @staticmethod
    def mask_result_set(role: SAPAuthContext, table_name: str, results: List[Dict]) -> List[Dict]:
        """
        Pillar 1 check: The final result set from HANA is intercepted before being 
        sent to the user. Columns are redacted according to field-level masking rules.
        """
        if not role.masked_fields:
            return results
            
        masked_results = []
        for row in results:
            masked_row = row.copy()
            for column, value in row.items():
                # Check for "TABLE-FIELD" masking rule
                mask_key = f"{table_name}-{column}".upper()
                if mask_key in role.masked_fields:
                    masked_row[column] = role.masked_fields[mask_key]
            masked_results.append(masked_row)
            
        return masked_results

# Singleton instance
security_mesh = SecurityMesh()

if __name__ == "__main__":
    # Test the mesh
    clerk_role = security_mesh.get_context("AP_CLERK")
    
    # Test Schema Filtering (Should block MBEW)
    mock_schemas = [
        {"metadata": {"table": "LFA1"}, "document": "Vendor Master"},
        {"metadata": {"table": "MBEW"}, "document": "Material Valuation (Denied)"}
    ]
    filtered = security_mesh.filter_schema_context(clerk_role, mock_schemas)
    print(f"Filtered Schemas for AP_CLERK: {[s['metadata']['table'] for s in filtered]}")
    
    # Test Masking
    mock_results = [{"LIFNR": "1000", "STCD1": "999-99-9999", "NAME1": "Acme Corp"}]
    masked = security_mesh.mask_result_set(clerk_role, "LFA1", mock_results)
    print(f"Masked Results for AP_CLERK: {masked}")
