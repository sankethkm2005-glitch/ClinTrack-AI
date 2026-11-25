"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Central configuration for the ClinTrace AI backend."""

    APP_NAME: str = "ClinTrace AI"
    APP_ENV: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "dev-only-change-before-production"

    # Database
    DATABASE_URL: str = "sqlite:///./clintrace.db"

    # Session & Cookies
    SESSION_COOKIE_NAME: str = "clintrace_session"
    SESSION_EXPIRE_MINUTES: int = 1440
    COOKIE_SECURE: bool = False

    # Private document storage (relative to backend/ unless absolute)
    UPLOAD_DIR: str = "storage/uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # AI Provider configuration (provider-independent)
    AI_PROVIDER: str = "grok"
    AI_MODEL: str = "grok-3-mini"
    AI_API_KEY: str = ""
    AI_BASE_URL: str = "https://api.x.ai/v1"
    AI_TIMEOUT_SECONDS: int = 60

    # Optional OCR binary override
    TESSERACT_CMD: str = ""

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def resolved_database_url(self) -> str:
        """Resolve relative SQLite paths against backend/ so CWD does not matter."""
        prefix = "sqlite:///./"
        if self.DATABASE_URL.startswith(prefix):
            rel_path = self.DATABASE_URL[len(prefix):]
            return f"sqlite:///{(BACKEND_DIR / rel_path).as_posix()}"
        return self.DATABASE_URL

    @property
    def resolved_upload_dir(self) -> Path:
        """Return absolute path to private upload storage outside frontend/."""
        path = Path(self.UPLOAD_DIR)
        if not path.is_absolute():
            path = BACKEND_DIR / path
        return path.resolve()


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()


settings = get_settings()
