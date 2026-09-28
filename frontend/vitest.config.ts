import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  test: {
    // 默认跑纯逻辑；需要 DOM（localStorage、选区）的用例在文件顶部用
    // `// @vitest-environment jsdom` 单独声明。
    environment: 'node',
    include: ['tests/unit/**/*.spec.ts'],
  },
})
