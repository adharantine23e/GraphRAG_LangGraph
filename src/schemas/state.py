from typing import List, Tuple, TypedDict, Optional
from dataclasses import dataclass


class GraphRAGState(TypedDict):
    processing_start_time: float
    user_context: str
    user_id: str
    question: str
    chat_history: List[Tuple[str, str]]
    entities: List[str]
    structured_data: str
    relevant_documents: List[str]
    final_prompt: str
    final_answer: str
    curr_agent: str


@dataclass
class PatientInteraction:
    id: str
    timestamp: str
    question: str
    prompt: str
    chatcbot_answers: str
    processing_time: float
    success: bool
    error_message: Optional[str] = None
