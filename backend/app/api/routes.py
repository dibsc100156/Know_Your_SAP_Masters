from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from app.core.security import get_user_auth_context, SAPAuthContext
from app.agents.orchestrator import run_agent_loop

router = APIRouter()

class ChatRequest(BaseModel):
    user_role: str = Field(..., description="SAP Role Key (e.g., AP_CLERK, PROCUREMENT_MGR, AUDITOR, CFO)")
    question: str = Field(..., description="The natural language question about vendor data.")

class ChatResponse(BaseModel):
    user_id: str
    role_applied: str
    question: str
    answer: str
    tables_used: List[str]
    executed_sql: Optional[str] = None
    data: Optional[List[dict]] = None
    masked_columns: List[str] = []

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Main entrypoint for the Vendor Chatbot.
    1. Fetches the SAP AuthContext for the provided role.
    2. Invokes the Agentic Orchestrator with the user's question and strict limits.
    3. Returns the answer, role-filtered data, and execution context.
    """
    try:
        # Step 1: Role-Aware RAG - Get Identity & Auth Context
        auth_context = get_user_auth_context(request.user_role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        # Step 2 & 3: Agentic Loop & Schema RAG
        # Pass the context into the Orchestrator
        result = run_agent_loop(request.question, auth_context)
        
        return ChatResponse(
            user_id=auth_context.user_id,
            role_applied=auth_context.roles[0],
            question=request.question,
            answer=result.get("answer", "I could not generate an answer."),
            tables_used=result.get("tables_used", []),
            executed_sql=result.get("executed_sql"),
            data=result.get("data", []),
            masked_columns=auth_context.masked_columns
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent Error: {str(e)}")