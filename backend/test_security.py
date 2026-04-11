import sys
import os

# Ensure the backend directory is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.security import get_user_auth_context
from app.tools.sql_executor import SAPSQLExecutor
import pandas as pd

def test_ap_clerk_access():
    auth = get_user_auth_context("AP_CLERK")
    print(f"\n--- Testing role: {auth.user_id} ({auth.roles[0]}) ---")
    executor = SAPSQLExecutor()
    
    # Simulate a query where AP Clerk looks up a vendor with their bank info
    sql = "SELECT LIFNR, NAME1, LAND1, BANKN, DMBTR FROM LFA1 lfa1 JOIN BSIK bsik ON lfa1.LIFNR=bsik.LIFNR"
    
    try:
        df = executor.execute(sql, auth)
        print("Result:\n", df.to_string())
    except Exception as e:
        print(f"Error: {e}")

def test_procurement_access():
    auth = get_user_auth_context("PROCUREMENT_MGR")
    print(f"\n--- Testing role: {auth.user_id} ({auth.roles[0]}) ---")
    executor = SAPSQLExecutor()
    
    # Try querying a denied table (BSIK for open FI items)
    sql = "SELECT * FROM BSIK"
    try:
        df = executor.execute(sql, auth)
        print("Result:\n", df.to_string())
    except PermissionError as e:
        print(f"Permission Blocked Expectedly: {e}")
        
def test_auditor_masking():
    auth = get_user_auth_context("AUDITOR")
    print(f"\n--- Testing role: {auth.user_id} ({auth.roles[0]}) ---")
    executor = SAPSQLExecutor()
    
    # Simulate an Auditor viewing vendor bank info (should be partially masked)
    sql = "SELECT LIFNR, NAME1, LAND1, BANKN, DMBTR FROM LFA1"
    
    try:
        df = executor.execute(sql, auth)
        print("Result:\n", df.to_string())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_ap_clerk_access()
    test_procurement_access()
    test_auditor_masking()