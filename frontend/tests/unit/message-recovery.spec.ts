// @vitest-environment jsdom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/shared/ui/confirm', () => ({
  confirmDialog: vi.fn(async () => true),
  promptDialog: vi.fn(async () => null),
  alertDialog: vi.fn(async () => undefined),
  reportError: vi.fn(async () => undefined),
}))
vi.mock('@/shared/ui/toast', () => ({ showSaveToast: vi.fn() }))

import { useChatStore } from '@/features/chat/store'
import { jsonResponse, modelSettings, sseText, stubFetch } from '../fixtures/api'

const USER_MESSAGE = {
  id: 'u-1',
  role: 'user',
  content: '原始问题',
  created_at: 'x',
  turn_id: 't-1',
  citations: [],
  tool_steps: [],
  editable: true,
  edit_unavailable_reason: null,
}

const PREVIEW = {
  preview_id: 'p-1',
  conversation_id: 'c-1',
  can_apply: true,
  requires_confirmation: true,
  file_changes: [{ path: 'A.md', action: 'restore', target_hash: 'h0', current_hash: 'h1' }],
  folder_changes: [],
  conflicts: [],
  affected_messages: ['u-1'],
  state_revision: 3,
  workspace_seq: 5,
  content_digest: 'd',
  expires_at: null,
}

const JOB = {
  job_id: 'j-1',
  operation_id: 'op-1',
  conversation_id: 'c-1',
  status: 'succeeded',
  stage: 'succeeded',
  prepared_turn_id: 'run-9',
  error: null,
  retryable: true,
  plan: {},
}

function sseResponse(events: Array<[string, unknown]>): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(sseText(events)))
      controller.close()
    },
  })
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

function makeStub(overrides: Record<string, (init: RequestInit) => Response> = {}) {
  return stubFetch((url, init) => {
    for (const [prefix, handler] of Object.entries(overrides)) {
      if (url.startsWith(prefix)) return handler(init)
    }
    if (url === '/model-settings') return jsonResponse(modelSettings)
    if (url.includes('/messages')) return jsonResponse([USER_MESSAGE])
    if (url.startsWith('/conversations/') && url.endsWith('/recoveries/preview')) {
      return jsonResponse(PREVIEW)
    }
    if (url === '/conversations') return jsonResponse([])
    if (url.startsWith('/conversations/')) {
      return jsonResponse({ id: 'c-1', title: 't', updated_at: 'x', pending_draft: null, state_revision: 3 })
    }
    if (url === '/notes') return jsonResponse({ files: [], folders: [] })
    return jsonResponse({}, 500)
  })
}

