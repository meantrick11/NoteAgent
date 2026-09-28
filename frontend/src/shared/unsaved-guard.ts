/**
 * 未保存内容的离开保护。三条路径都要覆盖：
 *   1. 应用内跳转（顶部导航、Home 快捷入口、浏览器前进后退）→ 路由守卫；
 *   2. 刷新或关闭标签页 → beforeunload；
 *   3. 会话切换与关闭面板 → 各自的动作里询问（在对应 store 里）。
 *
 * 取消离开时 URL 不动（守卫返回 false，vue-router 会放弃这次导航），
 * 选中页与文本都保持一致。确认放弃只清理当前动作确实放弃的缓冲。
 */

import type { Router } from 'vue-router'

import { useChatStore } from '@/features/chat/store'

/** 返回 true 表示可以离开；需要询问时由这里统一问。 */
export async function canLeaveAssistant(): Promise<boolean> {
  const chat = useChatStore()
  if (!chat.anyPanelDirty) return true
  if (!(await chat.confirmLeaveAssistant())) return false
  // 确认放弃：丢掉这次离开真正涉及的那一份缓冲，不动其他会话的草稿。
  chat.discardActivePanelEdits()
  return true
}

export function installUnsavedGuard(router: Router): void {
  router.beforeEach(async (to, from) => {
    if (to.path === from.path) return true
    if (from.name === 'assistant') return canLeaveAssistant()
    return true
  })
}

export function installBeforeUnload(): void {
  if (typeof window === 'undefined') return
  window.addEventListener('beforeunload', (event) => {
    const chat = useChatStore()
    if (!chat.anyPanelDirty) return
    event.preventDefault()
    // 现代浏览器忽略自定义文案，但仍要求设置 returnValue 才会弹确认。
    event.returnValue = ''
  })
}
