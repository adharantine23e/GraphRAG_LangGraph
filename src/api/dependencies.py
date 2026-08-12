from fastapi import Request

from src.agents.chatbot import GraphRAGWorkflow
from src.cache.answer_cache import AnswerCache
from src.logging_.supabase_logger import SupabaseLogger
from src.memory.short_term import ShortTermMemory


def get_workflow(request: Request) -> GraphRAGWorkflow:
    return request.app.state.workflow


def get_answer_cache(request: Request) -> AnswerCache:
    return request.app.state.answer_cache


def get_supabase_logger(request: Request) -> SupabaseLogger:
    return request.app.state.supabase_logger


def get_short_term_memory(request: Request) -> ShortTermMemory:
    return request.app.state.short_term_memory


def get_supabase_client(request: Request):
    return request.app.state.supabase_client
