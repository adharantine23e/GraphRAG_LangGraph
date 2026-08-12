import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import redis
import redis.asyncio as aioredis
from fastapi import FastAPI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_neo4j import Neo4jGraph, Neo4jVector
from supabase import create_client

from src.agents.chatbot import GraphRAGWorkflow
from src.api.routes.chat import router as chat_router
from src.api.routes.health import router as health_router
from src.cache.answer_cache import AnswerCache
from src.core.config import get_settings
from src.logging_.supabase_logger import SupabaseLogger
from src.memory.short_term import ShortTermMemory


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    llm = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        temperature=0.7,
        google_api_key=settings.gemini_api,
        max_retries=3,
    )
    graph = Neo4jGraph(
        url=settings.neo4j_uri,
        username=settings.neo4j_username,
        password=settings.neo4j_password,
    )
    embeddings = HuggingFaceEmbeddings(
        model_name=settings.embedding_model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": False},
    )
    vector_index = Neo4jVector.from_existing_graph(
        embeddings,
        search_type="hybrid",
        node_label="Document",
        text_node_properties=["text"],
        embedding_node_property="embedding",
    )

    sync_redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    async_redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    supabase_client = create_client(settings.supabase_url, settings.supabase_service_role_key)

    workflow = GraphRAGWorkflow(llm, graph, vector_index, redis_client=sync_redis)

    app.state.workflow = workflow
    app.state.answer_cache = AnswerCache(async_redis, ttl_seconds=settings.cache_ttl_seconds)
    app.state.short_term_memory = ShortTermMemory(
        sync_redis,
        max_turns=settings.short_term_memory_max_turns,
        ttl_seconds=settings.short_term_memory_ttl_seconds,
    )
    app.state.supabase_client = supabase_client
    app.state.supabase_logger = SupabaseLogger(supabase_client)

    yield

    sync_redis.close()
    await async_redis.aclose()


app = FastAPI(title="GraphRAG Chatbot API", lifespan=lifespan)
app.include_router(chat_router)
app.include_router(health_router)
