import hashlib
import uuid
from datetime import datetime, timezone


class SupabaseLogger:
    """Replaces QuestionLogger's SQLite logging with Supabase Postgres.

    Fixes two bugs present in the original QuestionLogger:
    - success/error_message are now actually persisted (previously always NULL).
    - frequent-question counting is a single atomic upsert (previously a
      read-then-write race that raised a silent NameError on every repeat).
    """

    def __init__(self, supabase_client):
        self.client = supabase_client

    @staticmethod
    def _question_hash(question: str) -> str:
        normalized = " ".join(question.lower().split())
        return hashlib.md5(normalized.encode()).hexdigest()

    def log_interaction(
        self, *, user_id: str, question: str, answer: str, prompt: str,
        processing_time_ms: int, success: bool, error_message: str | None = None,
    ) -> None:
        question_hash = self._question_hash(question)
        try:
            self.client.table("interactions").insert({
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "question": question,
                "question_hash": question_hash,
                "answer": answer,
                "prompt": prompt,
                "processing_time_ms": processing_time_ms,
                "success": success,
                "error_message": error_message,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            self.client.rpc("upsert_frequent_question", {
                "p_question_hash": question_hash,
                "p_sample_question": question,
            }).execute()
        except Exception as e:
            print(f"Error logging interaction to Supabase: {e}")

    def log_message_turn(
        self, *, user_id: str, role: str, content: str, entities: list | None = None,
    ) -> None:
        try:
            self.client.table("messages").insert({
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "role": role,
                "content": content,
                "entities": entities,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            print(f"Error logging message to Supabase: {e}")
