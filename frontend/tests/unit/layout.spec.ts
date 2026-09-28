import { describe, expect, it } from 'vitest'

import {
  CHAT_LAYOUT_KEY,
  LAYOUT_DEFAULTS,
  LAYOUT_LIMITS,
  applyPaneWidth,
  chatLayoutBounds,
  draggedWidth,
  effectiveChatLayout,
  keyedWidth,
  readStoredChatLayout,
  saveChatLayout,
  storedWidth,
  type StorageLike,
} from '@/features/chat/layout'

function memoryStorage(initial: Record<string, string> = {}): StorageLike & {
  data: Record<string, string>
} {
  const data = { ...initial }
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = value
    },
  }
}

describe('chatLayoutBounds 的收边顺序', () => {
  it('宽屏给足上限', () => {
    const bounds = chatLayoutBounds(1920)
    expect(bounds.sidebarMin).toBe(LAYOUT_LIMITS.sidebarMin)
    expect(bounds.sidebarMax).toBe(LAYOUT_LIMITS.sidebarMax)
    expect(bounds.paneMin).toBe(LAYOUT_LIMITS.paneMin)
    expect(bounds.paneMax).toBe(LAYOUT_LIMITS.paneMax)
  })

  it('中等宽度先压右栏上限，再压左栏上限', () => {
    // 1088 - 200 - 440 = 448 → 右栏上限 448；1088 - 300 - 440 = 348 → 左栏上限 348。
    const bounds = chatLayoutBounds(1088)
    expect(bounds.paneMax).toBe(448)
    expect(bounds.sidebarMax).toBe(348)
  })

  it('极窄视口下两个 min 一起让位，不会出现 min > max', () => {
    const bounds = chatLayoutBounds(400)
    expect(bounds.sidebarMin + bounds.paneMin).toBeLessThanOrEqual(400)
    expect(bounds.sidebarMin).toBeGreaterThanOrEqual(0)
    expect(bounds.paneMin).toBeGreaterThanOrEqual(0)
    expect(bounds.sidebarMin).toBeLessThanOrEqual(bounds.sidebarMax)
    expect(bounds.paneMin).toBeLessThanOrEqual(bounds.paneMax)
  })
})

describe('存储值校验', () => {
  it('只接受范围内的有限数值', () => {
    expect(storedWidth(300, 260, 200, 400)).toBe(300)
    expect(storedWidth(100, 260, 200, 400)).toBe(260)
    expect(storedWidth(500, 260, 200, 400)).toBe(260)
    expect(storedWidth('300', 260, 200, 400)).toBe(260)
    expect(storedWidth(Number.NaN, 260, 200, 400)).toBe(260)
    expect(storedWidth(undefined, 260, 200, 400)).toBe(260)
  })
})

describe('readStoredChatLayout', () => {
  it('没有存储时用默认宽度', () => {
    expect(readStoredChatLayout(memoryStorage())).toEqual(LAYOUT_DEFAULTS)
    expect(readStoredChatLayout(null)).toEqual(LAYOUT_DEFAULTS)
  })

  it('读回合法宽度', () => {
    const storage = memoryStorage({
      [CHAT_LAYOUT_KEY]: JSON.stringify({ sidebarWidth: 300, notePaneWidth: 500 }),
    })
    expect(readStoredChatLayout(storage)).toEqual({ sidebarWidth: 300, notePaneWidth: 500 })
  })

  it('越界或类型不对的字段各自回退默认', () => {
    const storage = memoryStorage({
      [CHAT_LAYOUT_KEY]: JSON.stringify({ sidebarWidth: 9999, notePaneWidth: 'wide' }),
    })
    expect(readStoredChatLayout(storage)).toEqual(LAYOUT_DEFAULTS)
  })

  it('存储损坏时退回默认而不是抛异常', () => {
    const storage = memoryStorage({ [CHAT_LAYOUT_KEY]: '{not json' })
    expect(readStoredChatLayout(storage)).toEqual(LAYOUT_DEFAULTS)
  })

  it('键名保持 noteagent.chat-layout.v1，老用户的记忆宽度不会失效', () => {
    expect(CHAT_LAYOUT_KEY).toBe('noteagent.chat-layout.v1')
  })
})

