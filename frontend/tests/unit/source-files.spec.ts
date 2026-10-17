import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'

import { openChatStream } from '@/features/chat/api'
import { useSourceFilesStore } from '@/features/source-files/store'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

describe('source file client contracts', () => {
  it('sends only selected attachment IDs with a chat turn', async () => {
    const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = []
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ input, init })
      return new Response('', { status: 200 })
    })
    await openChatStream('summarize', null, 'request-1', undefined, ['file-1'])
    expect(JSON.parse(String(calls[0]?.init?.body))).toMatchObject({
      question: 'summarize', attachment_ids: ['file-1'],
    })
  })

  it('loads files and one-level folders independently from notes', async () => {
    const paths: string[] = []
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      const path = String(input)
      paths.push(path)
      return Response.json(path.endsWith('/folders') ? { folders: ['study'] } : [{
        id: 'file-1', display_name: 'lesson.txt', folder: 'study', media_type: 'text/plain',
        size_bytes: 10, status: 'ready', error: null, created_at: '', updated_at: '',
      }])
    })
    const store = useSourceFilesStore()
    await store.refresh()
    expect(paths).toEqual(['/source-files', '/source-files/folders'])
    expect(store.files[0]?.display_name).toBe('lesson.txt')
    expect(store.folders).toEqual(['study'])
  })
})
