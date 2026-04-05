"""
config.py —— pydantic-settings 配置管理（Phase 4 升级版）

env 文件加载优先级（后者覆盖前者）：
  1. ~/.codeagent/.env  （用户全局配置）
  2. .env               （项目本地配置，最高优先级）
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_openai import ChatOpenAI

# 用户全局配置路径
_USER_ENV = Path.home() / ".codeagent" / ".env"
_LOCAL_ENV = Path(".env")

# 收集存在的 env 文件（按优先级从低到高）
_ENV_FILES: list[str] = []
if _USER_ENV.exists():
    _ENV_FILES.append(str(_USER_ENV))
if _LOCAL_ENV.exists():
    _ENV_FILES.append(str(_LOCAL_ENV))
if not _ENV_FILES:
    _ENV_FILES = [".env"]  # 回退，让 pydantic-settings 自行处理


class Settings(BaseSettings):
    PROJECT_NAME: str = "CodeAgent"

    # LLM（火山引擎 Ark，OpenAI 兼容）
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v3.2")

    # Embedding（Phase 2 启用）
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "doubao-embedding-vision-250615")
    EMBEDDING_BASE_URL: str = os.getenv("EMBEDDING_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    EMBEDDING_API_KEY: str = os.getenv("EMBEDDING_API_KEY", "")

    # 存储
    VECTOR_BACKEND: str = os.getenv("VECTOR_BACKEND", "qdrant")
    DB_URL: str = os.getenv("DB_URL", "sqlite:///./codeagent.db")

    # 记忆窗口
    WINDOW_SIZE: int = int(os.getenv("WINDOW_SIZE", "10"))

    # Qdrant
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")

    # Shell 沙箱
    WORKSPACE_DIR: str = os.getenv("WORKSPACE_DIR", ".")
    SHELL_SANDBOX: str = os.getenv("SHELL_SANDBOX", "subprocess")

    # 重试
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "3"))

    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,  # type: ignore[arg-type]
        extra="ignore",
    )

    @property
    def embedding_api_key(self) -> str:
        return self.EMBEDDING_API_KEY or self.LLM_API_KEY


settings = Settings()


def get_llm(streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        model=settings.LLM_MODEL,
        temperature=0.3,
        max_tokens=4096,
        streaming=streaming,
        max_retries=settings.LLM_MAX_RETRIES,
    )
