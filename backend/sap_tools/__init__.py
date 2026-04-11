"""
sap_tools — SAP Masters Agentic RAG CLI Tools

CLI tools for the 5-Pillar RAG system:
- /ddic       → Schema lookup (Pillar 3)
- /sql-pattern → SQL pattern retrieval (Pillar 4)
- /graph      → Graph traversal (Pillar 5)
- /validate   → SQL validation (Security)
- /execute    → SQL execution (dry-run)
- /mask       → Column masking (Pillar 1)
- /roles      → List all roles
- /domains    → List all domains
- /info       → Role details
- /init       → Initialize all stores

Usage:
    python -m sap_tools --help
    python -m sap_tools /ddic "vendor tables"
    python -m sap_tools /graph LFA1 MARA
"""

from sap_tools.cli import main

__all__ = ["main"]
__version__ = "1.0.0"
