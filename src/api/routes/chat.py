import asyncio
import time

from fastapi import APIRouter, Depends

from src.agents.chatbot import GraphRAGWorkflow
from src.api.auth import get_current_user_id
from src.api.dependencies import (
    get_answer_cache,
    get_short_term_memory,
    get_supabase_client,
    get_supabase_logger,
    get_workflow,
)
from src.api.schemas import ChatHistoryResponse, ChatRequest, ChatResponse, MessageOut
from src.cache.answer_cache import AnswerCache
from src.logging_.supabase_logger import SupabaseLogger
from src.memory.short_term import ShortTermMemory

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    user_id: str = Depends(get_current_user_id),
    workflow: GraphRAGWorkflow = Depends(get_workflow),
    cache: AnswerCache = Depends(get_answer_cache),
    short_term_memory: ShortTermMemory = Depends(get_short_term_memory),
    supabase_logger: SupabaseLogger = Depends(get_supabase_logger),
) -> ChatResponse:
    prior_context = await asyncio.to_thread(short_term_memory.load_context, user_id)
    has_prior_context = bool(prior_context) and prior_context != "Không có lịch sử hội thoại."

    if not has_prior_context:
        cached_answer = await cache.get(req.question)
        if cached_answer is not None:
            return ChatResponse(answer=cached_answer, cached=True)

    start = time.time()
    answer = await asyncio.to_thread(
        workflow.process_question,
        question=req.question,
        user_id=user_id,
    )
    processing_time_ms = int((time.time() - start) * 1000)

    if not has_prior_context:
        await cache.set(req.question, answer)

    await asyncio.to_thread(
        supabase_logger.log_interaction,
        user_id=user_id,
        question=req.question,
        answer=answer,
        prompt="",
        processing_time_ms=processing_time_ms,
        success=bool(answer.strip()),
    )
    await asyncio.to_thread(
        supabase_logger.log_message_turn,
        user_id=user_id, role="user", content=req.question,
    )
    await asyncio.to_thread(
        supabase_logger.log_message_turn,
        user_id=user_id, role="assistant", content=answer,
    )

    return ChatResponse(answer=answer, cached=False)


@router.get("/chat/history", response_model=ChatHistoryResponse)
async def chat_history(
    user_id: str = Depends(get_current_user_id),
    supabase_client=Depends(get_supabase_client),
) -> ChatHistoryResponse:
    def _query():
        return (
            supabase_client.table("messages")
            .select("id, role, content, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(50)
            .execute()
        )

    result = await asyncio.to_thread(_query)
    messages = [MessageOut(**row) for row in result.data]
    return ChatHistoryResponse(messages=messages)
