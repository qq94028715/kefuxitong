# AI 客服培训平台

面向企业的 AI 客服培训系统：管理员上传培训资料，系统自动提炼知识；客服登录后由 AI 扮演客户进行模拟对话训练，结束后由 AI 主管自动评分。帮助企业更快培养出能独立接待客户的客服人员。

## ✨ 功能特性

- ✔ 多格式资料导入：**TXT / Markdown / PPT / PDF / DOCX / XLSX**
- ✔ AI 自动提炼知识：产品知识、销售案例（成功/失败模式）、SOP、培训教材、FAQ
- ✔ AI 模拟客户：多轮自然对话，6 种随机性格，越练越真实
- ✔ AI 自动评分：四维加权评分（需求确认 / 产品知识 / 销售技巧 / 成交推进）
- ✔ 训练成绩管理：管理员可查看每位客服的训练记录与四维得分
- ✔ 长对话优化：超过阈值自动 AI 摘要，压缩上下文、提升稳定性
- ✔ 本地部署：数据留在自己服务器，支持 DeepSeek / 通义 / OpenAI 等兼容模型

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy + SQLite + JWT |
| 前端 | Vue 3 + Vite + Vue Router + Axios |
| AI | OpenAI 兼容 LLM（默认 DeepSeek，可配置通义 / OpenAI / Kimi，未配置时走规则兜底） |

## 目录结构

```
kefuxitong/
├── backend/      # 后端 API 服务（FastAPI）
├── frontend/     # 前端 Web 应用（Vue 3）
├── docs/         # 项目文档
├── scripts/      # 启动脚本
├── uploads/      # 运行时上传文件（不入库）
└── backup/       # 运行时数据备份（不入库）
```

## 快速开始

### 1. 环境要求

- Python 3.12+
- Node.js 22 LTS+
- Git

### 2. 克隆仓库

```bash
git clone https://github.com/qq94028715/kefuxitong.git
cd kefuxitong
```

### 3. 启动后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt       # Windows
# .venv/bin/pip install -r requirements.txt         # macOS/Linux
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

### 4. 启动前端（新开终端）

```bash
cd frontend
npm install
npm run dev
```

### 5. 一键启动（Windows）

双击 `scripts/start.bat`，自动打开前后端两个窗口。

### 6. 访问

- 前端页面：http://localhost:5173
- 接口文档：http://localhost:8000/docs

## 配置 LLM（可选但推荐）

编辑 `backend/.env`：

```ini
LLM_API_KEY=你的密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
```

未配置时系统走规则兜底模式，仍可完整体验训练流程（无 AI 生成内容）。

## 默认账号

首次启动后端自动创建：
- **管理员**：`admin` / `admin123`

客服账号由管理员在后台创建。

## 使用流程

1. 管理员登录 → 新建客服账号 → 上传培训资料（按资料类型分类）
2. 提取知识库（AI 自动提炼结构化知识）
3. 客服账号登录 → 选择训练类型 → 与 AI 客户对话 → 查看评分
4. 管理员在后台查看客服的训练成绩与成长情况

详见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## License

MIT
