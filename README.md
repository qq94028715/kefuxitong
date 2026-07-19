# kefuxitong 客服系统

基于 Web 的客服系统。

## 项目结构

```
kefuxitong/
├── backend/     # Python 后端（API 服务）
├── frontend/    # Vue 前端（Web 界面）
├── docs/        # 项目文档
├── scripts/     # 部署与运维脚本
├── uploads/     # 用户上传文件（运行时生成，不入库）
└── backup/      # 数据备份（运行时生成，不入库）
```

## 环境要求

| 工具 | 要求版本 | 本地状态 |
|------|----------|----------|
| Python | 3.12+ | 3.13.14 ✅ |
| Node.js | 22 LTS | v22.22.2 ✅ |
| Git | 任意 | 2.54.0 ✅ |

## 快速开始

```bash
git clone https://github.com/qq94028715/kefuxitong.git
cd kefuxitong
```

后端、前端的启动方式见各子目录说明（v0.1 后补充）。

## 开发方式

采用 GitHub + 版本迭代开发，所有代码围绕本仓库进行：

1. 每个版本有明确的新增/修改文件清单
2. 所有文件保持结构与路径一致
3. 通过 Git 提交管理变更，远程仓库作为唯一代码源

详见 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)。

## License

MIT