describe('saveChatLayout', () => {
  it('写入与读取对称', () => {
    const storage = memoryStorage()
    saveChatLayout(storage, { sidebarWidth: 320, notePaneWidth: 480 })
    expect(JSON.parse(storage.data[CHAT_LAYOUT_KEY])).toEqual({
      sidebarWidth: 320,
      notePaneWidth: 480,
    })
  })

  it('写入失败不影响调用方', () => {
    const throwing: StorageLike = {
      getItem: () => null,
      setItem: () => {
        throw new Error('quota exceeded')
      },
    }
    expect(() => saveChatLayout(throwing, LAYOUT_DEFAULTS)).not.toThrow()
  })
})

describe('effectiveChatLayout', () => {
  it('把用户意图收进当前视口的边界', () => {
    const effective = effectiveChatLayout({ sidebarWidth: 400, notePaneWidth: 600 }, 1088)
    expect(effective.sidebarWidth).toBe(348)
    expect(effective.notePaneWidth).toBe(448)
  })

  it('视口变宽后回到用户原本想要的宽度', () => {
    const intent = { sidebarWidth: 400, notePaneWidth: 600 }
    expect(effectiveChatLayout(intent, 800).notePaneWidth).toBeLessThan(600)
    expect(effectiveChatLayout(intent, 1920)).toEqual({ ...intent, bounds: chatLayoutBounds(1920) })
  })
})

describe('键盘调整', () => {
  const bounds = chatLayoutBounds(1920)

  it('左栏右移变大，左移变小', () => {
    expect(keyedWidth('sidebar', { key: 'ArrowRight', shiftKey: false }, 260, bounds)).toBe(270)
    expect(keyedWidth('sidebar', { key: 'ArrowLeft', shiftKey: false }, 260, bounds)).toBe(250)
  })

  it('右栏方向相反：左移变大', () => {
    expect(keyedWidth('pane', { key: 'ArrowLeft', shiftKey: false }, 400, bounds)).toBe(410)
    expect(keyedWidth('pane', { key: 'ArrowRight', shiftKey: false }, 400, bounds)).toBe(390)
  })

  it('Shift 走大步长', () => {
    expect(keyedWidth('sidebar', { key: 'ArrowRight', shiftKey: true }, 260, bounds)).toBe(300)
    expect(keyedWidth('pane', { key: 'ArrowLeft', shiftKey: true }, 400, bounds)).toBe(440)
  })

  it('Home／End 直达边界', () => {
    expect(keyedWidth('sidebar', { key: 'Home', shiftKey: false }, 260, bounds)).toBe(200)
    expect(keyedWidth('sidebar', { key: 'End', shiftKey: false }, 260, bounds)).toBe(400)
    expect(keyedWidth('pane', { key: 'Home', shiftKey: false }, 400, bounds)).toBe(300)
    expect(keyedWidth('pane', { key: 'End', shiftKey: false }, 400, bounds)).toBe(600)
  })

  it('不认识的按键返回 null，交给浏览器处理', () => {
    expect(keyedWidth('sidebar', { key: 'Tab', shiftKey: false }, 260, bounds)).toBeNull()
  })
})

describe('拖动', () => {
  it('左栏往右拖变宽；右栏往左拖变宽', () => {
    expect(draggedWidth({ kind: 'sidebar', startX: 300, startWidth: 260 }, 350)).toBe(310)
    expect(draggedWidth({ kind: 'pane', startX: 800, startWidth: 400 }, 700)).toBe(500)
  })
})

describe('applyPaneWidth', () => {
  it('只改被拖动的那一栏，并把值收进边界', () => {
    const bounds = chatLayoutBounds(1920)
    const next = applyPaneWidth({ sidebarWidth: 260, notePaneWidth: 400 }, 'pane', 9999, bounds)
    expect(next).toEqual({ sidebarWidth: 260, notePaneWidth: 600 })
  })
})
