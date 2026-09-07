import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端开发服务器，/api 请求代理到后端 8000 端口
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts: true,
    proxy: {
      '/api': {
        // 必须用 127.0.0.1 而非 localhost：Node 会把 localhost 解析成 IPv6 ::1，
        // 而 uvicorn 绑定 0.0.0.0 只监听 IPv4，会导致 ECONNREFUSED ::1:8000（所有接口 500）
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
