/**
 * 三栏宽度：左侧会话栏、中间聊天区、右侧引用／草稿面板。
 *
 * 只持久化左右两栏的宽度，中间区吃剩余空间。拖动与键盘走同一条
 * `setPaneWidth`，所以边界收束逻辑只有一份。
 *
 * 与旧实现的一致性要点（改名或改常量都会让老用户的记忆宽度失效）：
 *  - 存储键仍是 `noteagent.chat-layout.v1`，值仍是 `{sidebarWidth, notePaneWidth}`；
 *  - 越界或类型不对的存储值回退默认，再按当前视口收边；
 *  - 视口变化只重新收边，不改用户意图，也不写存储。
 */

import { computed, ref, type ComputedRef, type Ref } from 'vue'

export const CHAT_LAYOUT_KEY = 'noteagent.chat-layout.v1'
export const LAYOUT_DEFAULTS = { sidebarWidth: 260, notePaneWidth: 400 }
export const LAYOUT_LIMITS = {
  sidebarMin: 200,
  sidebarMax: 400,
  paneMin: 300,
  paneMax: 600,
  chatMin: 440,
}
/** 键盘调整：方向键 10px，按住 Shift 40px，Home／End 直接到边界。 */
export const KEYBOARD_STEP = 10
export const KEYBOARD_STEP_LARGE = 40

export type PaneKind = 'sidebar' | 'pane'

export interface ChatLayout {
  sidebarWidth: number
  notePaneWidth: number
}

export interface LayoutBounds {
  sidebarMin: number
  sidebarMax: number
  paneMin: number
  paneMax: number
}

/** 只依赖 getItem／setItem，测试可以传内存实现。 */
export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export function clampValue(value: number, low: number, high: number): number {
  return Math.round(Math.min(high, Math.max(low, value)))
}

/**
 * 当前视口下的有效上下界：先压右栏，再压左栏，最后允许中间区被压到 0。
 * 窗口很窄时 `sidebarMin + paneMin` 会超过视口，所以两个 min 也要跟着让。
 */
export function chatLayoutBounds(viewport: number): LayoutBounds {
  const limits = LAYOUT_LIMITS
  const paneMax = Math.min(
    limits.paneMax,
    Math.max(limits.paneMin, viewport - limits.sidebarMin - limits.chatMin),
  )
  const sidebarMax = Math.min(
    limits.sidebarMax,
    Math.max(limits.sidebarMin, viewport - limits.paneMin - limits.chatMin),
  )
  let paneMin = limits.paneMin
  let sidebarMin = limits.sidebarMin
  if (sidebarMin + paneMin > viewport) {
    paneMin = Math.max(0, Math.min(paneMin, viewport - sidebarMin))
    sidebarMin = Math.max(0, Math.min(sidebarMin, viewport - paneMin))
  }
  return { sidebarMin, sidebarMax, paneMin, paneMax }
}

/** 只接受范围内的有限数值，越界或类型不对都回退默认。 */
export function storedWidth(
  value: unknown,
  fallback: number,
  low: number,
  high: number,
): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return fallback
  if (value < low || value > high) return fallback
  return value
}

/** 读取存储；损坏或不可用时退回默认宽度，页面照常可用。 */
export function readStoredChatLayout(storage: StorageLike | null | undefined): ChatLayout {
  if (!storage) return { ...LAYOUT_DEFAULTS }
  try {
    const raw = storage.getItem(CHAT_LAYOUT_KEY)
    if (!raw) return { ...LAYOUT_DEFAULTS }
    const parsed = JSON.parse(raw) as Partial<ChatLayout> | null
    return {
      sidebarWidth: storedWidth(
        parsed?.sidebarWidth,
        LAYOUT_DEFAULTS.sidebarWidth,
        LAYOUT_LIMITS.sidebarMin,
        LAYOUT_LIMITS.sidebarMax,
      ),
      notePaneWidth: storedWidth(
        parsed?.notePaneWidth,
        LAYOUT_DEFAULTS.notePaneWidth,
        LAYOUT_LIMITS.paneMin,
        LAYOUT_LIMITS.paneMax,
      ),
    }
  } catch {
    return { ...LAYOUT_DEFAULTS }
  }
}

export function saveChatLayout(
  storage: StorageLike | null | undefined,
  layout: ChatLayout,
): void {
  if (!storage) return
  try {
    storage.setItem(CHAT_LAYOUT_KEY, JSON.stringify(layout))
  } catch {
    // 写入失败忽略：布局仍在本次会话内生效。
  }
}

/** 把用户意图按当前视口收进边界；返回实际生效的宽度。 */
export function effectiveChatLayout(
  layout: ChatLayout,
  viewport: number,
): ChatLayout & { bounds: LayoutBounds } {
  const bounds = chatLayoutBounds(viewport)
  return {
    sidebarWidth: clampValue(layout.sidebarWidth, bounds.sidebarMin, bounds.sidebarMax),
    notePaneWidth: clampValue(layout.notePaneWidth, bounds.paneMin, bounds.paneMax),
    bounds,
  }
}

