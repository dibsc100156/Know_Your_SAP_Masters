#!/usr/bin/env python3
"""
sap_tools — SAP Masters Agentic RAG CLI Tools

Unified CLI for the 5-Pillar RAG system.
Use: python -m sap_tools <command>

Run without arguments to see full help:
    python -m sap_tools
"""

from sap_tools.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
