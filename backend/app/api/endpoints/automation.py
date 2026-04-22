from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.doc_gardening_agent import DocGardeningAgent
from app.core.observability_interface import ObservabilityQueryInterface
from app.core.pr_review_loop import RalphWiggumPRReviewLoop

router = APIRouter(prefix="/automation", tags=["automation"])


class PRReviewRequest(BaseModel):
    pr_title: str
    changed_files: List[str] = Field(default_factory=list)
    diff_summary: str = ""
    tests_added: bool = False
    docs_updated: bool = False
    max_rounds: int = 2


@router.post("/pr-review-loop")
async def run_pr_review_loop(request: PRReviewRequest) -> Dict[str, Any]:
    loop = RalphWiggumPRReviewLoop()
    return loop.iterate_until_stable(
        pr_title=request.pr_title,
        changed_files=request.changed_files,
        diff_summary=request.diff_summary,
        tests_added=request.tests_added,
        docs_updated=request.docs_updated,
        max_rounds=request.max_rounds,
    )


@router.get("/doc-gardening")
async def run_doc_gardening() -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[4]
    agent = DocGardeningAgent(repo_root)
    return agent.scan()


@router.get("/observability/logs")
async def query_logs(logql: str = Query(...), limit: int = Query(default=50, ge=1, le=200)) -> Dict[str, Any]:
    interface = ObservabilityQueryInterface()
    return interface.query_logs(logql, limit=limit)


@router.get("/observability/metrics")
async def query_metrics(promql: str = Query(...)) -> Dict[str, Any]:
    interface = ObservabilityQueryInterface()
    try:
        return interface.query_metrics(promql)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/observability/traces/{run_id}")
async def get_trace(run_id: str) -> Dict[str, Any]:
    interface = ObservabilityQueryInterface()
    try:
        return interface.get_trace(run_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
