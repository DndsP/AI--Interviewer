from __future__ import annotations

import json
from statistics import mean

from sqlalchemy.orm import Session, joinedload

from app.models.interview import Answer, Interview, Question, Score
from app.services.evaluator import EvaluationService
from app.services.llm import LLMService


FINAL_REPORT_PROMPT = """You are an expert interview coach. Given the full interview transcript, the resume summary, and the JD summary below, generate a detailed feedback report for the student.

Structure the report exactly as follows:

---
INTERVIEW FEEDBACK REPORT
---

OVERALL SCORE: X/10
HIRING RECOMMENDATION: Strong Yes / Yes / Maybe / No (with 1-line reason)

METRICS:
- Communication clarity: X/10
- Technical depth: X/10
- Structured thinking: X/10
- Confidence & presence: X/10
- Relevance of answers: X/10

STRENGTHS: (3-4 bullet points - specific moments from the interview)

AREAS TO WORK ON: (3-4 bullet points - specific gaps, not generic advice)

QUESTION-BY-QUESTION BREAKDOWN:
For each question: what they said (1 line summary), what was good, what was missing.

RESOURCES TO IMPROVE:
For each weak area identified, suggest 1-2 specific free resources (courses, books, practice sites, YouTube channels) with a 1-line description of why that resource helps.

NEXT STEPS: 3 concrete actions the student should take before their next interview.
"""


