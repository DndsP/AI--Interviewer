from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.interview import Answer, Interview, Question
from app.schemas.interview import QuestionPayload
from app.services.question_generator import QuestionGeneratorService
from app.services.report_service import ReportService
from app.services.vector_store import QuestionMemoryStore


class InterviewAgentService:
    def __init__(
        self,
        question_generator: QuestionGeneratorService,
        report_service: ReportService,
        question_store: QuestionMemoryStore,
    ) -> None:
        self.question_generator = question_generator
        self.report_service = report_service
        self.question_store = question_store

    async def seed_questions(self, db: Session, interview: Interview) -> list[Question]:
        interview_payload = self._resume_payload(interview)
        resume_profile = interview_payload["profile"]
        distilled_context = interview_payload.get("distilled_context", {})
        gaps = json.loads(interview.skill_gaps_json)
        questions = await self.question_generator.generate_questions(
            profile=self._profile_from_json(resume_profile),
            job_description=interview.job_description,
            gap_analysis=gaps,
            distilled_context=distilled_context,
        )
        created_questions: list[Question] = []
        for index, item in enumerate(questions, start=1):
            question = Question(
                interview_id=interview.id,
                sequence=index,
                category=item["category"],
                prompt=item["prompt"],
                expected_focus=item["expected_focus"],
                asked_at=None,
                is_follow_up=False,
            )
            db.add(question)
            db.flush()
            self.question_store.add(interview.id, index, item["category"], item["prompt"])
            created_questions.append(question)

        if created_questions:
            interview.current_question_id = created_questions[0].id
            interview.question_count = len(created_questions)
            interview.status = "ready"
            db.add(interview)
            db.commit()
            for question in created_questions:
                db.refresh(question)
        return created_questions

    def get_current_question(self, db: Session, interview: Interview) -> Question:
        question = (
            db.query(Question)
            .filter(Question.id == interview.current_question_id, Question.interview_id == interview.id)
            .one()
        )
        if question.asked_at is None:
            question.asked_at = datetime.utcnow()
            db.add(question)
            db.commit()
            db.refresh(question)
        return question

    async def submit_answer(
        self,
        db: Session,
        interview: Interview,
        question_id: int,
        answer_text: str,
        transcript_source: str,
    ) -> dict:
        question = (
            db.query(Question)
            .filter(Question.id == question_id, Question.interview_id == interview.id)
            .one()
        )
        answer = Answer(
            interview_id=interview.id,
            question_id=question.id,
            content=answer_text.strip(),
            transcript_source=transcript_source,
        )
        db.add(answer)
        db.flush()

        follow_up_generated = False
        action_decision: dict[str, str] | None = None
        if not question.is_follow_up:
            distilled_context = self._interview_context(interview)
            action_decision = await self.question_generator.decide_next_turn(
                question=question.prompt,
                answer=answer.content,
                category=question.category,
                question_number=question.sequence,
                question_bank=self._question_bank(db, interview),
                distilled_context=distilled_context,
            )
            if action_decision["action"] in {"FOLLOWUP", "CLARIFY", "ENCOURAGE"}:
                later_questions = (
                    db.query(Question)
                    .filter(
                        Question.interview_id == interview.id,
                        Question.sequence > question.sequence,
                    )
                    .order_by(Question.sequence.desc())
                    .all()
                )
                for later_question in later_questions:
                    later_question.sequence += 1
                    db.add(later_question)

                next_sequence = question.sequence + 1
                follow_up_question = Question(
                    interview_id=interview.id,
                    sequence=next_sequence,
                    category=question.category,
                    prompt=action_decision["prompt"],
                    expected_focus=action_decision["expected_focus"],
                    is_follow_up=True,
                )
                db.add(follow_up_question)
                db.flush()
                interview.current_question_id = follow_up_question.id
                interview.question_count = (
                    db.query(Question).filter(Question.interview_id == interview.id).count()
                )
                follow_up_generated = True
        if question.is_follow_up or (action_decision and action_decision["action"] == "NEXT_QUESTION") or not follow_up_generated:
            next_question = (
                db.query(Question)
                .filter(
                    Question.interview_id == interview.id,
                    Question.sequence > question.sequence,
                )
                .order_by(Question.sequence.asc())
                .first()
            )
            interview.current_question_id = next_question.id if next_question else None

        if interview.current_question_id is None:
            interview.status = "report_pending"
        else:
            interview.status = "in_progress"

        db.add(interview)
        db.commit()

        next_question_payload = None
        if interview.current_question_id is not None:
            next_question = (
                db.query(Question)
                .filter(Question.id == interview.current_question_id)
                .one()
            )
            next_question_payload = self.to_payload(next_question)

        return {
            "next_question": next_question_payload,
            "follow_up_generated": follow_up_generated,
            "report_ready": interview.current_question_id is None,
        }

    def end_interview(self, db: Session, interview: Interview) -> Interview:
        interview.current_question_id = None
        interview.status = "report_pending"
        db.add(interview)
        db.commit()
        db.refresh(interview)
        return interview

    async def build_report_if_ready(self, db: Session, interview: Interview) -> dict | None:
        if interview.current_question_id is not None and interview.status != "report_pending":
            return None
        return await self.report_service.build_report(db, interview)

    @staticmethod
    def to_payload(question: Question) -> QuestionPayload:
        return QuestionPayload(
            question_id=question.id,
            sequence=question.sequence,
            category=question.category,
            prompt=question.prompt,
            expected_focus=question.expected_focus,
            is_follow_up=question.is_follow_up,
        )

    @staticmethod
    def _profile_from_json(data: dict) -> object:
        from app.schemas.interview import ResumeProfile

        return ResumeProfile(**data)

    @staticmethod
    def _interview_context(interview: Interview) -> dict[str, object]:
        payload = InterviewAgentService._resume_payload(interview)
        return payload.get("distilled_context", {})

    @staticmethod
    def _resume_payload(interview: Interview) -> dict[str, object]:
        payload = json.loads(interview.resume_summary_json)
        if "profile" in payload:
            return payload
        return {"profile": payload, "distilled_context": {}}

    @staticmethod
    def _question_bank(db: Session, interview: Interview) -> list[dict[str, str | int | bool]]:
        questions = (
            db.query(Question)
            .filter(Question.interview_id == interview.id)
            .order_by(Question.sequence.asc())
            .all()
        )
        return [
            {
                "sequence": item.sequence,
                "category": item.category,
                "prompt": item.prompt,
                "is_follow_up": item.is_follow_up,
            }
            for item in questions
        ]
