from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "AI Interview System"
    app_env: str = "development"
    debug: bool = True
    deepgram_api_key: str = Field(default="", alias="DEEPGRAM_API_KEY")
    deepgram_stt_model: str = "nova-3"
    deepgram_tts_model: str = "aura-2-thalia-en"
    deepgram_base_url: str = "https://api.deepgram.com/v1"
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    app_url: str = "http://localhost:8000"
    sqlite_url: str = f"sqlite:///{(BASE_DIR / 'storage' / 'app.db').as_posix()}"
    upload_dir: Path = BASE_DIR / "storage" / "resumes"
    chroma_dir: Path = BASE_DIR / "storage" / "chroma"
    use_chroma: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_dir.mkdir(parents=True, exist_ok=True)
    return settings
