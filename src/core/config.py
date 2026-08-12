from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Neo4j
    neo4j_uri: str
    neo4j_username: str
    neo4j_password: str

    # LLM
    gemini_api: str
    gemini_model: str = "gemini-2.0-flash"

    # Embedding model
    embedding_model_name: str = "keepitreal/vietnamese-sbert"

    # Redis
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 86400
    short_term_memory_ttl_seconds: int = 7 * 24 * 3600
    short_term_memory_max_turns: int = 3

    # Supabase
    supabase_url: str
    supabase_service_role_key: str
    supabase_jwt_secret: str

    # App
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
