// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'

import { copyMessageText } from '@/features/chat/clipboard'
import { editUnavailableMessage, type ChatMessage } from '@/features/chat/store'

function message(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    key: 'k',
    role: 'user',
    content: '原文\n带换行',
    citations: [],
    toolSteps: [],
    live: false,
    traceLabel: '',
    ownerKey: '',
    id: 'u-1',
    turnId: 't-1',
    requestId: null,
    editable: false,
    editUnavailableReason: null,
    selectionAtStart: 0,
    ...overrides,
  }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('copyMessageText', () => {
  it('writes the raw content to the clipboard', async () => {
    const writeText = vi.fn(async () => undefined)
    vi.stubGlobal('navigator', { clipboard: { writeText } })

    expect(await copyMessageText('a\nb')).toBe(true)
    expect(writeText).toHaveBeenCalledWith('a\nb')
  })

  it('reports failure when the clipboard rejects', async () => {
    vi.stubGlobal('navigator', {
      clipboard: { writeText: vi.fn(async () => Promise.reject(new Error('denied'))) },
    })
    expect(await copyMessageText('a')).toBe(false)
  })

  it('reports failure when there is no clipboard API', async () => {
    vi.stubGlobal('navigator', {})
    expect(await copyMessageText('a')).toBe(false)
  })
})

describe('editUnavailableMessage', () => {
  it('returns null when the message is editable', () => {
    expect(editUnavailableMessage(message({ editable: true }))).toBeNull()
  })

  it('returns the server reason when editing is unavailable', () => {
    expect(
      editUnavailableMessage(
        message({ editable: false, editUnavailableReason: 'history_not_recoverable' }),
      ),
    ).toBe('history_not_recoverable')
  })

  it('falls back to a generic reason', () => {
    expect(editUnavailableMessage(message({ editable: false }))).toBe('历史消息暂不支持编辑')
  })
})
