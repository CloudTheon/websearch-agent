import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    # LLM
    model_provider: str = "openai"
    llm_model: str = os.getenv("LLM_MODEL", "")
    api_key: str = os.getenv("API_KEY", "")
    base_url: str = os.getenv("BASE_URL", "")
    extra_body: dict = field(default_factory=lambda: {"enable_thinking": False})

    # 搜索工具
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # 持久化
    db_path: Path = BASE_DIR / "data" / "agent.db"

    # 静态资源
    web_path: Path = BASE_DIR / "static" / "index.html"

    # Web
    cors_origins: list[str] = field(default_factory=lambda: ["*"])

    def require(self) -> "Settings":
        missing = [
            k
            for k in ("llm_model", "api_key", "tavily_api_key")
            if not getattr(self, k)
        ]
        if missing:
            raise RuntimeError(f"缺少环境变量: {', '.join(missing)}")
        return self


settings = Settings()
