# AGENTS.md — AI 客服培训系统（kefuxitong）

给 AI 助手看的项目说明。接手前先读完，避免重复踩坑。

## 一、这是什么

企业内部 AI 客服培训平台：管理员上传培训资料 → 系统自动提炼知识库 → 客服登录后由 AI 扮演客户做模拟对话训练 → 结束后 AI 主管四维评分（需求确认 / 产品知识 / 销售技巧 / 成交推进）。

真实业务场景：**金属标牌 / 标识牌 B2B 询单**（PVC 标牌、304 不锈钢电缆标牌、铝牌等），成交周期长、以旺旺/微信咨询为主。

技术栈：FastAPI + SQLAlchemy + SQLite + JWT ｜ Vue 3 + Vite + Vue Router + Axios ｜ LLM 走 OpenAI 兼容接口（默认 DeepSeek，未配 Key 时规则兜底）。

## 二、目录结构

```
kefuxitong/
├── backend/
│   ├── app/
│   │   ├── ai/            # simulator(模拟客户) / evaluator(评分) / knowledge(知识库)
│   │   │   └── prompts/   # customer.txt(客户) / trainer.txt(主管) / knowledge.txt
│   │   ├── batch.py       # 批次与题库调度
│   │   ├── config.py      # 全部配置项（读 .env）
│   │   └── main.py        # FastAPI 路由
│   ├── data/              # kefuxitong.db（.gitignore 忽略，不入库）+ backup_* 备份
│   └── .env               # 密钥与 LLM 配置（不入库，换机需手动带）
├── frontend/src/views/    # Login / Admin / Train / Mastery
├── scripts/               # 数据导入与清洗脚本
├── uploads/               # 上传的培训素材（不入库）
└── docs/
```

## 三、启动

```bat
:: 后端（Python 3.12+）
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000

:: 前端（Node 22 LTS+）
cd frontend
npm install
npm run dev
```

- 前端 http://localhost:5173 ｜ API 文档 http://localhost:8000/docs
- 依赖装完后双击 `scripts/start.bat` 可一键起前后端
- `npm run build` 产物在 `frontend/dist`
- 测试：`backend/` 下 `pytest test_batch_flow.py test_mastery_flow.py test_desensitize.py`

## 四、当前状态（截至 2026-09-05）

版本 **v0.16.1**，代码已推 GitHub `main`（remote: https://github.com/qq94028715/kefuxitong.git）。

数据现状（换机后若用打包的 db）：users 5 / question 21 / knowledge 17（PVC 已去抗UV，v10）/ materials 27 / chat_session 35 / chat_message 210 / training_batch 7 / score 27 / quick_reply 53。

## 五、重要约定（改动前必读）

1. **模拟客户严守剧本**：AI 客户只能问剧本/知识库里真实存在的问题，不许编造参数（曾出现剧本是 304 不锈钢、客户却问 PVC/UV/8 年寿命）。改 `backend/app/ai/simulator.py` 和 `prompts/customer.txt` 时别删【剧本纪律】【对话纪律】。
2. **知识库版本化**：改动知识库要**新建 version**（如 v9 → v10），不要直接改旧版；`data/backup_YYYYMMDD_HHMMSS/` 留备份。`get_knowledge_for_training` 自动取 `max(version)`。
3. **判定回流默认关闭**：`config.py` 的 `judgment_flow_enabled = False`，错题/正确题**不写入** mistake_log 与 skill_mastery（主人测试期要求）。上线恢复需设 `.env: JUDGMENT_FLOW_ENABLED=true`。**别误以为是 bug。**
4. **BATCH_SIZE 被临时调小**（`.env` 里为 5，方便调试），正式用改回 20 或删掉该行。
5. **脏数据清洗**：题库剧本用 `scripts/clean_question_scripts.py`（默认 dry-run，`--safe-ratio` 阈值防误洗，默认 0.3，个别题降到 0.2）。知识库改运用 `scripts/drop_uv_from_pvc_knowledge.py`。两者都会自动备份。
6. **敏感文件不入 git**：`.env`、`*.db`、`uploads/`、`backup/`、`node_modules/`、`.venv/` 全部 gitignore。提交前确认 `git ls-files` 不含真实密钥。

## 六、踩过的坑

- **前端路由**：`frontend/src/router.js` 末尾有兜底路由 `{ path: '/:pathMatch(.*)*', redirect: '/login' }`，未知地址（如拼错的 `#/trainpan`）跳登录页。正确训练页是 `#/train`。
- **弹窗别被 tab 隔离**：Vue 弹窗要放在所有 `v-if="tab===..."` 容器**之外**，否则跨 tab 触发时永不渲染（v0.16 修过"看对话"点不开就是这个原因）。
- **续接训练**：`batch.py:start_question` 优先级是「续接 in_progress session → 开新题 → None」，别改回只挑 `session_id is None`。续接时用 `existing_msg_count > 0` 判断是否跳过 AI 开场白。
- **SQLite WAL**：拷贝/打包 db 前先 `PRAGMA wal_checkpoint(TRUNCATE)` + `integrity_check`，否则 -wal 未合并会丢数据。
- **git remote-tracking 可能过期**：`git log origin/main..HEAD` 数量对不上时，先 `git fetch` 检查 `merge-base`，必要时 `git update-ref refs/remotes/origin/main <远端真实SHA>`。push 加 `GIT_TERMINAL_PROMPT=0` 防卡密码输入。

## 七、主人偏好

- 先给结论和数据，再讲过程；能表格别纯文字。
- 改数据前先备份，破坏性操作先 dry-run 给他看。
- 改完顺手本地 commit（push 前确认无密钥泄漏）。
