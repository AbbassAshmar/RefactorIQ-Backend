import json
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.constants import DEFAULT_GEMINI_MODEL
from app.core.path_utils import resolve_scan_repo_base_dir


BASE_DIR = Path(__file__).resolve().parents[1]


def _resolve_env_file() -> str:
    return str(BASE_DIR / ".env.development")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore", 
    )

    # Database for your app
    APP_DATABASE_URL: str

    # Security
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ENCRYPTION_KEY: str
    RESET_DB_ON_STARTUP: bool = True

    # GitHub OAuth
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str
    GITHUB_REDIRECT_URI: str

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Application
    APP_NAME: str = "RefactorIQ"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"
    LOG_FILE_NAME: str = "app.log"

    # Admin seeder
    ADMIN_EMAIL: str
    ADMIN_USERNAME: str
    ADMIN_PASSWORD: str

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # Scan workspace
    SCAN_REPO_BASE_DIR: Path

    # Code embeddings
    CODE_EMBEDDING_MODEL_ID: str = "Salesforce/SFR-Embedding-Code-400M_R"
    CODE_EMBEDDING_MODEL_PATH: Path | None = None
    CODE_EMBEDDING_LOCAL_FILES_ONLY: bool = False
    CODE_EMBEDDING_BATCH_SIZE: int = 8
    CODE_EMBEDDING_DEVICE: str | None = None
    CODE_EMBEDDING_MAX_LENGTH: int = 8192
    CODE_EMBEDDING_TRUST_REMOTE_CODE: bool = True

    # LLM provider
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = DEFAULT_GEMINI_MODEL

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("SCAN_REPO_BASE_DIR", mode="before")
    @classmethod
    def parse_scan_repo_base_dir(cls, v: Path | str) -> Path:
        return resolve_scan_repo_base_dir(v, base_dir=BASE_DIR)

    @field_validator("CODE_EMBEDDING_MODEL_PATH", mode="before")
    @classmethod
    def parse_code_embedding_model_path(cls, v: Path | str | None) -> Path | None:
        if v is None or v == "":
            return None

        path = Path(v)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path.resolve()

settings = Settings()
