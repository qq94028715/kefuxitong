# 前端 (Frontend)

Vue 3 + Vite + Vue Router + Axios。

## 目录结构

```
frontend/
├── src/
│   ├── main.js          # 应用入口
│   ├── App.vue          # 根组件
│   ├── router.js        # 路由（hash 模式）
│   ├── api.js           # axios 封装 + API 调用
│   ├── style.css        # 全局样式
│   └── views/
│       ├── Login.vue    # 登录页（管理员/客服切换）
│       ├── Admin.vue    # 管理后台（账号/训练类型/语料管理）
│       └── Train.vue    # 客服训练页（对话+评分）
├── index.html
├── vite.config.js
└── package.json
```

## 安装依赖

```bash
cd frontend
npm install
```

## 启动开发服务器

```bash
npm run dev
```

访问：http://localhost:5173

开发服务器已配置代理：`/api` 请求自动转发到后端 `http://localhost:8000`，
所以前后端需同时运行。

## 构建

```bash
npm run build
```

构建产物在 `dist/`，可部署到任意静态服务器。部署时需将 `/api` 反向代理到后端。

## 使用流程

1. 用管理员账号登录（`admin` / `admin123`）→ 管理后台
2. 在「客服账号」tab 新建客服账号
3. 在「语料管理」tab 为训练类型添加「客户问题 + 标准回答」
4. 退出，用客服账号登录 → 训练中心
5. 选择训练类型 → 与 AI 客户对话 → 查看评分反馈
