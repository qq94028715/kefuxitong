"""应用配置。通过环境变量或 .env 文件覆盖默认值。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录
BASE_DIR = Path(__file__).resolve().parent.parent
# 数据目录（SQLite 数据库存放处，不入库）
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Settings(BaseSettings):
    # 数据库
    database_url: str = f"sqlite:///{(DATA_DIR / 'kefuxitong.db').as_posix()}"

    # JWT
    secret_key: str = "dev-secret-change-me-to-a-long-random-string"
    access_token_expire_minutes: int = 1440  # 24h

    # 默认管理员（首次启动自动创建，登录后请修改密码）
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"

    # 训练相关
    questions_per_session: int = 5  # 每次训练抽取的问题数

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
