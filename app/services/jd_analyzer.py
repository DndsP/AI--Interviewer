from __future__ import annotations

import re
from collections import OrderedDict

from app.schemas.interview import ResumeProfile
from app.services.resume_parser import COMMON_SKILLS


def _normalize_skill(skill: str) -> str:
    return skill.strip().lower()


def extract_jd_skills(job_description: str) -> list[str]:
    found = []
    for skill in COMMON_SKILLS:
        if re.search(r"\b" + re.escape(skill) + r"\b", job_description, re.I):
            found.append(skill.title() if skill.islower() else skill)
    bullet_like = [
        line.strip(" -•")
        for line in job_description.splitlines()
        if any(token in line.lower() for token in ("experience", "knowledge", "skill", "must", "should"))
    ]
    return list(OrderedDict.fromkeys(found + bullet_like[:8]))


def compare_resume_with_jd(profile: ResumeProfile, job_description: str) -> dict[str, list[str]]:
    jd_skills = extract_jd_skills(job_description)
    resume_skills = {_normalize_skill(skill) for skill in profile.skills}
    matched = [skill for skill in jd_skills if _normalize_skill(skill) in resume_skills]
    missing = [skill for skill in jd_skills if _normalize_skill(skill) not in resume_skills]

    focus_areas = []
    if not profile.projects:
        focus_areas.append("Project depth and ownership examples")
    if any("lead" in item.lower() for item in jd_skills):
        focus_areas.append("Leadership and stakeholder communication")
    if missing:
        focus_areas.extend(f"Gap validation: {skill}" for skill in missing[:4])

    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "additional_focus_areas": list(OrderedDict.fromkeys(focus_areas)),
    }
