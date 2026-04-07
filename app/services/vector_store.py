from __future__ import annotations

from typing import Any


class QuestionMemoryStore:
    """Small abstraction so Chroma stays optional."""

    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []

    def add(self, interview_id: int, sequence: int, category: str, prompt: str) -> None:
        self._entries.append(
            {
                "interview_id": interview_id,
                "sequence": sequence,
                "category": category,
                "prompt": prompt,
            }
        )

    def search(self, interview_id: int) -> list[dict[str, Any]]:
        return [entry for entry in self._entries if entry["interview_id"] == interview_id]
