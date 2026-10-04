// @vitest-environment jsdom
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// 对话框在这里没有挂载的组件，真实实现会一直等用户点确认。
// 用桩替掉：默认"确认"，个别用例再改返回值。
vi.mock('@/shared/ui/confirm', () => ({
  confirmDialog: vi.fn(async () => true),
  promptDialog: vi.fn(async () => null),
  alertDialog: vi.fn(async () => undefined),
  reportError: vi.fn(async () => undefined),
}))

import { useChatStore, citePaneKey } from '@/features/chat/store'
import { useModelsStore } from '@/features/models/store'
import { draft, jsonResponse, messages, modelSettings, sseText } from '../fixtures/api'

type Handler = (init: RequestInit) => Response | Promise<Response>

function routeFetch(routes: Array<[string, Handler]>) {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const impl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const options = init ?? {}
    calls.push({ url, init: options })
    for (const [prefix, handler] of routes) {
      if (url.startsWith(prefix)) return handler(options)
    }
    return jsonResponse({ detail: `no stub for ${url}` }, 500)
  }) as typeof fetch
  return { calls, fetch: impl }
}

/** 一个可直接读取的 SSE 响应。 */
function sseResponse(events: Array<[string, unknown]>): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(sseText(events)))
      controller.close()
    },
  })
  return new Response(body, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function bodyOf(call: { init: RequestInit }): Record<string, unknown> {
  return JSON.parse(String(call.init.body)) as Record<string, unknown>
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/** 让 store 拿到一份可用状态，避免 refreshIfStale 打出未预期的请求。 */
async function ready(routes: Array<[string, Handler]> = []) {
  const stub = routeFetch([['/model-settings', () => jsonResponse(modelSettings)], ...routes])
  vi.stubGlobal('fetch', stub.fetch)
  const models = useModelsStore()
  await models.fetchStatus(true)
  return stub
}

describe('发送门闩', () => {
  it('第一次 await 之前就上锁：双击的第二下直接拒绝', async () => {
    const stub = await ready([
      ['/chat', () => sseResponse([['token', 'ok'], ['answer', 'ok']])],
    ])
    const chat = useChatStore()

    const first = chat.send('第一个问题')
    const second = await chat.send('第二个问题')
    expect(second).toBe('refused')
    expect(await first).toBe('sent')

    // 只有一轮请求，用户消息也只多了一条（第二下没有产生任何写入）。
    expect(stub.calls.filter((call) => call.url === '/chat')).toHaveLength(1)
    expect(chat.messages.filter((item) => item.role === 'user')).toHaveLength(1)
  })

  it('维护窗口里不发送，并把原因告诉用户', async () => {
    const stub = routeFetch([
      ['/model-settings', () => jsonResponse({ ...modelSettings, busy: true })],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const models = useModelsStore()
    await models.fetchStatus(true)
    const chat = useChatStore()

    expect(await chat.send('会被拒的问题')).toBe('refused')
    expect(stub.calls.some((call) => call.url === '/chat')).toBe(false)
    expect(chat.messages.at(-1)?.content).toContain('向量索引重建中')
  })

  it('流异常后释放门闩，下一条还能发出去', async () => {
    const stub = await ready([
      ['/chat', () => jsonResponse({ detail: '会话不存在' }, 404)],
    ])
    const chat = useChatStore()

    expect(await chat.send('第一轮')).toBe('failed')
    expect(chat.streaming).toBe(false)
    expect(chat.messages.at(-1)?.content).toContain('会话不存在')

    vi.stubGlobal(
      'fetch',
      routeFetch([
        ['/model-settings', () => jsonResponse(modelSettings)],
        ['/chat', () => sseResponse([['answer', '第二轮']])],
      ]).fetch,
    )
    expect(await chat.send('第二轮')).toBe('sent')
    expect(stub.calls.filter((call) => call.url === '/chat')).toHaveLength(1)
  })
})

describe('一轮的正文与引用', () => {
  it('token 累积，answer 整体替换，来源到达顺序不影响引用', async () => {
    await ready([
      [
        '/chat',
        () =>
          sseResponse([
            ['conversation', { id: 'c-1', title: '新会话' }],
            ['thinking', 'x'],
            ['tool', { name: 'search_relative_from_chromadb', args: { query: 'go' } }],
            ['tool_done', { name: 'search_relative_from_chromadb', status: 'ok', preview: '3 命中', arguments: '{}' }],
            ['token', '半成品'],
            ['sources', [{ index: 1, file_name: 'Go.md', quote: 'q' }]],
            ['answer', '最终正文 [[cite:1]]'],
          ]),
      ],
    ])
    const chat = useChatStore()
    await chat.send('Go 并发')

    const answer = chat.messages.at(-1)
    expect(answer?.role).toBe('assistant')
    expect(answer?.content).toBe('最终正文 [[cite:1]]')
    expect(answer?.citations).toEqual([{ index: 1, file_name: 'Go.md', quote: 'q' }])
    expect(answer?.toolSteps.map((step) => step.name)).toContain('search_relative_from_chromadb')
    expect(answer?.live).toBe(false)
  })

  it('新会话在 conversation 事件后拿到正式 id，临时键下的内容跟着搬过去', async () => {
    await ready([
      [
        '/chat',
        () =>
          sseResponse([
            ['conversation', { id: 'real-1', title: '新会话' }],
            ['answer', '好的'],
          ]),
      ],
      ['/conversations', () => jsonResponse([])],
    ])
    const chat = useChatStore()
    chat.patchActivePanel({ fileName: 'Go.md', dirty: true, text: '草稿正文' })

    await chat.send('新会话的第一个问题')

    expect(chat.currentId).toBe('real-1')
    // 临时键的面板搬到了正式 id 下，正文没有丢。
    expect(chat.panels['real-1']?.text).toBe('草稿正文')
    expect(chat.panels[citePaneKey(null)]).toBeUndefined()
  })
})

describe('会话之间的面板隔离', () => {
  it('两个会话各有一份快照，切回来还是自己的内容', async () => {
    await ready([
      ['/conversations/', () => jsonResponse(messages)],
      ['/notes/', () => jsonResponse({ file_name: 'Go.md', content: 'Go 正文' })],
    ])
    const chat = useChatStore()

    await chat.openConversation('c-1')
    chat.patchActivePanel({ fileName: 'Go.md', dirty: true, text: '会话一的草稿' })
    await chat.openConversation('c-2')
    chat.patchActivePanel({ fileName: 'Rust.md', dirty: true, text: '会话二的草稿' })

    expect(chat.panel.text).toBe('会话二的草稿')
    await chat.openConversation('c-1')
    expect(chat.panel.text).toBe('会话一的草稿')
    // 切会话不丢未保存内容，所以离开保护仍然成立。
    expect(chat.anyPanelDirty).toBe(true)
  })

  it('服务端草稿进快照，本地未保存的编辑优先保留', async () => {
    await ready()
    const chat = useChatStore()
    chat.currentId = 'c-1'

    chat.applyServerDraft('c-1', draft)
    expect(chat.panel.mode).toBe('draft')
    expect(chat.panel.text).toBe(draft.content)

    chat.patchActivePanel({ text: '我改过的正文', dirty: true })
    chat.applyServerDraft('c-1', { ...draft, content: '服务端新正文' })
    // 未保存的编辑不被旧的服务端快照覆盖。
    expect(chat.panel.text).toBe('我改过的正文')
    expect(chat.panel.dirty).toBe(true)
  })
})

describe('草稿的保存与审批边界', () => {
  async function withDraftPanel() {
    const stub = await ready([
      ['/chat/draft', () => jsonResponse({ status: 'updated', pending_draft: draft })],
      ['/chat/review', () => jsonResponse({ status: 'written', action: 'append', file_name: 'Go.md' })],
    ])
    const chat = useChatStore()
    chat.currentId = 'c-1'
    chat.openDraft(draft)
    await Promise.resolve()
    return { chat, stub }
  }

  it('保存草稿只调 PUT /chat/draft，不碰笔记', async () => {
    const { chat, stub } = await withDraftPanel()
    chat.patchActivePanel({ text: '## 新正文\n' })

    expect(await chat.saveDraftContent()).toBe(true)
    expect(stub.calls.some((call) => call.url === '/chat/draft')).toBe(true)
    expect(stub.calls.some((call) => call.url.startsWith('/notes/'))).toBe(false)
    const call = stub.calls.find((item) => item.url === '/chat/draft')!
    expect(call.init.method).toBe('PUT')
    expect(bodyOf(call)).toMatchObject({ thread_id: 'c-1', content: '## 新正文\n' })
  })

  it('同意前先把未保存正文落库，再调 review', async () => {
    const { chat, stub } = await withDraftPanel()
    chat.patchActivePanel({ text: '## 改过的正文\n', dirty: true })

    await chat.reviewDraft({ action: 'approve' })

    const order = stub.calls.map((call) => call.url)
    expect(order.indexOf('/chat/draft')).toBeLessThan(order.indexOf('/chat/review'))
    expect(stub.calls.some((call) => call.url.startsWith('/notes/'))).toBe(false)
  })

  it('保存失败就不继续审批', async () => {
    const stub = routeFetch([
      ['/model-settings', () => jsonResponse(modelSettings)],
      ['/chat/draft', () => jsonResponse({ detail: 'no pending draft' }, 409)],
      ['/chat/review', () => jsonResponse({ status: 'written' })],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const models = useModelsStore()
    await models.fetchStatus(true)
    const chat = useChatStore()
    chat.currentId = 'c-1'
    chat.openDraft(draft)
    await Promise.resolve()
    chat.patchActivePanel({ text: '改过的正文', dirty: true })

    await chat.reviewDraft({ action: 'approve' })

    expect(stub.calls.some((call) => call.url === '/chat/review')).toBe(false)
    expect(chat.panel.text).toBe('改过的正文')
  })

  it('审批业务失败（HTTP 200 + error）保留草稿并可重试', async () => {
    const { chat } = await withDraftPanel()
    vi.stubGlobal(
      'fetch',
      routeFetch([
        ['/model-settings', () => jsonResponse(modelSettings)],
        ['/chat/review', () => jsonResponse({ error: '写盘失败' })],
      ]).fetch,
    )

    await chat.reviewDraft({ action: 'approve' })

    expect(chat.panel.draft).not.toBeNull()
    expect(chat.panel.hintLocate).toContain('写盘失败')
    expect(chat.messages.at(-1)?.content).toContain('审批失败')
  })

  it('拒绝走 review 的 reject，不动正文', async () => {
    const { chat, stub } = await withDraftPanel()
    await chat.reviewDraft({ action: 'reject' })

    const call = stub.calls.find((item) => item.url === '/chat/review')!
    expect(bodyOf(call)).toMatchObject({ thread_id: 'c-1', action: 'reject' })
    expect(chat.panel.mode).toBe('citation')
    expect(chat.panel.draft).toBeNull()
  })

  it('只有 append／create 才提供覆盖入口', async () => {
    await ready()
    const chat = useChatStore()
    chat.currentId = 'c-1'

    chat.openDraft(draft)
    await Promise.resolve()
    expect(chat.panelOverrideAvailable).toBe(true)

    chat.openDraft({ ...draft, action: 'replace' })
    await Promise.resolve()
    expect(chat.panelOverrideAvailable).toBe(false)
  })
})

describe('引用面板', () => {
  it('打开引用时按 quote 选中片段', async () => {
    await ready([
      ['/notes/', () => jsonResponse({ file_name: 'Go.md', content: '前言\n目标片段\n后记' })],
    ])
    const chat = useChatStore()
    chat.currentId = 'c-1'

    await chat.openCitation({ index: 1, file_name: 'Go.md', quote: '目标片段' })

    expect(chat.panel.fileName).toBe('Go.md')
    expect(chat.panel.mode).toBe('citation')
    expect(chat.panel.text).toContain('目标片段')
    expect(chat.panel.selStart).toBe('前言\n'.length)
    expect(chat.panel.selEnd).toBe('前言\n目标片段'.length)
    expect(chat.panel.hintLocate).toBe('')
  })

  it('片段失配时给出提示而不是静默', async () => {
    await ready([
      ['/notes/', () => jsonResponse({ file_name: 'Go.md', content: '这篇笔记已经改过了' })],
    ])
    const chat = useChatStore()
    chat.currentId = 'c-1'

    await chat.openCitation({ index: 1, file_name: 'Go.md', quote: '原来的片段' })

    expect(chat.panel.hintLocate).toBe('笔记已更新，原片段无法定位。')
  })

  it('打不开笔记时保留面板并说明原因', async () => {
    await ready([['/notes/', () => jsonResponse({ detail: 'not found' }, 404)]])
    const chat = useChatStore()
    chat.currentId = 'c-1'

    await chat.openCitation({ index: 1, file_name: 'Gone.md', quote: '' })

    expect(chat.panel.hintLocate).toBe('无法打开笔记。')
    expect(chat.panel.textDisabled).toBe(true)
  })

  it('保存引用写正式笔记，成功后清掉未保存标记', async () => {
    const stub = await ready([
      ['/notes/', () => jsonResponse({ file_name: 'Go.md', indexed: true })],
    ])
    const chat = useChatStore()
    chat.currentId = 'c-1'
    chat.patchActivePanel({
      fileName: 'Go.md',
      text: '## 编辑后的正文',
      textDisabled: false,
      dirty: true,
    })

    expect(await chat.saveCitation()).toBe(true)

    const call = stub.calls.find((item) => item.url === '/notes/Go.md')!
    expect(call.init.method).toBe('PUT')
    expect(bodyOf(call)).toEqual({ content: '## 编辑后的正文' })
    expect(chat.panel.dirty).toBe(false)
  })

  it('文件级引用（没有 quote）只打开整篇，不选区', async () => {
    await ready([
      ['/notes/', () => jsonResponse({ file_name: 'Go.md', content: '整篇正文' })],
    ])
    const chat = useChatStore()
    chat.currentId = 'c-1'

    await chat.openCitation({ index: 1, file_name: 'Go.md', quote: null })

    expect(chat.panel.selStart).toBe(0)
    expect(chat.panel.selEnd).toBe(0)
    expect(chat.panel.hintLocate).toBe('')
  })
})

describe('切换会话时的请求隔离', () => {
  it('慢请求不覆盖后来选中的会话', async () => {
    // 用一道闸门精确控制 c-1 的响应什么时候回来。
    let release = (): void => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const stub = routeFetch([
      ['/model-settings', () => jsonResponse(modelSettings)],
      [
        '/conversations/',
        async () => {
          await gate
          return jsonResponse(messages)
        },
      ],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const models = useModelsStore()
    await models.fetchStatus(true)
    const chat = useChatStore()

    const slow = chat.openConversation('c-1')
    // 等请求真的发出去了再切走，否则闸门还没人拿着。
    await vi.waitFor(() => {
      expect(stub.calls.some((call) => call.url.startsWith('/conversations/'))).toBe(true)
    })

    chat.currentId = 'c-2'
    release()
    await slow

    // c-1 的迟到响应被丢弃：既不覆盖会话，也不往消息列表里塞内容。
    expect(chat.currentId).toBe('c-2')
    expect(chat.messages).toEqual([])
  })
})
