# 后端 (Backend)

FastAPI + SQLAlchemy + SQLite，开箱即跑，无需额外安装数据库。

## 目录结构

```
backend/
├── app/
│   ├── main.py         # FastAPI 入口 + 全部路由
│   ├── config.py       # 配置（读取 .env）
│   ├── database.py     # SQLite 连接
│   ├── models.py       # 数据模型
│   ├── schemas.py      # Pydantic 请求/响应模型
│   ├── auth.py         # JWT 认证 + 角色鉴权
│   └── ai_trainer.py   # AI 训练器（语料驱动评分）
├── data/               # SQLite 数据库（自动生成，不入库）
├── requirements.txt
└── .env.example
```

## 安装依赖

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\pip install -r requirements.txt
# macOS / Linux
.venv/bin/pip install -r requirements.txt
```

## 启动

```bash
# Windows
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
# macOS / Linux
.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后：
- API 服务：http://localhost:8000
- 接口文档（Swagger）：http://localhost:8000/docs

## 默认数据

首次启动自动初始化：
- 管理员账号：`admin` / `admin123`（登录后请尽快修改）
- 训练类型：`PVC训练`、`金属铭牌训练`（各含 3 条示例语料）

## 配置

复制 `.env.example` 为 `.env`，按需修改数据库路径、密钥、默认管理员等。

## AI 训练器说明

当前 MVP 采用**规则模式**：从语料库抽取「客户问题」由 AI 扮演客户提问，
用文本相似度对比客服回答与「标准答案」给出评分。

后续接入真实 LLM（如 OpenAI / DeepSeek / 通义千问）时，
在 `app/ai_trainer.py` 的 `LLMAdapter` 中实现 `generate_customer_reply`，
并根据 `.env` 中的 `LLM_*` 配置切换。详见 `docs/DEVELOPMENT.md`。
