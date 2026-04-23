"""
SAP Masters Agentic RAG — Backend Application Package

5-Pillar RAG Architecture for SAP S/4 HANA Master Data.
"""

__all__ = ["run_agent_loop"]


def __getattr__(name: str):
    if name == "run_agent_loop":
        from app.agents.orchestrator import run_agent_loop
        return run_agent_loop
    raise AttributeError(name)
