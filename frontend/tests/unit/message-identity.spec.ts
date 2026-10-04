// @vitest-environment jsdom
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// 对话框在这里没有挂载的组件；用桩避免等待用户点击。
vi.mock('@/shared/ui/confirm', () => ({
  confirmDialog: vi.fn(async () => true),
  promptDialog: vi.fn(async () => null),
  alertDialog: vi.fn(async () => undefined),
  reportError: vi.fn(async () => undefined),
}))
vi.mock('@/shared/ui/toast', () => ({ showSaveToast: vi.fn() }))

import { useChatStore } from '@/features/chat/store'
import { editUnavailableMessage } from '@/features/chat/store'
import { decodeChatEvent } from '@/features/chat/sse'
import { jsonResponse, modelSettings, sseText, stubFetch } from '../fixtures/api'

function sseResponse(events: Array<[string, unknown]>): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(sseText(events)))
      controller.close()
    },
  })
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('decodeChatEvent identity', () => {
  it('decodes user_message with the client request id', () => {
    const event = decodeChatEvent({
      event: 'user_message',
      data: {
        message_id: 'srv-1',
        turn_id: 't-1',
        run_id: 'r-1',
        request_id: 'req-1',
        state_revision: 3,
      },
    })
    expect(event).toEqual({
      type: 'user_message',
      messageId: 'srv-1',
      turnId: 't-1',
      runId: 'r-1',
      requestId: 'req-1',
      stateRevision: 3,
    })
  })

  it('decodes turn_complete', () => {
    expect(
      decodeChatEvent({
        event: 'turn_complete',
        data: { status: 'completed', checkpoint_id: 'cp-1', state_revision: 0 },
      }),
    ).toEqual({
      type: 'turn_complete',
      status: 'completed',
      checkpointId: 'cp-1',
      stateRevision: 0,
    })
  })
})

describe('message identity in the store', () => {
  it('keeps distinct ids for identical text and reflects editability', async () => {
    const duplicated = [
      { id: 'u-1', role: 'user', content: '重复', created_at: 'x', turn_id: 't1', citations: [], tool_steps: [], editable: false, edit_unavailable_reason: 'recovery_not_available' },
      { id: 'u-2', role: 'user', content: '重复', created_at: 'x', turn_id: 't2', citations: [], tool_steps: [], editable: false, edit_unavailable_reason: 'recovery_not_available' },
    ]
    const { fetch } = stubFetch((url) => {
      if (url.includes('/messages')) return jsonResponse(duplicated)
      if (url.startsWith('/conversations/')) {
        return jsonResponse({
          id: 'c-1',
          title: 't',
          updated_at: 'x',
          pending_draft: null,
        })
      }
      return jsonResponse({}, 500)
    })
    vi.stubGlobal('fetch', fetch)

    const chat = useChatStore()
    await chat.openConversation('c-1')

    const ids = chat.messages.map((m) => m.id)
    expect(ids).toEqual(['u-1', 'u-2'])
    expect(chat.messages[0].turnId).toBe('t1')
    expect(editUnavailableMessage(chat.messages[0])).toBe('recovery_not_available')
  })

  it('replaces the optimistic user row by request id, not by text', async () => {
    const { fetch } = stubFetch((url, init) => {
      if (url === '/model-settings') return jsonResponse(modelSettings)
      if (url === '/conversations') return jsonResponse([])
      if (url === '/chat') {
        const body = JSON.parse(String(init.body ?? '{}'))
        return sseResponse([
          ['conversation', { id: 'c-9', title: 't' }],
          [
            'user_message',
            {
              message_id: 'srv-u',
              turn_id: 't-9',
              run_id: 'r-9',
              request_id: body.request_id,
              state_revision: 0,
            },
          ],
          ['token', '你好'],
          ['answer', '你好'],
          ['turn_complete', { status: 'completed', checkpoint_id: 'cp', state_revision: 0 }],
        ])
      }
      return jsonResponse({}, 500)
    })
    vi.stubGlobal('fetch', fetch)

    const chat = useChatStore()
    expect(await chat.send('你好')).toBe('sent')

    const users = chat.messages.filter((m) => m.role === 'user')
    expect(users.map((m) => m.id)).toEqual(['srv-u'])
    expect(users[0].turnId).toBe('t-9')
  })
})
