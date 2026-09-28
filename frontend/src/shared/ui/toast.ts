/**
 * 保存成功的浮层提示。Assistant 的引用面板与 Library 的正文保存共用同一个。
 *
 * 与旧实现一致的两点：显示 3 秒；在"窗口宽度被内嵌浏览器报大"的环境里，
 * 靠右对齐会画到可视区之外，所以改贴顶部导航的右缘。
 */

import { ref } from 'vue'

const VISIBLE_MS = 3000

export const toastVisible = ref(false)
let timer: ReturnType<typeof setTimeout> | null = null

/** 计算浮层左边界；返回 null 表示保持默认的靠右定位。 */
function clippedLeft(): number | null {
  if (typeof window === 'undefined') return null
  const outer = window.outerWidth || window.innerWidth
  // 内嵌浏览器（如 Cursor）会把 innerWidth 报得比真实窗口大。
  if (window.innerWidth <= outer + 8) return null
  const nav = document.querySelector('.app-nav')
  if (!nav) return null
  return Math.round(nav.getBoundingClientRect().right + 8)
}

export function showSaveToast(): void {
  const left = clippedLeft()
  const root = document.documentElement
  if (left === null) root.style.removeProperty('--toast-left')
  else root.style.setProperty('--toast-left', `${left}px`)

  toastVisible.value = false
  // 强制下一帧再打开，保证连续两次保存都能看到动画。
  void root.offsetWidth
  toastVisible.value = true
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => {
    toastVisible.value = false
    timer = null
  }, VISIBLE_MS)
}
