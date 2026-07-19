# 开发流程

## 版本迭代规则

本项目按版本号推进开发，每个版本对应一次完整的功能交付。

### 版本命名

`v主版本.次版本`，如 v0.1、v0.2、v1.0

### 提交清单规范

每个版本包含一个文件清单，说明新增/修改的文件，例如：

```
v0.1
新增:
  backend/app/main.py
  backend/app/models.py
  frontend/src/views/Login.vue
修改:
  README.md
```

所有文件路径与仓库结构保持一致，便于逐文件对照实现。

### 分支策略

- `main`：稳定分支，保持可运行状态
- 按需创建 `feature/*` 分支进行开发，完成后合并回 `main`

## 目录职责

| 目录 | 用途 | 是否入库 |
|------|------|----------|
| `backend/` | 后端 API 服务 | 是 |
| `frontend/` | 前端 Web 应用 | 是 |
| `docs/` | 项目文档 | 是 |
| `scripts/` | 部署、运维脚本 | 是 |
| `uploads/` | 运行时上传文件 | 否（保留目录） |
| `backup/` | 运行时数据备份 | 否（保留目录） |

## 推送到 GitHub

本地提交后，推送到远程需要配置 Git 凭证：

```bash
# 配置提交者信息（首次）
git config user.name "你的名字"
git config user.email "你的邮箱"

# 推送
git push origin main
```

若使用 HTTPS，建议配置 Personal Access Token 或 Git Credential Manager。
若使用 SSH，需将公钥添加到 GitHub 账号。
