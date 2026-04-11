from fastapi import APIRouter
from app.api.endpoints import chat, chat_async, governance

api_router = APIRouter()
# Sync endpoint — original, for backward compatibility and low-latency cases
api_router.include_router(chat.router, tags=["Chat"])
# Async endpoint — Celery-backed, for production horizontal scale
api_router.include_router(chat_async.router, tags=["Chat:Async"])
# LeanIX governance — audit trail, compliance classification, DPO reporting
api_router.include_router(governance.router, tags=["Governance"])
