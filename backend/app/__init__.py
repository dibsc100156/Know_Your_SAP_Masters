"""
SAP Masters Agentic RAG — Backend Application Package

5-Pillar RAG Architecture for SAP S/4 HANA Master Data.
"""
from app.agents.orchestrator import run_agent_loop

__all__ = ["run_agent_loop"]
