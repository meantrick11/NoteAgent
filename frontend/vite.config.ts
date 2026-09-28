import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 开发期把后端接口代理到本地 FastAPI。
// changeOrigin 必须为 false：后端 require_same_origin 比较 Origin 的 netloc 与 Host，
// 改写 Host 会让浏览器发出的 Origin 与 Host 配不上，写操作会被 403。
const API_TARGET = 'http://127.0.0.1:8000'
const API_ROUTES = ['/chat', '/conversations', '/notes', '/model-settings']

export default defineConfig(({ command }) => ({
  plugins: [vue()],
  // 构建产物由 FastAPI 挂在 /ui-assets/ 下，所以生产资源路径固定带前缀；
  // 开发服务器仍在根路径，路由与 Playwright 的 baseURL 都更直观。
  base: command === 'build' ? '/ui-assets/' : '/',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: '../src/noteagent/web/dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(
      API_ROUTES.map((route) => [route, { target: API_TARGET, changeOrigin: false }]),
    ),
  },
}))
