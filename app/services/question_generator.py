from __future__ import annotations

from app.schemas.interview import ResumeProfile
from app.services.llm import LLMService


INTERVIEWER_DECISION_PROMPT = """You are an expert technical interviewer conducting a mock interview for a student. You will be given a compressed resume summary and a compressed job description.

Your job is to simulate a realistic, encouraging interview experience. After each student response, you must decide ONE of the following next actions:

1. NEXT_QUESTION - if the student answered well and you should move to the next prepared question
2. FOLLOWUP - if the answer was vague, incomplete, or interesting enough to dig deeper
3. CLARIFY - if the student seems confused or stuck, gently rephrase or give a small hint
4. ENCOURAGE - if the student is visibly struggling, give a short motivating nudge and simplify

Always reason briefly (internally) about why you chose that action, then respond naturally as a human interviewer would - warm, professional, and adaptive.

Rules:
- Never break character
- Do not reveal your action label to the student
- Keep your tone encouraging but honest
- Track which question number you are on
- If all 6 questions are done, wrap up the interview warmly
"""


QUESTION_GENERATION_PROMPT = """You are a senior technical interviewer. Given the resume summary and JD summary below, generate exactly 6 interview questions tailored to this specific candidate and role.

Question breakdown:
Q1 - Icebreaker / background (easy, builds comfort)
Q2 - Core technical skill from JD (must-have)
Q3 - Project deep-dive from resume (specific to their work)
Q4 - Behavioral / situational (STAR format expected)
Q5 - Problem-solving or system design (role-appropriate difficulty)
Q6 - Motivation / culture fit (why this role, this company)

For each question, also add one line: WHAT TO LISTEN FOR - what a strong answer looks like.

Output as a numbered list. Plain text only.
"""


