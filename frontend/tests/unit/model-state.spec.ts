// @vitest-environment jsdom
// 需要 DOM：store 用 visibilitychange／focus 绑定跨标签刷新。
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  POLL_INTERVAL_MS,
  STATUS_MAX_AGE_MS,
  useModelsStore,
} from '@/features/models/store'
import type { ChatProfile } from '@/shared/api/types'
import {
  embeddingCandidates,
  embeddingJob,
  jsonResponse,
  modelSettings,
  stubFetch,
} from '../fixtures/api'

type Handler = (init: RequestInit) => Response | Promise<Response>

/** 按 URL 前缀分发的 fetch 桩；长前缀要先注册。 */
function routeFetch(routes: Array<[string, Handler]>) {
  return stubFetch((url, init) => {
    for (const [prefix, handler] of routes) {
      if (url.startsWith(prefix)) return handler(init)
    }
    return jsonResponse({ detail: `no stub for ${url}` }, 500)
  })
}

function newProfile(): ChatProfile {
  return {
    id: 'new',
    label: '新配置',
    provider: 'deepseek',
    model: 'deepseek-chat',
    base_url: '',
    auth_mode: 'api_key',
    context_window: 32768,
    has_api_key: true,
    credential_source: 'ui',
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('状态读取', () => {
  it('fetchStatus 把服务端状态写进 store', async () => {
    vi.stubGlobal('fetch', routeFetch([['/model-settings', () => jsonResponse(modelSettings)]]).fetch)
    const store = useModelsStore()
    await store.fetchStatus(true)

    expect(store.revision).toBe(7)
    expect(store.chatProfiles).toHaveLength(2)
    expect(store.activeChat?.id).toBe('env-default')
    expect(store.activeEmbedding?.model_id).toBe('intfloat/multilingual-e5-small')
    expect(store.indexedFiles).toBe(120)
    expect(store.corpusFiles).toBe(20)
    expect(store.busy).toBe(false)
  })

  it('读状态失败时保留上一次已知状态而不是清零', async () => {
    const stub = routeFetch([
      ['/model-settings', () => jsonResponse(modelSettings)],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    await store.fetchStatus(true)
    expect(store.revision).toBe(7)

    vi.stubGlobal(
      'fetch',
      routeFetch([['/model-settings', () => jsonResponse({ detail: 'boom' }, 500)]]).fetch,
    )
    await store.fetchStatus(true)
    expect(store.revision).toBe(7)
    expect(store.chatProfiles).toHaveLength(2)
  })

  it('同一标签页 1 秒内的重复读取被合并', async () => {
    const stub = routeFetch([['/model-settings', () => jsonResponse(modelSettings)]])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    await store.fetchStatus(true)
    await store.fetchStatus()
    expect(stub.calls).toHaveLength(1)
  })
})

describe('维护窗口与流式状态', () => {
  it('busy 时 canSend 为 false，笔记与聊天写入都要看它', async () => {
    vi.stubGlobal(
      'fetch',
      routeFetch([['/model-settings', () => jsonResponse({ ...modelSettings, busy: true })]]).fetch,
    )
    const store = useModelsStore()
    await store.fetchStatus(true)
    expect(store.canSend).toBe(false)
  })

  it('流式期间锁定模型入口，但不影响 canSend', async () => {
    vi.stubGlobal('fetch', routeFetch([['/model-settings', () => jsonResponse(modelSettings)]]).fetch)
    const store = useModelsStore()
    await store.fetchStatus(true)
    expect(store.modelActionsLocked).toBe(false)

    store.setStreaming(true)
    expect(store.modelActionsLocked).toBe(true)
    expect(store.canSend).toBe(true)
  })

  it('重建任务进行中同样锁定模型入口', async () => {
    vi.stubGlobal(
      'fetch',
      routeFetch([
        ['/model-settings', () => jsonResponse({ ...modelSettings, embedding_job: embeddingJob })],
      ]).fetch,
    )
    const store = useModelsStore()
    await store.fetchStatus(true)
    expect(store.jobRunning).toBe(true)
    expect(store.modelActionsLocked).toBe(true)
    store.dispose()
  })
})

describe('聊天配置的写操作', () => {
  it('保存时带上读到的 expected_revision', async () => {
    const saved = newProfile()
    const stub = routeFetch([
      ['/model-settings/chat/profiles', () => jsonResponse(saved, 201)],
      ['/model-settings', () => jsonResponse(modelSettings)],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    await store.fetchStatus(true)
    await store.submitProfile(
      { label: '新配置', provider: 'deepseek', model: 'deepseek-chat' },
      null,
      false,
    )

    const create = stub.calls.find((call) => call.url === '/model-settings/chat/profiles')
    expect(JSON.parse(String(create?.init.body)).expected_revision).toBe(7)
    expect(store.chatNotice).toEqual({ kind: 'ok', text: '已保存「新配置」（未启用）。' })
  })

  it('保存并启用走 activate 而不是普通保存', async () => {
    const stub = routeFetch([
      ['/model-settings/chat/activate', () => jsonResponse(newProfile())],
      ['/model-settings', () => jsonResponse(modelSettings)],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    await store.fetchStatus(true)
    await store.submitProfile({ label: '新配置', provider: 'deepseek', model: 'm' }, null, true)

    expect(stub.calls.some((call) => call.url === '/model-settings/chat/activate')).toBe(true)
    expect(stub.calls.some((call) => call.url === '/model-settings/chat/profiles')).toBe(false)
  })

  it('revision 冲突时给出错误提示并刷新状态', async () => {
    const stub = routeFetch([
      [
        '/model-settings/chat/profiles',
        () => jsonResponse({ message: 'revision 已过期，请刷新后重试' }, 409),
      ],
      ['/model-settings', () => jsonResponse(modelSettings)],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    await store.fetchStatus(true)
    const before = stub.calls.filter((call) => call.url === '/model-settings').length

    const ok = await store.submitProfile(
      { label: '新配置', provider: 'deepseek', model: 'm' },
      null,
      false,
    )

    expect(ok).toBe(false)
    expect(store.chatNotice).toEqual({
      kind: 'error',
      text: 'revision 已过期，请刷新后重试',
    })
    expect(stub.calls.filter((call) => call.url === '/model-settings').length).toBe(before + 1)
  })

  it('启用失败保留原 active 配置', async () => {
    vi.stubGlobal(
      'fetch',
      routeFetch([
        ['/model-settings/chat/activate', () => jsonResponse({ detail: '模型不可用' }, 400)],
        ['/model-settings', () => jsonResponse(modelSettings)],
      ]).fetch,
    )
    const store = useModelsStore()
    await store.fetchStatus(true)
    const ok = await store.activateProfile('local')

    expect(ok).toBe(false)
    expect(store.activeChat?.id).toBe('env-default')
    expect(store.chatNotice).toEqual({ kind: 'error', text: '模型不可用' })
  })
})

describe('向量模型切换与任务轮询', () => {
  it('unchanged 时不建任务、不进维护窗口', async () => {
    vi.stubGlobal(
      'fetch',
      routeFetch([
        ['/model-settings/embedding/switch', () => jsonResponse({ unchanged: true, job: null })],
        ['/model-settings', () => jsonResponse(modelSettings)],
      ]).fetch,
    )
    const store = useModelsStore()
    await store.fetchStatus(true)
    await store.switchEmbedding('intfloat/multilingual-e5-small')

    expect(store.embeddingJob).toBeNull()
    expect(store.busy).toBe(false)
    expect(store.embeddingNotice).toEqual({
      kind: 'ok',
      text: '当前已经在使用这个向量模型，索引也在。',
    })
  })

  it('202 立刻进入维护窗口，并轮询到任务结束后刷新状态与候选', async () => {
    vi.useFakeTimers()
    let polls = 0
    const finished = {
      ...embeddingJob,
      status: 'succeeded' as const,
      stage: 'done',
      completed: 10,
      finished_at: '2026-09-28T10:01:00Z',
    }
    // 任务结束后服务端仍保留最后一条 job 记录，状态里也是它——UI 靠它显示成功／失败。
    const settled = { ...modelSettings, embedding_job: finished, busy: false }
    const stub = routeFetch([
      ['/model-settings/embedding/switch', () => jsonResponse({ unchanged: false, job: embeddingJob }, 202)],
      [
        '/model-settings/jobs/',
        () => {
          polls += 1
          return jsonResponse(finished)
        },
      ],
      ['/model-settings/embeddings', () => jsonResponse(embeddingCandidates)],
      ['/model-settings', () => jsonResponse(settled)],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    await store.fetchStatus(true)

    await store.switchEmbedding('BAAI/bge-small-zh-v1.5')
    expect(store.busy).toBe(true)
    expect(store.embeddingJob?.status).toBe('running')

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS + 10)
    expect(polls).toBe(1)
    expect(store.embeddingJob?.status).toBe('succeeded')
    expect(store.busy).toBe(false)
    // 任务结束后补一次整轮状态与候选列表。
    expect(store.embeddingCandidates).toHaveLength(3)
    expect(stub.calls.some((call) => call.url === '/model-settings/embeddings')).toBe(true)
    store.dispose()
  })

  it('页面不可见时停止轮询，转前台后重新读取状态', async () => {
    vi.useFakeTimers()
    let polls = 0
    const stub = routeFetch([
      ['/model-settings/jobs/', () => {
        polls += 1
        return jsonResponse(embeddingJob)
      }],
      ['/model-settings', () => jsonResponse({ ...modelSettings, embedding_job: embeddingJob, busy: true })],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    store.init()
    await vi.advanceTimersByTimeAsync(0)
    expect(store.jobRunning).toBe(true)

    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    const before = polls
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)
    expect(polls).toBe(before)

    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
    document.dispatchEvent(new Event('visibilitychange'))
    await vi.advanceTimersByTimeAsync(0)
    expect(store.embeddingJob?.status).toBe('running')
    store.dispose()
  })
})

describe('监听与轮询的生命周期', () => {
  it('init 只绑定一份监听，重复调用不会叠加轮询', async () => {
    vi.useFakeTimers()
    let polls = 0
    const stub = routeFetch([
      ['/model-settings/jobs/', () => {
        polls += 1
        return jsonResponse(embeddingJob)
      }],
      ['/model-settings', () => jsonResponse({ ...modelSettings, embedding_job: embeddingJob, busy: true })],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    store.init()
    store.init()
    await vi.advanceTimersByTimeAsync(0)

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)
    // 一份轮询 = 3 次；叠加成两份会是 6 次。
    expect(polls).toBe(3)
    store.dispose()
  })

  it('dispose 后不再轮询', async () => {
    vi.useFakeTimers()
    let polls = 0
    const stub = routeFetch([
      ['/model-settings/jobs/', () => {
        polls += 1
        return jsonResponse(embeddingJob)
      }],
      ['/model-settings', () => jsonResponse({ ...modelSettings, embedding_job: embeddingJob, busy: true })],
    ])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    store.init()
    await vi.advanceTimersByTimeAsync(0)
    store.dispose()
    const before = polls
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3)
    expect(polls).toBe(before)
  })

  it('refreshIfStale 只在超过 5 秒后重新读取', async () => {
    vi.useFakeTimers()
    const stub = routeFetch([['/model-settings', () => jsonResponse(modelSettings)]])
    vi.stubGlobal('fetch', stub.fetch)
    const store = useModelsStore()
    await store.fetchStatus(true)
    expect(stub.calls).toHaveLength(1)

    await store.refreshIfStale()
    expect(stub.calls).toHaveLength(1)

    vi.setSystemTime(Date.now() + STATUS_MAX_AGE_MS + 1)
    await store.refreshIfStale()
    expect(stub.calls).toHaveLength(2)
  })
})

describe('索引状态文案', () => {
  it('索引不可用与「空但正常」不能混为一谈', async () => {
    vi.stubGlobal(
      'fetch',
      routeFetch([
        [
          '/model-settings',
          () =>
            jsonResponse({
              ...modelSettings,
              retrieval_available: false,
              retrieval_state: 'missing',
              retrieval_problem: '索引 collection 不存在，需要重建。',
            }),
        ],
      ]).fetch,
    )
    const store = useModelsStore()
    await store.fetchStatus(true)
    expect(store.retrievalStatus).toEqual({
      kind: 'error',
      text: '索引 collection 不存在，需要重建。',
    })
  })

  it('笔记目录为空时的空索引是正常状态', async () => {
    vi.stubGlobal(
      'fetch',
      routeFetch([
        [
          '/model-settings',
          () =>
            jsonResponse({
              ...modelSettings,
              retrieval_state: 'empty',
              indexed_files: 0,
              corpus_files: 0,
            }),
        ],
      ]).fetch,
    )
    const store = useModelsStore()
    await store.fetchStatus(true)
    expect(store.retrievalStatus).toEqual({
      kind: 'ok',
      text: '笔记目录为空，索引为空（状态正常）。',
    })
  })
})
