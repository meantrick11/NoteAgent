/**
 * 隔离测试用的固定响应与 SSE 构造器。
 *
 * 单元测试与 Playwright 都用这一份，保证「后端合同」只有一个写法；
 * 这里只放能被 pydantic schema 校验通过的形状，不发明新字段。
 */

import type {
  Conversation,
  ConversationDetail,
  EmbeddingCandidate,
  EmbeddingJob,
  Message,
  ModelSettingsStatus,
  NotesList,
  PendingDraft,
} from '@/shared/api/types'

export const conversations: Conversation[] = [
  { id: 'c-1', title: '你好', updated_at: '2026-09-28T10:00:00Z' },
  { id: 'c-2', title: 'Agent 笔记', updated_at: '2026-09-28T09:00:00Z' },
]

export const draft: PendingDraft = {
  action: 'append',
  file_name: 'Go.md',
  content: '## 并发模型\n\n- goroutine\n',
  reason: '补一节',
  similar: ['Go.md'],
  existing_files: ['Go.md', 'Rust.md'],
}

export const createDraft: PendingDraft = {
  action: 'create',
  file_name: 'C.md',
  content: '## 要点\n\n- x\n',
  reason: '新文件',
  similar: [],
  existing_files: [],
}

export const conversationDetail: ConversationDetail = {
  ...conversations[0],
  pending_draft: draft,
}

export const messages: Message[] = [
  {
    id: 'm-1',
    role: 'user',
    content: 'Go 的并发模型是什么？',
    created_at: '2026-09-28T10:00:01Z',
    citations: [],
    tool_steps: [],
  },
  {
    id: 'm-2',
    role: 'assistant',
    content: 'Go 用 goroutine 和 channel [[cite:1]] 表达并发。',
    created_at: '2026-09-28T10:00:02Z',
    citations: [
      { index: 1, file_name: 'Go.md', chunk_index: 0, quote: 'goroutine 是 Go 的并发单元' },
      { index: 2, file_name: 'docs/Rust.md', chunk_index: 3, quote: '所有权' },
    ],
    tool_steps: [
      { name: 'search_relative_from_chromadb', status: 'ok', preview: '3 命中', arguments: '{"query":"go 并发"}' },
      { name: 'read_file', status: 'ok', preview: 'ok', arguments: '{"file_name":"Go.md"}' },
    ],
  },
]

export const notes: NotesList = {
  files: [
    { file_name: 'Go.md', folder: '', mtime: 1758998400, indexed: true },
    { file_name: 'Rust.md', folder: '', mtime: 1758998400, indexed: false },
    { file_name: 'bak/context.md', folder: 'bak', mtime: 1758998400, indexed: true },
  ],
  folders: ['bak'],
}

export const embeddingCandidates: EmbeddingCandidate[] = [
  {
    model_id: 'intfloat/multilingual-e5-small',
    label: 'multilingual-e5-small',
    availability: 'available',
    reason: null,
    active: true,
  },
  {
    model_id: 'BAAI/bge-small-zh-v1.5',
    label: 'bge-small-zh-v1.5',
    availability: 'available',
    reason: null,
    active: false,
  },
  {
    model_id: 'some/missing-model',
    label: 'missing-model',
    availability: 'incomplete',
    reason: '本地缓存不完整',
    active: false,
  },
]

export const embeddingJob: EmbeddingJob = {
  id: 'job-1',
  status: 'running',
  stage: 'indexing',
  completed: 3,
  total: 10,
  active_model: 'intfloat/multilingual-e5-small',
  target_model: 'BAAI/bge-small-zh-v1.5',
  error: null,
  started_at: '2026-09-28T10:00:00Z',
  finished_at: null,
}

export const modelSettings: ModelSettingsStatus = {
  revision: 7,
  chat_profiles: [
    {
      id: 'env-default',
      label: '环境默认',
      provider: 'deepseek',
      model: 'deepseek-v4-flash',
      base_url: 'https://api.deepseek.com',
      auth_mode: 'api_key',
      context_window: 32768,
      has_api_key: true,
      credential_source: 'env',
    },
    {
      id: 'local',
      label: '本地服务',
      provider: 'openai-compatible',
      model: 'qwen2.5',
      base_url: 'http://localhost:1234/v1',
      auth_mode: 'none',
      context_window: 16384,
      has_api_key: false,
      credential_source: 'ui',
    },
  ],
  active_chat: {
    id: 'env-default',
    label: '环境默认',
    provider: 'deepseek',
    model: 'deepseek-v4-flash',
    base_url: 'https://api.deepseek.com',
    auth_mode: 'api_key',
    context_window: 32768,
    has_api_key: true,
    credential_source: 'env',
  },
  active_embedding: {
    model_id: 'intfloat/multilingual-e5-small',
    resolved_revision: 'rev-1',
    collection: 'my_knowledge',
    fingerprint: 'fp-1',
  },
  retrieval_available: true,
  retrieval_problem: null,
  retrieval_state: 'ok',
  indexed_files: 120,
  corpus_files: 20,
  busy: false,
  embedding_job: null,
}

/** 构造一条 SSE 报文；两个换行结尾，与 FastAPI 的输出一致。 */
export function sseText(events: Array<[string, unknown]>): string {
  return events
    .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
    .join('')
}

/** 把文本按固定字节数切块，用来模拟 UTF-8 字符与事件跨块。 */
export function streamFromText(text: string, chunkSize: number): ReadableStream<Uint8Array> {
  const bytes = new TextEncoder().encode(text)
  let offset = 0
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (offset >= bytes.length) {
        controller.close()
        return
      }
      controller.enqueue(bytes.slice(offset, offset + chunkSize))
      offset += chunkSize
    },
  })
}

/** 一步到位的流，用于不关心分片的用例。 */
export function streamFromEvents(events: Array<[string, unknown]>): ReadableStream<Uint8Array> {
  return streamFromText(sseText(events), 4096)
}

/** 一次 read 返回一个分片的流，用于精确控制空行落在哪里。 */
export function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  let index = 0
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index >= chunks.length) {
        controller.close()
        return
      }
      controller.enqueue(new TextEncoder().encode(chunks[index]))
      index += 1
    },
  })
}

/** 一个最小可用的 JSON Response，用于被 fetch 桩返回。 */
export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(body === null ? '' : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export function emptyResponse(status = 204): Response {
  return new Response(null, { status })
}

/**
 * 按路径匹配的 fetch 桩。返回调用记录，便于断言请求体与调用次数。
 */
export function stubFetch(
  handler: (url: string, init: RequestInit) => Response | Promise<Response>,
): { calls: Array<{ url: string; init: RequestInit }>; fetch: typeof fetch } {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const impl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString()
    const options = init ?? {}
    calls.push({ url, init: options })
    return handler(url, options)
  }) as typeof fetch
  return { calls, fetch: impl }
}
