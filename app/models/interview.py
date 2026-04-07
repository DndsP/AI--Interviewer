from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    candidate_name: Mapped[str] = mapped_column(String(255), default="Candidate")
    resume_filename: Mapped[str] = mapped_column(String(255))
    resume_text: Mapped[str] = mapped_column(Text)
    job_description: Mapped[str] = mapped_column(Text)
    resume_summary_json: Mapped[str] = mapped_column(Text)
    skill_gaps_json: Mapped[str] = mapped_column(Text)
    strengths_summary: Mapped[str] = mapped_column(Text, default="")
    weaknesses_summary: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(String(80), default="Pending")
    status: Mapped[str] = mapped_column(String(50), default="created")
    current_question_id: Mapped[int | None] = mapped_column(ForeignKey("questions.id"), nullable=True)
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    questions: Mapped[list["Question"]] = relationship(
        "Question",
        back_populates="interview",
        foreign_keys="Question.interview_id",
        cascade="all, delete-orphan",
        order_by="Question.sequence",
    )
    answers: Mapped[list["Answer"]] = relationship(
        "Answer",
        back_populates="interview",
        cascade="all, delete-orphan",
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(50))
    prompt: Mapped[str] = mapped_column(Text)
    expected_focus: Mapped[str] = mapped_column(Text, default="")
    is_follow_up: Mapped[bool] = mapped_column(Boolean, default=False)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    interview: Mapped["Interview"] = relationship(
        "Interview",
        back_populates="questions",
        foreign_keys=[interview_id],
    )
    answers: Mapped[list["Answer"]] = relationship("Answer", back_populates="question")


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    interview_id: Mapped[int] = mapped_column(ForeignKey("interviews.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    content: Mapped[str] = mapped_column(Text)
    transcript_source: Mapped[str] = mapped_column(String(50), default="text")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    interview: Mapped["Interview"] = relationship("Interview", back_populates="answers")
    question: Mapped["Question"] = relationship("Question", back_populates="answers")
    score: Mapped["Score"] = relationship(
        "Score",
        back_populates="answer",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id"), unique=True)
    correctness: Mapped[float] = mapped_column(Float)
    clarity: Mapped[float] = mapped_column(Float)
    depth: Mapped[float] = mapped_column(Float)
    overall: Mapped[float] = mapped_column(Float)
    feedback: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    answer: Mapped["Answer"] = relationship("Answer", back_populates="score")
