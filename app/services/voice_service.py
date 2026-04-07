from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from app.core.config import get_settings


@dataclass
class SpeechSynthesisResult:
    content: bytes
    media_type: str


class DeepgramVoiceService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.deepgram_api_key)

    def _headers(self, content_type: str) -> dict[str, str]:
        return {
            "Authorization": f"Token {self.settings.deepgram_api_key}",
            "Content-Type": content_type,
        }

    def live_transcription_url(self) -> str:
        query = urlencode(
            {
                "model": self.settings.deepgram_stt_model,
                "interim_results": "true",
                "punctuate": "true",
                "smart_format": "true",
                "endpointing": "1300",
                "utterance_end_ms": "1900",
                "vad_events": "true",
                "filler_words": "false",
            }
        )
        return f"wss://api.deepgram.com/v1/listen?{query}"

    async def synthesize(self, text: str) -> SpeechSynthesisResult:
        if not self.configured:
            raise HTTPException(status_code=503, detail="Deepgram API key is not configured.")

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.settings.deepgram_base_url}/speak",
                headers=self._headers("application/json"),
                params={"model": self.settings.deepgram_tts_model},
                json={"text": text},
            )
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail="Deepgram TTS request failed.")
            media_type = response.headers.get("content-type", "audio/mpeg")
            return SpeechSynthesisResult(content=response.content, media_type=media_type)

    async def transcribe(self, audio_bytes: bytes, media_type: str) -> str:
        if not self.configured:
            raise HTTPException(status_code=503, detail="Deepgram API key is not configured.")
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio payload is empty.")

        params = {
            "model": self.settings.deepgram_stt_model,
            "smart_format": "true",
            "punctuate": "true",
            "detect_language": "true",
        }

        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                f"{self.settings.deepgram_base_url}/listen",
                headers=self._headers(media_type or "audio/webm"),
                params=params,
                content=audio_bytes,
            )
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail="Deepgram STT request failed.")
            data = response.json()

        try:
            transcript = data["results"]["channels"][0]["alternatives"][0]["transcript"]
        except (KeyError, IndexError, TypeError) as exc:
            raise HTTPException(status_code=502, detail="Deepgram returned an unexpected STT response.") from exc

        return transcript.strip()