class QuestionGeneratorService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    async def generate_questions(
        self,
        profile: ResumeProfile,
        job_description: str,
        gap_analysis: dict[str, list[str]],
        distilled_context: dict[str, object] | None = None,
    ) -> list[dict[str, str]]:
        fallback = self._fallback_questions(profile, gap_analysis)
        compact_context = self._compact_context(distilled_context)
        response = await self.llm_service.chat_json(
            system_prompt=(
                QUESTION_GENERATION_PROMPT
                + "\nReturn JSON with one key only: questions. "
                "Each item must include category, prompt, and expected_focus."
            ),
            user_prompt=(
                f"Resume summary:\n{self._resume_summary(distilled_context, profile)}\n\n"
                f"JD summary:\n{self._jd_summary(distilled_context, gap_analysis)}\n\n"
                f"Compact interview context: {compact_context}\n"
                "Return exactly 6 questions."
            ),
            fallback={"questions": fallback},
            temperature=0.5,
        )
        questions = response.get("questions", fallback)
        normalized = []
        for item in questions[:8]:
            normalized.append(
                {
                    "category": item.get("category", "technical"),
                    "prompt": item.get("prompt", "Tell me about your most relevant experience."),
                    "expected_focus": item.get(
                        "expected_focus",
                        "Role relevance, problem solving, and communication.",
                    ),
                }
            )
        return normalized

    async def decide_next_turn(
        self,
        question: str,
        answer: str,
        category: str,
        question_number: int,
        question_bank: list[dict[str, str | int | bool]],
        distilled_context: dict[str, object] | None = None,
    ) -> dict[str, str]:
        resume_summary, jd_summary = self._summaries_from_context(distilled_context)
        compact_bank = [
            {
                "sequence": item.get("sequence"),
                "category": item.get("category"),
                "prompt": item.get("prompt"),
                "is_follow_up": item.get("is_follow_up", False),
            }
            for item in question_bank[:10]
        ]
        fallback = {
            "action": "FOLLOWUP",
            "reason": "The answer could use more depth.",
            "interviewer_message": (
                "Thanks for sharing that. Could you go a bit deeper and walk me through the trade-offs, "
                "impact, or concrete decisions you made?"
            ),
            "expected_focus": "Depth, clarity, impact, and ownership.",
        }
        response = await self.llm_service.chat_json(
            system_prompt=INTERVIEWER_DECISION_PROMPT
            + "\nReturn JSON with these keys only: action, reason, interviewer_message, expected_focus.",
            user_prompt=(
                f"Current resume summary: {resume_summary}\n"
                f"Current JD summary: {jd_summary}\n"
                f"Question bank: {compact_bank}\n"
                f"Current question number: {question_number}\n"
                f"Current question category: {category}\n"
                f"Current question: {question}\n"
                f"Student response: {answer}\n"
                "Decide the next best interviewer move."
            ),
            fallback=fallback,
            temperature=0.3,
        )
        action = str(response.get("action", fallback["action"])).upper().strip()
        if action not in {"NEXT_QUESTION", "FOLLOWUP", "CLARIFY", "ENCOURAGE"}:
            action = fallback["action"]
        return {
            "action": action,
            "reason": str(response.get("reason", fallback["reason"])),
            "prompt": str(response.get("interviewer_message", fallback["interviewer_message"])).strip(),
            "expected_focus": str(response.get("expected_focus", fallback["expected_focus"])),
        }

    def _fallback_questions(
        self,
        profile: ResumeProfile,
        gap_analysis: dict[str, list[str]],
    ) -> list[dict[str, str]]:
        top_project = profile.projects[0] if profile.projects else "a recent project"
        missing = ", ".join(gap_analysis.get("missing_skills", [])[:3]) or "role-critical tools"
        return [
            {
                "category": "technical",
                "prompt": "Let's start with architecture. How would you design and ship a scalable FastAPI service for this role?",
                "expected_focus": "Architecture, APIs, testing, deployment, and trade-offs.",
            },
            {
                "category": "project",
                "prompt": f"I'd love to hear about {top_project}. What was the biggest technical challenge you solved there?",
                "expected_focus": "Ownership, constraints, decisions, and measurable outcomes.",
            },
            {
                "category": "behavioral",
                "prompt": "Can you describe a time you disagreed with a teammate or stakeholder, and how you handled it?",
                "expected_focus": "Communication, collaboration, and conflict resolution.",
            },
            {
                "category": "technical",
                "prompt": f"The job description emphasizes {missing}. How would you go about closing those gaps quickly on the job?",
                "expected_focus": "Learning plan, prioritization, and adaptability.",
            },
            {
                "category": "project",
                "prompt": "Could you share an example where you improved performance, reliability, or developer experience?",
                "expected_focus": "Metrics, root-cause analysis, and long-term thinking.",
            },
            {
                "category": "behavioral",
                "prompt": "What kind of team environment helps you do your best work, and how do you contribute to it?",
                "expected_focus": "Self-awareness, teamwork, and culture add.",
            },
        ]

    @staticmethod
    def _compact_context(distilled_context: dict[str, object] | None) -> str:
        if not distilled_context:
            return "No extra distilled context available."
        focus_areas = ", ".join(distilled_context.get("focus_areas", [])[:4])
        risk_areas = ", ".join(distilled_context.get("risk_areas", [])[:4])
        return (
            f"Candidate brief: {distilled_context.get('candidate_brief', '')}; "
            f"JD brief: {distilled_context.get('jd_brief', '')}; "
            f"Focus areas: {focus_areas}; "
            f"Risk areas: {risk_areas}"
        )

    @staticmethod
    def _summaries_from_context(distilled_context: dict[str, object] | None) -> tuple[str, str]:
        if not distilled_context:
            return ("No compressed resume summary available.", "No compressed JD summary available.")
        return (
            str(distilled_context.get("candidate_brief", "No compressed resume summary available.")),
            str(distilled_context.get("jd_brief", "No compressed JD summary available.")),
        )

    @staticmethod
    def _resume_summary(
        distilled_context: dict[str, object] | None,
        profile: ResumeProfile,
    ) -> str:
        if distilled_context and distilled_context.get("candidate_brief"):
            return str(distilled_context["candidate_brief"])
        return (
            f"NAME: {profile.candidate_name}\n"
            f"EDUCATION: {'; '.join(profile.education[:2]) or 'Not clearly specified'}\n"
            f"SKILLS: {', '.join(profile.skills[:10]) or 'Not clearly specified'}"
        )

    @staticmethod
    def _jd_summary(
        distilled_context: dict[str, object] | None,
        gap_analysis: dict[str, list[str]],
    ) -> str:
        if distilled_context and distilled_context.get("jd_brief"):
            return str(distilled_context["jd_brief"])
        return (
            "ROLE: Role details extracted from JD\n"
            f"MUST-HAVE SKILLS: {', '.join(gap_analysis.get('missing_skills', [])[:5] + gap_analysis.get('matched_skills', [])[:3]) or 'Not clearly specified'}"
        )
