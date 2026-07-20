"""应用配置。通过环境变量或 .env 文件覆盖默认值。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录
BASE_DIR = Path(__file__).resolve().parent.parent
# 数据目录（SQLite 数据库存放处，不入库）
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
# 上传材料目录
UPLOAD_DIR = BASE_DIR.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    # 数据库
    database_url: str = f"sqlite:///{(DATA_DIR / 'kefuxitong.db').as_posix()}"

    # JWT
    secret_key: str = "dev-secret-change-me-to-a-long-random-string"
    access_token_expire_minutes: int = 1440  # 24h

    # 默认管理员（首次启动自动创建，登录后请修改密码）
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"

    # ---------- LLM 配置（OpenAI 兼容接口）----------
    # 不配置时 simulator/evaluator 走规则 fallback，knowledge 提取会失败
    # DeepSeek:  LLM_BASE_URL=https://api.deepseek.com/v1  LLM_MODEL=deepseek-chat
    # 通义千问:  LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  LLM_MODEL=qwen-plus
    # OpenAI:    LLM_BASE_URL=https://api.openai.com/v1  LLM_MODEL=gpt-4o-mini
    llm_api_key: str = ""  # 留空 = 不启用 LLM
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1024
    llm_timeout: int = 60  # 秒

    # 训练相关
    max_dialogue_turns: int = 20  # 单次训练最大对话轮数（防止无限聊）
    min_dialogue_turns: int = 4  # 至少聊几轮才允许结束评分
    stream_delay: float = 0.03  # 逐字流式速度（秒/字符），可用 .env 覆盖，免重新部署

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
