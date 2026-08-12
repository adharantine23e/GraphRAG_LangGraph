import json
import datetime


class ShortTermMemory:
    """Per-user recent-turns store backed by Redis, replacing LangGraph's InMemoryStore.

    Uses a capped list per user (LPUSH/LTRIM) with a refreshed TTL, so context
    is exact-keyed by user_id (not fuzzy-searched) and survives process restarts.
    """

    def __init__(self, redis_client, max_turns: int = 3, ttl_seconds: int = 7 * 24 * 3600):
        self.redis = redis_client
        self.max_turns = max_turns
        self.ttl = ttl_seconds

    def _key(self, user_id: str) -> str:
        return f"chat:recent:{user_id}"

    def load_context(self, user_id: str) -> str:
        if not user_id:
            return ""
        raw_turns = self.redis.lrange(self._key(user_id), 0, self.max_turns - 1)
        if not raw_turns:
            return "Không có lịch sử hội thoại."
        turns = [json.loads(t) for t in raw_turns]
        return "\n".join(
            f"Q: {t['question'][:100]}... A: {t['answer'][:100]}..."
            for t in reversed(turns)
        )

    def store_turn(self, user_id: str, question: str, answer: str, entities: list) -> None:
        if not user_id:
            return
        payload = json.dumps({
            "question": question,
            "answer": answer,
            "entities": entities,
            "timestamp": datetime.datetime.now().isoformat(),
        })
        key = self._key(user_id)
        self.redis.lpush(key, payload)
        self.redis.ltrim(key, 0, self.max_turns - 1)
        self.redis.expire(key, self.ttl)
