from fastapi import APIRouter
from app.api.endpoints import automation, chat, chat_async, eval, ciba

api_router = APIRouter()
# Sync endpoint — original, for backward compatibility and low-latency cases
api_router.include_router(chat.router, tags=["Chat"])
# Async endpoint — Celery-backed, for production horizontal scale
api_router.include_router(chat_async.router, tags=["Chat:Async"])
# Eval Alerting
api_router.include_router(eval.router, tags=["Evaluation"])
# CIBA Approval — async approve/deny for sentinel-blocked queries (Phase 15)
api_router.include_router(ciba.router, tags=["CIBA Approval"])
# Automation surfaces — PR review, doc gardening, observability query interface
api_router.include_router(automation.router, tags=["Automation"])
