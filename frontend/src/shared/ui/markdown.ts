import { marked } from 'marked'

/**
 * Markdown 渲染唯一的入口。迁移前用模板里的 CDN marked，
 * 现在锁成 npm 依赖，渲染结果必须与旧页面一致。
 */
export function renderMarkdown(text: string): string {
  if (!text) return ''
  return marked.parse(text) as string
}
