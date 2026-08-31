from pathlib import Path    #路径解析模块Path

from pydantic import Field, SecretStr, field_validator  #数据校验模块
from pydantic_settings import BaseSettings, SettingsConfigDict


def project_root() -> Path:
    """Return the repository root (three levels above this module)."""
    return Path(__file__).resolve().parents[3]      ##获取项目根目录


def _resolve_path(value: Path) -> Path:
    """Make a relative path absolute under the project root."""
    if not value.is_absolute(): #获取绝对路径
        value = project_root() / value
    return value.resolve()  #依旧层层跟踪获取最终的绝对路径


class Settings(BaseSettings):
    """Environment-backed app settings. Secrets stay in SecretStr."""
    model_config = SettingsConfigDict(
        env_file=str(project_root() / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )      #get relative enviroment settings from projectroot/.env

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

    database_url: str = Field(default="", validation_alias="DATABASE_URL")  #默认数据库连接的URL为空

    # 上下文压缩与 stub 截断相关（token 估算用字符/4）。禁止在 compact/agent 里写死这些数字。
    chat_context_window: int = Field(default=32768, validation_alias="CHAT_CONTEXT_WINDOW")
    context_trigger_ratio: float = Field(default=0.8, validation_alias="CONTEXT_TRIGGER_RATIO")
    context_target_ratio: float = Field(default=0.6, validation_alias="CONTEXT_TARGET_RATIO")
    context_stub_preview_tokens: int = Field(default=1000, validation_alias="CONTEXT_STUB_PREVIEW_TOKENS")
    context_args_preview_chars: int = Field(default=500, validation_alias="CONTEXT_ARGS_PREVIEW_CHARS")
    context_output_reserve: int = Field(default=1024, validation_alias="CONTEXT_OUTPUT_RESERVE")
    context_safety_buffer: int = Field(default=512, validation_alias="CONTEXT_SAFETY_BUFFER")
    chat_max_tool_hops: int = Field(default=8, validation_alias="CHAT_MAX_TOOL_HOPS")

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
