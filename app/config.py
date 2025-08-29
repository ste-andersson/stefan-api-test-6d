from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os


class Settings(BaseSettings):
    OPENAI_API_KEY: str
    OPENAI_REALTIME_MODEL: str = "gpt-4o-mini-transcribe"
    LANGUAGE: str = "sv"
    SAMPLE_RATE: int = 16000
    RING_SIZE: int = 200

    # CORS
    ALLOWED_ORIGINS: str = ""  # comma-separated, optional

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def parsed_origins(self) -> List[str]:
        if not self.ALLOWED_ORIGINS:
            return [
                "https://stefan-api-test-6.lovable.app",
                "http://localhost:5173",
                "http://localhost:3000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:3000",
            ]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


settings = Settings()
