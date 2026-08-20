from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    """Return the repository root (three levels above this module)."""
    return Path(__file__).resolve().parents[3]


def _resolve_path(value: Path) -> Path:
    """Make a relative path absolute under the project root."""
    if not value.is_absolute():
        value = project_root() / value
    return value.resolve()


class Settings(BaseSettings):
    """Environment-backed app settings. Secrets stay in SecretStr."""
    model_config = SettingsConfigDict(
        env_file=str(project_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    deepseek_api_key: SecretStr = Field(default=SecretStr(""), validation_alias="DEEPSEEK_API_KEY")
    deepseek_api_base: str | None = Field(default=None, validation_alias="DEEPSEEK_API_BASE")
    chat_model: str = Field(default="deepseek-v4-flash", validation_alias="CHAT_MODEL")

    notes_dir: Path = Path("notes")
    chroma_dir: Path = Path("chromadb_persist")
    chroma_collection: str = "my_knowledge"

    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        validation_alias="EMBEDDING_MODEL",
    )
    embedding_cache_dir: Path = Field(
        default=Path("var/models"),
        validation_alias="EMBEDDING_CACHE_DIR",
    )
    embedding_local_files_only: bool = Field(
        default=False,
        validation_alias="EMBEDDING_LOCAL_FILES_ONLY",
    )

    host: str = "127.0.0.1"
    port: int = 8000
    log_dir: Path = Path("var/logs")
    log_level: str = "DEBUG"

    database_url: str = Field(default="", validation_alias="DATABASE_URL")

    @field_validator(
        "notes_dir",
        "chroma_dir",
        "log_dir",
        "embedding_cache_dir",
        mode="after",
    )
    @classmethod
    def resolve_required_paths(cls, value: Path) -> Path:
        """Normalize configured directories to absolute paths."""
        return _resolve_path(value)
