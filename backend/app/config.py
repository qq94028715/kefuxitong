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
    batch_size: int = 20  # 每批题数（组卷大小，调试时可临时改小）

    # ---------- 掌握度引擎（v0.8）----------
    mastery_alpha: float = 0.3  # EMA 学习率（新判定权重），驳回时自动翻倍
    mastery_pass_threshold: float = 50.0  # 及格线：mastery >= 该值 → pass
    mastery_master_threshold: float = 80.0  # 达标线：mastery >= 该值 → master
    # 自适应出题批内配比（20 题基准，比例和不足 100% 时按比例顺延）
    adaptive_mistake_ratio: float = 0.2  # 错题重练
    adaptive_weak_ratio: float = 0.5  # 薄弱点优先
    adaptive_consolidate_ratio: float = 0.2  # 及格巩固（难度升级）
    adaptive_new_ratio: float = 0.1  # 新题/随机巩固

    # 主管判定回流开关（v0.16）：暂时关闭 = 判定只记状态，不写错题本/不更新掌握度
    # 上线正式启用后设 TRUE，判定结果才会回流错题本复练 + 掌握度 EMA
    judgment_flow_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