async function readyWithMessage(stub: ReturnType<typeof makeStub>) {
  vi.stubGlobal('fetch', stub.fetch)
  const chat = useChatStore()
  await chat.openConversation('c-1')
  expect(chat.messages[0].editable).toBe(true)
  return chat
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('message recovery flow', () => {
  it('reload restores a failed durable recovery job', async () => {
    const failed = { ...JOB, status: 'failed', error: 'index unavailable', prepared_turn_id: null }
    const stub = makeStub({ '/conversations/c-1': () => jsonResponse({
      id: 'c-1', pending_draft: null, state_revision: 3, recovery: failed,
    }) })
    vi.stubGlobal('fetch', stub.fetch)
    const chat = useChatStore()
    await chat.openConversation('c-1')
    expect(chat.recoveryJob?.job_id).toBe('j-1')
    expect(chat.recoveryPhase).toBe('failed')
    expect(chat.recoveryError).toBe('index unavailable')
  })

  it('start failure reconnects the persisted job for retry', async () => {
    const stub = makeStub()
    const chat = await readyWithMessage(stub)
    chat.beginEdit(chat.messages[0])
    chat.updateEditingText('edited')
    await chat.submitEdit()
    const failed = { ...JOB, status: 'failed', error: 'index unavailable', prepared_turn_id: null }
    const next = makeStub({ '/conversations/c-1': (init) => init.method === 'POST'
      ? jsonResponse({ message: 'failed' }, 500)
      : jsonResponse({ id: 'c-1', pending_draft: null, state_revision: 3, recovery: failed }) })
    vi.stubGlobal('fetch', next.fetch)
    await chat.confirmRecovery()
    expect(chat.recoveryPhase).toBe('failed')
    expect(chat.recoveryJob?.job_id).toBe('j-1')
  })
  it('preview requires confirmation and cancel starts nothing', async () => {
    const stub = makeStub()
    const chat = await readyWithMessage(stub)

    chat.beginEdit(chat.messages[0])
    chat.updateEditingText('改过的问题')
    await chat.submitEdit()

    expect(chat.recoveryPhase).toBe('confirming')
    expect(stub.calls.some((c) => c.url.endsWith('/recoveries'))).toBe(false)

    chat.cancelRecovery()
    expect(chat.recoveryPhase).toBe('idle')
    expect(stub.calls.some((c) => c.url.endsWith('/recoveries'))).toBe(false)
    expect(stub.calls.some((c) => c.url === '/chat')).toBe(false)
  })

  it('confirms with the file paths then runs the prepared turn', async () => {
    const stub = makeStub({
      '/conversations/c-1/recoveries/preview': () => jsonResponse(PREVIEW),
      '/recoveries/j-1': () => jsonResponse(JOB),
      '/conversations/c-1/recoveries': () => jsonResponse(JOB),
      '/chat': () =>
        sseResponse([
          ['conversation', { id: 'c-1', title: 't' }],
          ['token', '重新生成'],
          ['answer', '重新生成'],
          ['turn_complete', { status: 'completed', checkpoint_id: 'cp', state_revision: 4 }],
        ]),
    })
    const chat = await readyWithMessage(stub)

    chat.beginEdit(chat.messages[0])
    chat.updateEditingText('改过的问题')
    await chat.submitEdit()
    await chat.confirmRecovery()

    const start = stub.calls.find((c) => c.url === '/conversations/c-1/recoveries')
    expect(stub.calls.map((c) => c.url)).toContain('/conversations/c-1/recoveries')
    expect(JSON.parse(String(start!.init.body)).confirmed_file_changes).toEqual(['A.md'])

    const chatCall = stub.calls.find((c) => c.url === '/chat')
    expect(JSON.parse(String(chatCall!.init.body)).prepared_turn_id).toBe('run-9')
  })

  it('a conflict only offers cancel and never starts', async () => {
    const stub = makeStub({
      '/conversations/c-1/recoveries/preview': () =>
        jsonResponse({ ...PREVIEW, can_apply: false, conflicts: [{ path: 'A.md', reason: 'changed' }] }),
    })
    const chat = await readyWithMessage(stub)

    chat.beginEdit(chat.messages[0])
    chat.updateEditingText('改过的问题')
    await chat.submitEdit()

    expect(chat.recoveryPhase).toBe('conflict')
    await chat.confirmRecovery()
    expect(stub.calls.some((c) => c.url.endsWith('/recoveries'))).toBe(false)
  })

  it('unchanged text closes the editor without a preview', async () => {
    const stub = makeStub()
    const chat = await readyWithMessage(stub)

    chat.beginEdit(chat.messages[0])
    await chat.submitEdit()
    expect(chat.recoveryPhase).toBe('idle')
    expect(stub.calls.some((c) => c.url.includes('/recoveries/preview'))).toBe(false)
  })
})

it('ignores a preview returned after switching conversations', async () => {
  let release!: (r: Response) => void
  const base = makeStub()
  const delayed = stubFetch((url, init) => url.endsWith('/recoveries/preview') ? new Promise<Response>((resolve) => { release = resolve }) : base.fetch(url, init))
  const chat = await readyWithMessage(delayed)
  chat.beginEdit(chat.messages[0]); chat.updateEditingText('edited')
  const pending = chat.submitEdit()
  await vi.waitFor(() => expect(release).toBeTypeOf('function'))
  await chat.openConversation('c-2')
  release(jsonResponse(PREVIEW)); await pending
  expect(chat.currentId).toBe('c-2')
  expect(chat.recoveryPreview).toBeNull()
  expect(chat.recoveryPhase).toBe('idle')
})

it('late recovery success cannot run the prepared turn in a different conversation', async () => {
  let release!: (r: Response) => void
  const base = makeStub()
  const delayed = stubFetch((url, init) => url === '/conversations/c-1/recoveries' ? new Promise<Response>((resolve) => { release = resolve }) : base.fetch(url, init))
  const chat = await readyWithMessage(delayed)
  chat.beginEdit(chat.messages[0]); chat.updateEditingText('edited'); await chat.submitEdit()
  const pending = chat.confirmRecovery()
  await vi.waitFor(() => expect(release).toBeTypeOf('function'))
  await chat.openConversation('c-2')
  release(jsonResponse(JOB)); await pending
  expect(chat.currentId).toBe('c-2')
  expect(delayed.calls.some((c) => c.url === '/chat')).toBe(false)
})
