# kefuxitong 客服训练系统

AI 驱动的客服培训平台：管理员维护训练语料，客服登录后选择训练类型（PVC训练 / 金属铭牌训练），由 AI 扮演客户进行模拟对话训练，系统根据语料自动评分。

## 功能

**管理后台**
- 客服账号管理（新增 / 删除）
- 训练类型管理（PVC训练、金属铭牌训练，可扩展）
- 语料管理（按训练类型维护「客户问题 + 标准回答」）

**客服训练端**
- 选择训练类型开始训练
- AI 从语料库抽取问题扮演客户，逐轮对话
- 实时评分与反馈（对比标准答案）
- 训练结束给出总分

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | FastAPI + SQLAlchemy + SQLite + JWT |
| 前端 | Vue 3 + Vite + Vue Router + Axios |
| AI | 语料驱动规则引擎（预留 LLM 接口） |

## 目录结构

```
kefuxitong/
├── backend/      # 后端 API 服务
├── frontend/     # 前端 Web 应用
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

## 默认账号

首次启动后端自动创建：
- **管理员**：`admin` / `admin123`

客服账号由管理员在后台创建。

## 使用流程

1. 管理员登录 → 新建客服账号 → 维护语料
2. 客服账号登录 → 选择训练类型 → 与 AI 对话 → 查看评分

详见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## License

MIT
