import sys, os, traceback
sys.path.insert(0, r'C:\Users\vishnu\.openclaw\workspace\SAP_HANA_LLM_VendorChatbot\backend')

from app.core.memgraph_adapter import use_memgraph

print("Patching sys.excepthook...")
def hook(exc_type, exc_value, exc_traceback):
    print("FATAL EXCEPTION CAUGHT!")
    traceback.print_exception(exc_type, exc_value, exc_traceback)
sys.excepthook = hook

print("Calling use_memgraph...")
try:
    use_memgraph(uri='bolt://localhost:7687')
    print("SUCCESS")
except Exception as e:
    print(f"Exception raised: {type(e).__name__} - {e}")
    traceback.print_exc()