class ReportService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service
        self.evaluation_service = EvaluationService(llm_service)

    async def build_report(self, db: Session, interview: Interview) -> dict:
        hydrated = (
            db.query(Interview)
            .options(
                joinedload(Interview.answers).joinedload(Answer.score),
                joinedload(Interview.questions),
            )
            .filter(Interview.id == interview.id)
            .one()
        )
        await self._evaluate_answers_if_missing(db, hydrated)
        db.refresh(hydrated)
        answers = hydrated.answers
        resume_payload = self._resume_payload(hydrated)
        distilled_context = resume_payload.get("distilled_context", {})
        gap_data = json.loads(hydrated.skill_gaps_json or "{}")
        gaps = gap_data.get("missing_skills", [])
        score_rows = [answer.score for answer in answers if answer.score]
        average_scores = {
            "correctness": round(mean([score.correctness for score in score_rows]), 2) if score_rows else 0.0,
            "clarity": round(mean([score.clarity for score in score_rows]), 2) if score_rows else 0.0,
            "depth": round(mean([score.depth for score in score_rows]), 2) if score_rows else 0.0,
            "overall": round(mean([score.overall for score in score_rows]), 2) if score_rows else 0.0,
        }
        fallback = self._fallback_report(hydrated, gaps, average_scores)
        response = await self.llm_service.chat_json(
            system_prompt=(
                FINAL_REPORT_PROMPT
                + "\nReturn JSON with these keys only: strengths, weaknesses, hiring_recommendation, report_text."
            ),
            user_prompt=(
                f"Resume summary: {distilled_context.get('candidate_brief', '')}\n"
                f"JD summary: {distilled_context.get('jd_brief', '')}\n"
                f"Full interview transcript: {self._transcript_text(hydrated)}\n"
            ),
            fallback=fallback,
            temperature=0.3,
        )
        hydrated.strengths_summary = "\n".join(response.get("strengths", fallback["strengths"]))
        hydrated.weaknesses_summary = "\n".join(response.get("weaknesses", fallback["weaknesses"]))
        hydrated.recommendation = response.get("hiring_recommendation", fallback["hiring_recommendation"])
        hydrated.status = "completed"
        db.add(hydrated)
        db.commit()
        db.refresh(hydrated)

        question_lookup = {question.id: question for question in hydrated.questions}
        answered_questions = []
        for answer in answers:
            if not answer.score:
                continue
            question: Question | None = question_lookup.get(answer.question_id)
            answered_questions.append(
                {
                    "question": question.prompt if question else "",
                    "category": question.category if question else "unknown",
                    "answer": answer.content,
                    "score": {
                        "correctness": answer.score.correctness,
                        "clarity": answer.score.clarity,
                        "depth": answer.score.depth,
                        "overall": answer.score.overall,
                        "feedback": answer.score.feedback,
                    },
                    "created_at": answer.created_at,
                }
            )

        return {
            "interview_id": hydrated.id,
            "candidate_name": hydrated.candidate_name,
            "status": hydrated.status,
            "strengths": [item for item in hydrated.strengths_summary.splitlines() if item],
            "weaknesses": [item for item in hydrated.weaknesses_summary.splitlines() if item],
            "skill_gaps": gaps,
            "hiring_recommendation": hydrated.recommendation,
            "average_scores": average_scores,
            "answered_questions": answered_questions,
            "report_text": str(response.get("report_text", fallback["report_text"])),
        }

    async def _evaluate_answers_if_missing(self, db: Session, interview: Interview) -> None:
        question_lookup = {question.id: question for question in interview.questions}
        resume_payload = self._resume_payload(interview)
        distilled_context = resume_payload.get("distilled_context", {})
        changed = False
        for answer in interview.answers:
            if answer.score:
                continue
            question = question_lookup.get(answer.question_id)
            if not question:
                continue
            evaluation = await self.evaluation_service.evaluate_answer(
                question=question.prompt,
                answer=answer.content,
                expected_focus=question.expected_focus,
                category=question.category,
                distilled_context=distilled_context,
            )
            db.add(
                Score(
                    answer_id=answer.id,
                    correctness=evaluation["correctness"],
                    clarity=evaluation["clarity"],
                    depth=evaluation["depth"],
                    overall=evaluation["overall"],
                    feedback=evaluation["feedback"],
                )
            )
            changed = True
        if changed:
            db.commit()

    @staticmethod
    def _resume_payload(interview: Interview) -> dict[str, object]:
        payload = json.loads(interview.resume_summary_json)
        if "profile" in payload:
            return payload
        return {"profile": payload, "distilled_context": {}}

    def _fallback_report(
        self,
        interview: Interview,
        skill_gaps: list[str],
        average_scores: dict[str, float],
    ) -> dict:
        strengths = [
            "Demonstrated relevant technical grounding and communicated ideas clearly.",
            "Provided examples that connected prior work to the target role.",
        ]
        weaknesses = [
            "Some answers could go deeper on measurable impact and design trade-offs.",
            "Needs stronger evidence around the missing job-description skills.",
        ]
        recommendation = "Proceed to next round" if average_scores["overall"] >= 6.5 else "Hold"
        report_text = (
            "---\n"
            "INTERVIEW FEEDBACK REPORT\n"
            "---\n\n"
            f"OVERALL SCORE: {average_scores['overall']}/10\n"
            f"HIRING RECOMMENDATION: {recommendation} - Based on the overall interview performance.\n\n"
            "METRICS:\n"
            f"- Communication clarity: {average_scores['clarity']}/10\n"
            f"- Technical depth: {average_scores['depth']}/10\n"
            f"- Structured thinking: {average_scores['overall']}/10\n"
            f"- Confidence & presence: {average_scores['clarity']}/10\n"
            f"- Relevance of answers: {average_scores['correctness']}/10\n\n"
            "STRENGTHS:\n"
            + "\n".join(f"- {item}" for item in strengths)
            + "\n\nAREAS TO WORK ON:\n"
            + "\n".join(f"- {item}" for item in weaknesses[:4])
            + "\n\nQUESTION-BY-QUESTION BREAKDOWN:\nSee per-answer feedback below.\n\n"
            "RESOURCES TO IMPROVE:\n- Use free interview practice platforms and role-specific tutorials.\n\n"
            "NEXT STEPS:\n1. Practice concise STAR answers.\n2. Add measurable impact to examples.\n3. Rehearse role-specific technical explanations."
        )
        return {
            "strengths": strengths,
            "weaknesses": weaknesses + ([f"Skill gaps still to validate: {', '.join(skill_gaps[:4])}"] if skill_gaps else []),
            "hiring_recommendation": recommendation,
            "summary": interview.candidate_name,
            "report_text": report_text,
        }

    @staticmethod
    def _transcript_text(interview: Interview) -> str:
        question_lookup = {question.id: question for question in interview.questions}
        transcript_parts = []
        for index, answer in enumerate(interview.answers, start=1):
            question = question_lookup.get(answer.question_id)
            transcript_parts.append(f"Q{index}: {question.prompt if question else ''}")
            transcript_parts.append(f"A{index}: {answer.content}")
        return "\n".join(transcript_parts)
