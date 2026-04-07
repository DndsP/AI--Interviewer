from __future__ import annotations

import re
from collections import OrderedDict
from pathlib import Path

from pypdf import PdfReader

from app.schemas.interview import ResumeProfile


COMMON_SKILLS = {
    "python",
    "fastapi",
    "django",
    "flask",
    "sql",
    "sqlite",
    "postgresql",
    "mysql",
    "mongodb",
    "redis",
    "docker",
    "kubernetes",
    "aws",
    "azure",
    "gcp",
    "javascript",
    "typescript",
    "react",
    "node.js",
    "node",
    "java",
    "spring",
    "c++",
    "c#",
    "golang",
    "go",
    "machine learning",
    "deep learning",
    "nlp",
    "llm",
    "openai",
    "rag",
    "langchain",
    "pandas",
    "numpy",
    "scikit-learn",
    "tensorflow",
    "pytorch",
    "html",
    "css",
    "git",
    "linux",
    "rest",
    "api",
}

SECTION_PATTERNS = {
    "experience": re.compile(r"^(experience|work experience|professional experience)$", re.I),
    "projects": re.compile(r"^(projects|project experience)$", re.I),
    "education": re.compile(r"^(education|academic background)$", re.I),
    "skills": re.compile(r"^(skills|technical skills|core skills)$", re.I),
}


def extract_text_from_pdf(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _normalize_lines(text: str) -> list[str]:
    return [line.strip(" \t-•") for line in text.splitlines() if line.strip()]


def _extract_candidate_name(lines: list[str]) -> str:
    if not lines:
        return "Candidate"
    first = lines[0]
    if len(first.split()) <= 5 and not re.search(r"resume|curriculum|vitae", first, re.I):
        return first.title()
    return "Candidate"


def _collect_sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"experience": [], "projects": [], "education": [], "skills": []}
    current_section: str | None = None
    for line in lines:
        lowered = line.lower().strip(":")
        matched_section = next(
            (name for name, pattern in SECTION_PATTERNS.items() if pattern.match(lowered)),
            None,
        )
        if matched_section:
            current_section = matched_section
            continue
        if current_section:
            sections[current_section].append(line)
    return sections


def _dedupe(items: list[str]) -> list[str]:
    return list(OrderedDict.fromkeys(item for item in items if item))


def _extract_skills(text: str, section_lines: list[str]) -> list[str]:
    corpus = f"{text}\n" + "\n".join(section_lines)
    hits = []
    for skill in COMMON_SKILLS:
        pattern = r"\b" + re.escape(skill) + r"\b"
        if re.search(pattern, corpus, re.I):
            hits.append(skill.title() if skill.islower() else skill)
    inferred = []
    for fragment in re.split(r"[,|/]", " ".join(section_lines)):
        cleaned = fragment.strip()
        if 1 < len(cleaned) < 40 and re.search(r"[A-Za-z]", cleaned):
            inferred.append(cleaned)
    return _dedupe(hits + inferred[:12])[:20]


def parse_resume(file_path: Path) -> tuple[str, ResumeProfile]:
    text = extract_text_from_pdf(file_path)
    lines = _normalize_lines(text)
    sections = _collect_sections(lines)
    profile = ResumeProfile(
        candidate_name=_extract_candidate_name(lines),
        skills=_extract_skills(text, sections["skills"]),
        experience=_dedupe(sections["experience"])[:8],
        projects=_dedupe(sections["projects"])[:6],
        education=_dedupe(sections["education"])[:4],
        summary=" ".join(lines[:8])[:500],
    )
    return text, profile
