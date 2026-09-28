import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, extractErrorMessage, requestJson } from '@/shared/api/http'
import * as chatApi from '@/features/chat/api'
import * as notesApi from '@/features/notes/api'
import * as modelsApi from '@/features/models/api'
import { emptyResponse, jsonResponse, stubFetch } from '../fixtures/api'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('错误文案提取', () => {
  it('优先级是 message → detail → error → HTTP 状态码', () => {
    expect(extractErrorMessage({ message: '模型管理', detail: 'd', error: 'e' }, 500)).toBe(
      '模型管理',
    )
    expect(extractErrorMessage({ detail: 'd', error: 'e' }, 500)).toBe('d')
    expect(extractErrorMessage({ error: 'e' }, 500)).toBe('e')
    expect(extractErrorMessage({}, 503)).toBe('HTTP 503')
    expect(extractErrorMessage(null, 404)).toBe('HTTP 404')
  })

  it('忽略非字符串与空串，不把对象塞进提示里', () => {
    expect(extractErrorMessage({ detail: { nested: true } }, 422)).toBe('HTTP 422')
    expect(extractErrorMessage({ message: '' }, 400)).toBe('HTTP 400')
  })
})

describe('requestJson', () => {
  it('返回解析后的 JSON', async () => {
    vi.stubGlobal('fetch', stubFetch(() => jsonResponse({ id: 'c-1' })).fetch)
    await expect(requestJson('/conversations/c-1')).resolves.toEqual({ id: 'c-1' })
  })

  it('空响应体（204）返回 null 而不是抛解析错误', async () => {
    vi.stubGlobal('fetch', stubFetch(() => emptyResponse(204)).fetch)
    await expect(requestJson('/conversations/c-1', { method: 'DELETE' })).resolves.toBeNull()
  })

  it('非 2xx 抛出 ApiError，并带上后端文案与状态码', async () => {
    vi.stubGlobal(
      'fetch',
      stubFetch(() => jsonResponse({ detail: 'conversation not found' }, 404)).fetch,
    )
    await expect(requestJson('/conversations/x')).rejects.toThrowError(
      new ApiError(404, 'conversation not found'),
    )
  })

  it('业务失败却是 200 时不抛异常，交给调用方看返回体', async () => {
    // /chat/review 的失败就是这种形状：HTTP 200 + {"error": ...}。
    vi.stubGlobal('fetch', stubFetch(() => jsonResponse({ error: 'no pending draft' })).fetch)
    await expect(chatApi.reviewDraft({ thread_id: 't', action: 'approve' })).resolves.toEqual({
      error: 'no pending draft',
    })
  })

  it('网络异常转成 status 0 的 ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      stubFetch(() => {
        throw new TypeError('Failed to fetch')
      }).fetch,
    )
    await expect(requestJson('/notes')).rejects.toMatchObject({ status: 0 })
  })

  it('写请求不自动重试：一次调用只发一次请求', async () => {
    const stub = stubFetch(() => jsonResponse({ detail: 'boom' }, 500))
    vi.stubGlobal('fetch', stub.fetch)
    await expect(notesApi.writeNote('A.md', 'x')).rejects.toThrowError()
    expect(stub.calls).toHaveLength(1)
  })
})

