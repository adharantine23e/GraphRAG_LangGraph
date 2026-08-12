import hashlib


class AnswerCache:
    """Redis-backed cache for final chatbot answers, keyed by normalized question text.

    Deliberately excludes user_id/entities from the key so generic questions
    are shared across users. Callers should skip writes/reads when the asking
    user has non-trivial prior conversation context, to avoid serving a
    generic cached answer to a context-dependent follow-up.
    """

    def __init__(self, redis_client, ttl_seconds: int = 86400, key_prefix: str = "answer_cache"):
        self.redis = redis_client
        self.ttl = ttl_seconds
        self.prefix = key_prefix

    def _key(self, question: str) -> str:
        normalized = " ".join(question.lower().split())
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return f"{self.prefix}:{digest}"

    async def get(self, question: str) -> str | None:
        return await self.redis.get(self._key(question))

    async def set(self, question: str, answer: str) -> None:
        if not answer or not answer.strip():
            return
        await self.redis.set(self._key(question), answer, ex=self.ttl)
