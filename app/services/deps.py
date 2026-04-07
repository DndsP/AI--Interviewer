from functools import lru_cache

from app.services.context_service import ContextDistillationService
from app.services.interview_agent import InterviewAgentService
from app.services.llm import LLMService
from app.services.question_generator import QuestionGeneratorService
from app.services.report_service import ReportService
from app.services.vector_store import QuestionMemoryStore
from app.services.voice_service import DeepgramVoiceService


@lru_cache
def get_llm_service() -> LLMService:
    return LLMService()


@lru_cache
def get_question_store() -> QuestionMemoryStore:
    return QuestionMemoryStore()


@lru_cache
def get_interview_agent() -> InterviewAgentService:
    llm_service = get_llm_service()
    return InterviewAgentService(
        question_generator=QuestionGeneratorService(llm_service),
        report_service=ReportService(llm_service),
        question_store=get_question_store(),
    )


@lru_cache
def get_voice_service() -> DeepgramVoiceService:
    return DeepgramVoiceService()


@lru_cache
def get_context_service() -> ContextDistillationService:
    return ContextDistillationService(get_llm_service())