/** 方向键／Home／End 的步进；右栏向左是变宽，方向与左栏相反。 */
export function keyedWidth(
  kind: PaneKind,
  event: { key: string; shiftKey: boolean },
  current: number,
  bounds: LayoutBounds,
): number | null {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(event.key)) return null
  const inSidebar = kind === 'sidebar'
  const low = inSidebar ? bounds.sidebarMin : bounds.paneMin
  const high = inSidebar ? bounds.sidebarMax : bounds.paneMax
  if (event.key === 'Home') return low
  if (event.key === 'End') return high
  const step = event.shiftKey ? KEYBOARD_STEP_LARGE : KEYBOARD_STEP
  const grow = inSidebar
    ? event.key === 'ArrowRight'
      ? step
      : -step
    : event.key === 'ArrowLeft'
      ? step
      : -step
  return current + grow
}

export interface DragState {
  kind: PaneKind
  startX: number
  startWidth: number
}

/** 拖动中的目标宽度；右栏往左拖是变宽，所以取负号。 */
export function draggedWidth(drag: DragState, clientX: number): number {
  const delta = clientX - drag.startX
  return drag.kind === 'sidebar' ? drag.startWidth + delta : drag.startWidth - delta
}

export function applyPaneWidth(
  layout: ChatLayout,
  kind: PaneKind,
  value: number,
  bounds: LayoutBounds,
): ChatLayout {
  if (kind === 'sidebar') {
    return { ...layout, sidebarWidth: clampValue(value, bounds.sidebarMin, bounds.sidebarMax) }
  }
  return { ...layout, notePaneWidth: clampValue(value, bounds.paneMin, bounds.paneMax) }
}

function defaultStorage(): StorageLike | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export interface UseChatLayout {
  /** 用户意图的宽度；可能超出当前视口的有效范围，渲染请用 effective。 */
  layout: Ref<ChatLayout>
  bounds: ComputedRef<LayoutBounds>
  effective: ComputedRef<ChatLayout & { bounds: LayoutBounds }>
  dragging: Ref<boolean>
  setPaneWidth(kind: PaneKind, value: number): void
  beginDrag(kind: PaneKind, event: PointerEvent, handle?: HTMLElement | null): void
  moveDrag(event: PointerEvent): void
  endDrag(handle?: HTMLElement | null): void
  keyPaneWidth(kind: PaneKind, event: KeyboardEvent): void
  dispose(): void
}

/**
 * 组件用的响应式封装。窗口 resize 只重新收边——用户意图留在 layout 里，
 * 视口变宽后会自然回到原来的宽度。
 */
export function useChatLayout(storage: StorageLike | null = defaultStorage()): UseChatLayout {
  const layout = ref<ChatLayout>(readStoredChatLayout(storage))
  const viewport = ref(typeof window === 'undefined' ? 1440 : window.innerWidth)
  const dragging = ref(false)
  let drag: DragState | null = null

  const bounds = computed(() => chatLayoutBounds(viewport.value))
  const effective = computed(() => effectiveChatLayout(layout.value, viewport.value))

  function setPaneWidth(kind: PaneKind, value: number): void {
    layout.value = applyPaneWidth(layout.value, kind, value, bounds.value)
  }

  function currentWidth(kind: PaneKind): number {
    return kind === 'sidebar' ? effective.value.sidebarWidth : effective.value.notePaneWidth
  }

  function beginDrag(kind: PaneKind, event: PointerEvent): void {
    if (event.button != null && event.button !== 0) return
    drag = { kind, startX: event.clientX, startWidth: currentWidth(kind) }
    dragging.value = true
    event.preventDefault()
  }

  function moveDrag(event: PointerEvent): void {
    if (!drag) return
    setPaneWidth(drag.kind, draggedWidth(drag, event.clientX))
  }

  function endDrag(): void {
    if (!drag) return
    drag = null
    dragging.value = false
    saveChatLayout(storage, layout.value)
  }

  function keyPaneWidth(kind: PaneKind, event: KeyboardEvent): void {
    const next = keyedWidth(kind, event, currentWidth(kind), bounds.value)
    if (next === null) return
    setPaneWidth(kind, next)
    saveChatLayout(storage, layout.value)
    event.preventDefault()
  }

  const onResize = (): void => {
    viewport.value = window.innerWidth
  }
  if (typeof window !== 'undefined') window.addEventListener('resize', onResize)

  function dispose(): void {
    if (typeof window !== 'undefined') window.removeEventListener('resize', onResize)
  }

  return {
    layout,
    bounds,
    effective,
    dragging,
    setPaneWidth,
    beginDrag,
    moveDrag,
    endDrag,
    keyPaneWidth,
    dispose,
  }
}
