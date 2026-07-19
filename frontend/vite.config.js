import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 前端开发服务器，/api 请求代理到后端 8000 端口
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
