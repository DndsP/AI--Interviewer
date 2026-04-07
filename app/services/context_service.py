from __future__ import annotations

from app.schemas.interview import ResumeProfile
from app.services.llm import LLMService


RESUME_COMPRESSION_PROMPT = """You are a resume parser. Given the full resume text below, extract and compress it into a structured summary under 200 words. Focus only on what matters for an interview: skills, experience, education, and notable projects.

Output format (plain text, no markdown):
NAME: ...
EDUCATION: ...
SKILLS: ...
EXPERIENCE: (2-3 bullet points, most recent first)
PROJECTS: (1-2 lines max)
HIGHLIGHTS: (any awards, publications, or standout facts)

Be concise. Omit filler. Preserve specifics like tech stack, years of experience, and measurable outcomes.
"""


JD_COMPRESSION_PROMPT = """You are a job description analyzer. Given the full JD below, extract and compress it into a structured summary under 150 words. Focus only on what an interviewer needs to assess a candidate.

Output format (plain text, no markdown):
ROLE: ...
COMPANY: ...
LEVEL: (entry / mid / senior)
MUST-HAVE SKILLS: ...
GOOD-TO-HAVE SKILLS: ...
KEY RESPONSIBILITIES: (3 bullet points max)
CULTURE/VALUES: (1 line if mentioned)

Remove all boilerplate (equal opportunity statements, benefit lists, etc.). Keep only signal.
"""


class ContextDistillationService:
    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    async def distill(
        self,
        resume_text: str,
        profile: ResumeProfile,
        job_description: str,
        gap_analysis: dict[str, list[str]],
    ) -> dict[str, object]:
        resume_summary = await self.compress_resume(resume_text=resume_text, profile=profile)
        jd_summary = await self.compress_jd(job_description=job_description, gap_analysis=gap_analysis)
        return {
            "candidate_brief": resume_summary,
            "jd_brief": jd_summary,
            "focus_areas": self._focus_areas(profile, gap_analysis),
            "risk_areas": self._risk_areas(gap_analysis),
        }

    async def compress_resume(
        self,
        resume_text: str,
        profile: ResumeProfile,
    ) -> str:
        fallback = self._fallback_resume_summary(profile)
        response = await self.llm_service.chat_json(
            system_prompt=(
                RESUME_COMPRESSION_PROMPT
                + "\nReturn JSON with one key only: summary."
            ),
            user_prompt=f"Resume:\n{resume_text}",
            fallback={"summary": fallback},
            temperature=0.1,
        )
        return str(response.get("summary", fallback)).strip()

    async def compress_jd(
        self,
        job_description: str,
        gap_analysis: dict[str, list[str]],
    ) -> str:
        fallback = self._fallback_jd_summary(job_description, gap_analysis)
        response = await self.llm_service.chat_json(
            system_prompt=(
                JD_COMPRESSION_PROMPT
                + "\nReturn JSON with one key only: summary."
            ),
            user_prompt=f"Job Description:\n{job_description}",
            fallback={"summary": fallback},
            temperature=0.1,
        )
        return str(response.get("summary", fallback)).strip()

    def _focus_areas(
        self,
        profile: ResumeProfile,
        gap_analysis: dict[str, list[str]],
    ) -> list[str]:
        areas = []
        areas.extend(profile.projects[:2])
        areas.extend(gap_analysis.get("additional_focus_areas", [])[:3])
        areas.extend(f"Validate must-have skill: {item}" for item in gap_analysis.get("missing_skills", [])[:2])
        return [item for item in areas if item][:6]

    def _risk_areas(self, gap_analysis: dict[str, list[str]]) -> list[str]:
        return [f"Missing or weak evidence for {item}" for item in gap_analysis.get("missing_skills", [])[:6]]

    def _fallback_resume_summary(self, profile: ResumeProfile) -> str:
        experience_lines = "; ".join(profile.experience[:3]) or "No clear experience extracted."
        project_lines = "; ".join(profile.projects[:2]) or "No clear projects extracted."
        return (
            f"NAME: {profile.candidate_name}\n"
            f"EDUCATION: {'; '.join(profile.education[:2]) or 'Not clearly specified'}\n"
            f"SKILLS: {', '.join(profile.skills[:10]) or 'Not clearly specified'}\n"
            f"EXPERIENCE: {experience_lines}\n"
            f"PROJECTS: {project_lines}\n"
            "HIGHLIGHTS: Resume parsed with fallback summarization."
        )

    def _fallback_jd_summary(self, job_description: str, gap_analysis: dict[str, list[str]]) -> str:
        must_have = ", ".join(gap_analysis.get("matched_skills", [])[:3] + gap_analysis.get("missing_skills", [])[:5])
        return (
            "ROLE: Role details extracted from JD\n"
            "COMPANY: Not clearly specified\n"
            "LEVEL: mid\n"
            f"MUST-HAVE SKILLS: {must_have or 'Not clearly specified'}\n"
            "GOOD-TO-HAVE SKILLS: Not clearly specified\n"
            f"KEY RESPONSIBILITIES: {job_description[:180].strip() or 'Not clearly specified'}\n"
            "CULTURE/VALUES: Not clearly specified"
        )