describe('笔记接口的路径与请求体', () => {
  it('嵌套路径逐段编码，斜杠仍然是分隔符', () => {
    expect(notesApi.noteUrl('bak/context.md')).toBe('/notes/bak/context.md')
    expect(notesApi.noteUrl('a b/c d.md')).toBe('/notes/a%20b/c%20d.md')
  })

  it('移动笔记发送的是 from/to，不是内部变量名', async () => {
    const stub = stubFetch(() => jsonResponse({ file_name: 'bak/A.md', indexed: false }))
    vi.stubGlobal('fetch', stub.fetch)
    await notesApi.moveNote('A.md', 'bak/A.md')
    expect(stub.calls[0].url).toBe('/notes/move')
    expect(JSON.parse(String(stub.calls[0].init.body))).toEqual({
      from: 'A.md',
      to: 'bak/A.md',
    })
  })

  it('重命名目录同样发送 from/to', async () => {
    const stub = stubFetch(() =>
      jsonResponse({ from_name: 'bak', to_name: 'archive', files: [] }),
    )
    vi.stubGlobal('fetch', stub.fetch)
    await notesApi.renameFolder('bak', 'archive')
    expect(stub.calls[0].url).toBe('/notes/folders/rename')
    expect(JSON.parse(String(stub.calls[0].init.body))).toEqual({
      from: 'bak',
      to: 'archive',
    })
  })

  it('删除目录把名字编码进路径', async () => {
    const stub = stubFetch(() => jsonResponse({ name: 'a b', deleted: [] }))
    vi.stubGlobal('fetch', stub.fetch)
    await notesApi.deleteFolder('a b')
    expect(stub.calls[0].url).toBe('/notes/folders/a%20b')
    expect(stub.calls[0].init.method).toBe('DELETE')
  })

  it('补建索引用 POST 且不发多余请求体字段', async () => {
    const stub = stubFetch(() => jsonResponse({ file_name: 'A.md', indexed: true }))
    vi.stubGlobal('fetch', stub.fetch)
    await notesApi.indexNote('A.md')
    expect(stub.calls[0].url).toBe('/notes/A.md/index')
    expect(stub.calls[0].init.method).toBe('POST')
  })
})

describe('聊天接口的请求体', () => {
  it('保存草稿只发送 thread_id 与 content', async () => {
    const stub = stubFetch(() => jsonResponse({ status: 'updated', pending_draft: {} }))
    vi.stubGlobal('fetch', stub.fetch)
    await chatApi.saveDraftContent('t-1', '## 新正文\n')
    expect(stub.calls[0].url).toBe('/chat/draft')
    expect(stub.calls[0].init.method).toBe('PUT')
    expect(JSON.parse(String(stub.calls[0].init.body))).toEqual({
      thread_id: 't-1',
      content: '## 新正文\n',
    })
  })

  it('审批把 write_action 与 file_name 透传（override 时才带上）', async () => {
    const stub = stubFetch(() => jsonResponse({ status: 'written', file_name: 'A.md' }))
    vi.stubGlobal('fetch', stub.fetch)
    await chatApi.reviewDraft({
      thread_id: 't-1',
      action: 'override',
      write_action: 'append',
      file_name: 'A.md',
    })
    expect(stub.calls[0].url).toBe('/chat/review')
    expect(JSON.parse(String(stub.calls[0].init.body))).toEqual({
      thread_id: 't-1',
      action: 'override',
      write_action: 'append',
      file_name: 'A.md',
    })
  })

  it('重命名会话对 id 做编码', async () => {
    const stub = stubFetch(() => jsonResponse({ id: 'a/b', title: '新', updated_at: '' }))
    vi.stubGlobal('fetch', stub.fetch)
    await chatApi.renameConversation('a/b', '新')
    expect(stub.calls[0].url).toBe('/conversations/a%2Fb')
    expect(stub.calls[0].init.method).toBe('PATCH')
  })
})

describe('模型接口的相对路径与 revision', () => {
  it('除状态外都挂在 /model-settings 前缀下', async () => {
    const stub = stubFetch(() => jsonResponse({ verified: true, streaming: true, tool_calling: true }))
    vi.stubGlobal('fetch', stub.fetch)
    await modelsApi.testChatProfile({ label: 'a', provider: 'deepseek', model: 'm' })
    expect(stub.calls[0].url).toBe('/model-settings/chat/test')
  })

  it('删除配置把 expected_revision 放进查询参数', async () => {
    const stub = stubFetch(() => emptyResponse(204))
    vi.stubGlobal('fetch', stub.fetch)
    await modelsApi.deleteChatProfile('id/1', 7)
    expect(stub.calls[0].url).toBe('/model-settings/chat/profiles/id%2F1?expected_revision=7')
    expect(stub.calls[0].init.method).toBe('DELETE')
  })

  it('切换向量模型发送 model_id 与 expected_revision', async () => {
    const stub = stubFetch(() => jsonResponse({ unchanged: false, job: null }, 202))
    vi.stubGlobal('fetch', stub.fetch)
    await modelsApi.switchEmbedding('m-1', 9)
    expect(stub.calls[0].url).toBe('/model-settings/embedding/switch')
    expect(JSON.parse(String(stub.calls[0].init.body))).toEqual({
      model_id: 'm-1',
      expected_revision: 9,
    })
  })
})
