"""Application settings loaded from environment variables and `.env` files."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
DEFAULT_DB_PATH = BACKEND_DIR / "data" / "mcq_exam.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files take precedence; real environment variables override both.
        env_file=(ROOT_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # OPENAI_KEY is accepted for backwards compatibility with the original project.
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "OPENAI_KEY"),
    )
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = Field(default=0.4, ge=0, le=2)
    openai_timeout_seconds: float = Field(default=90, gt=0)
    openai_max_retries: int = Field(default=2, ge=0, le=5)

    database_url: str = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    max_upload_mb: float = Field(default=5, gt=0)
    max_source_chars: int = Field(default=40_000, ge=1_000)
    max_questions_per_generation: int = Field(default=30, ge=1, le=50)
    # Allowance for network latency when answers/submissions arrive right at the deadline.
    submission_grace_seconds: int = Field(default=10, ge=0, le=120)

    serve_frontend: bool = True
    log_level: str = "INFO"

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def _blank_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def has_openai_key(self) -> bool:
        return self.openai_api_key is not None

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)


@lru_cache
def get_settings() -> Settings:
    return Settings()
