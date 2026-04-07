from __future__ import annotations

from statistics import mean

from app.services.llm import LLMService


class EvaluationService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    async def evaluate_answer(
        self,
        question: str,
        answer: str,
        expected_focus: str,
        category: str,
        distilled_context: dict[str, object] | None = None,
    ) -> dict[str, float | str]:
        fallback = self._fallback_evaluation(answer)
        response = await self.llm_service.chat_json(
            system_prompt=(
                "You evaluate interview answers. Return JSON with correctness, clarity, depth, "
                "overall, and feedback. Scores must be numbers from 1 to 10."
            ),
            user_prompt=(
                f"Category: {category}\n"
                f"Question: {question}\n"
                f"Expected focus: {expected_focus}\n"
                f"Compact interview context: {self._compact_context(distilled_context)}\n"
                f"Answer: {answer}\n"
                "Provide fair scoring and short actionable feedback."
            ),
            fallback=fallback,
            temperature=0.2,
        )

        normalized = {
            "correctness": float(response.get("correctness", fallback["correctness"])),
            "clarity": float(response.get("clarity", fallback["clarity"])),
            "depth": float(response.get("depth", fallback["depth"])),
            "feedback": str(response.get("feedback", fallback["feedback"])),
        }
        normalized["overall"] = round(
            float(response.get("overall", mean([normalized["correctness"], normalized["clarity"], normalized["depth"]]))),
            2,
        )
        return normalized

    def _fallback_evaluation(self, answer: str) -> dict[str, float | str]:
        word_count = len(answer.split())
        correctness = 7.5 if word_count > 60 else 6.0 if word_count > 25 else 4.5
        clarity = 7.0 if any(token in answer.lower() for token in ("because", "therefore", "result")) else 5.5
        depth = 7.5 if any(token in answer.lower() for token in ("trade-off", "metric", "impact", "latency", "scale")) else 5.0
        overall = round(mean([correctness, clarity, depth]), 2)
        feedback = (
            "Good baseline answer. Add more concrete metrics, deeper technical trade-offs, "
            "and a clearer structure to strengthen it."
        )
        return {
            "correctness": correctness,
            "clarity": clarity,
            "depth": depth,
            "overall": overall,
            "feedback": feedback,
        }

    @staticmethod
    def _compact_context(distilled_context: dict[str, object] | None) -> str:
        if not distilled_context:
            return "No extra distilled context available."
        return (
            f"Candidate brief: {distilled_context.get('candidate_brief', '')}; "
            f"JD brief: {distilled_context.get('jd_brief', '')}; "
            f"Focus areas: {', '.join(distilled_context.get('focus_areas', [])[:4])}; "
            f"Risk areas: {', '.join(distilled_context.get('risk_areas', [])[:4])}"
        )
