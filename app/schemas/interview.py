from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ResumeProfile(BaseModel):
    candidate_name: str = "Candidate"
    skills: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    summary: str = ""


class UploadResumeResponse(BaseModel):
    interview_id: int
    candidate_name: str
    resume_profile: ResumeProfile
    matched_skills: list[str]
    missing_skills: list[str]
    additional_focus_areas: list[str]


class StartInterviewRequest(BaseModel):
    interview_id: int


class EndInterviewRequest(BaseModel):
    interview_id: int


class QuestionPayload(BaseModel):
    question_id: int
    sequence: int
    category: str
    prompt: str
    expected_focus: str
    is_follow_up: bool = False


class StartInterviewResponse(BaseModel):
    interview_id: int
    status: str
    total_questions: int
    current_question: QuestionPayload
    voice_hint: str


class SubmitAnswerRequest(BaseModel):
    interview_id: int
    question_id: int
    answer: str
    transcript_source: str = "text"
    interrupted: bool = False


class ScorePayload(BaseModel):
    correctness: float
    clarity: float
    depth: float
    overall: float
    feedback: str


class SubmitAnswerResponse(BaseModel):
    interview_id: int
    status: str
    next_question: QuestionPayload | None = None
    follow_up_generated: bool = False
    report_ready: bool = False


class AnswerReport(BaseModel):
    question: str
    category: str
    answer: str
    score: ScorePayload
    created_at: datetime


class FinalReportResponse(BaseModel):
    interview_id: int
    candidate_name: str
    status: str
    strengths: list[str]
    weaknesses: list[str]
    skill_gaps: list[str]
    hiring_recommendation: str
    average_scores: dict[str, float]
    answered_questions: list[AnswerReport]
    report_text: str
