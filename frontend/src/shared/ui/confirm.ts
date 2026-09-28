/**
 * 全局单例对话框：同一时刻只有一个，与旧页面的 openDocsModal 一致。
 *
 * 用 promise 而不是回调，是因为调用点分散在 store、路由守卫和 beforeunload 里，
 * 都需要"等用户回答完再决定"。写成模块级单例而不是 provide/inject，
 * 是为了让 store 和守卫不必依赖组件树。
 */

import { shallowRef } from 'vue'

export interface DialogOptions {
  title: string
  body?: string
  /** 需要输入时给初始值；不给就是纯确认框。 */
  value?: string
  input?: boolean
  /** true = 危险动作，确认按钮常态是红色。 */
  danger?: boolean
  confirmText?: string
  /** 只有一个"确认"，没有取消。 */
  alert?: boolean
}

export interface DialogState extends DialogOptions {
  open: boolean
}

const state = shallowRef<DialogState>({ open: false, title: '' })
let resolver: ((value: unknown) => void) | null = null

export function dialogState() {
  return state
}

function open(options: DialogOptions): Promise<unknown> {
  // 旧实现里后来的对话框会顶掉前一个（前一个按取消处理）。
  if (resolver) settle(null)
  return new Promise((resolve) => {
    resolver = resolve
    state.value = { ...options, open: true }
  })
}

/** 关闭对话框；result 为 null 表示取消。 */
export function settle(result: unknown): void {
  const resolve = resolver
  resolver = null
  state.value = { ...state.value, open: false }
  if (resolve) resolve(result)
}

export function confirmDialog(
  options: Omit<DialogOptions, 'input' | 'alert'>,
): Promise<boolean> {
  return open({ ...options, input: false }).then((value) => value === true)
}

export function promptDialog(
  options: Omit<DialogOptions, 'input' | 'alert' | 'danger'>,
): Promise<string | null> {
  return open({ ...options, input: true, danger: false }).then((value) =>
    typeof value === 'string' ? value : null,
  )
}

export function alertDialog(title: string, body: string): Promise<void> {
  return open({ title, body, alert: true, danger: false }).then(() => undefined)
}

/** 统一的失败提示：错误文案已经在 API 层提取过，这里只负责呈现。 */
export function reportError(title: string, error: unknown): Promise<void> {
  const message = error instanceof Error ? error.message : String(error)
  return alertDialog(title, message)
}
