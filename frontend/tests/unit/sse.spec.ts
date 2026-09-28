import { describe, expect, it } from 'vitest'

import { consumeSse, decodeChatEvent, TurnAccumulator } from '@/features/chat/sse'
import { messages, streamFromChunks, streamFromText, sseText } from '../fixtures/api'

async function collect(stream: ReadableStream<Uint8Array>) {
  const seen: Array<{ event: string; data: unknown }> = []
  await consumeSse(stream, (event) => seen.push(event))
  return seen
}

describe('consumeSse 的分片还原', () => {
  it('还原被切成任意字节的事件流', async () => {
    const text = sseText([
      ['conversation', { id: 'c-1', title: '你好' }],
      ['token', 'Hel'],
      ['token', 'lo'],
    ])
    // 逐字节切：UTF-8 的多字节字符与事件头都会被拆开。
    const seen = await collect(streamFromText(text, 1))
    expect(seen).toEqual([
      { event: 'conversation', data: { id: 'c-1', title: '你好' } },
      { event: 'token', data: 'Hel' },
      { event: 'token', data: 'lo' },
    ])
  })

  it('一次 read 里含多个事件时全部派发', async () => {
    const seen = await collect(
      streamFromChunks([`event: token\ndata: "a"\n\nevent: token\ndata: "b"\n\n`]),
    )
    expect(seen.map((item) => item.data)).toEqual(['a', 'b'])
  })

  it('一个事件跨多次 read 时才派发一次', async () => {
    const seen = await collect(streamFromChunks(['event: tok', 'en\ndata: ', '"split"', '\n\n']))
    expect(seen).toEqual([{ event: 'token', data: 'split' }])
  })

  it('空行把事件名复位成 token', async () => {
    const seen = await collect(streamFromChunks(['event: sources\ndata: []\n\ndata: "x"\n\n']))
    expect(seen[0].event).toBe('sources')
    expect(seen[1]).toEqual({ event: 'token', data: 'x' })
  })

  it('注释心跳被忽略', async () => {
    const seen = await collect(
      streamFromChunks([': keep-alive\n\n', 'event: token\ndata: "x"\n\n']),
    )
    expect(seen).toEqual([{ event: 'token', data: 'x' }])
  })

  it('流结束时末行没有换行也派发', async () => {
    const seen = await collect(streamFromChunks(['event: token\ndata: "tail"']))
    expect(seen).toEqual([{ event: 'token', data: 'tail' }])
  })

  it('data 不是 JSON 时按纯文本处理', async () => {
    const seen = await collect(streamFromChunks(['event: token\ndata: plain\n\n']))
    expect(seen).toEqual([{ event: 'token', data: 'plain' }])
  })
})

describe('decodeChatEvent 的协议校验', () => {
  it('把服务端的九种事件解码成带类型的领域事件', () => {
    const cases: Array<[string, unknown, string]> = [
      ['conversation', { id: 'c-1', title: 't' }, 'conversation'],
      ['thinking', 'x', 'thinking'],
      ['generating', 'x', 'generating'],
      ['think', '想一下', 'think'],
      ['tool', { name: 'read_file', args: { file_name: 'A.md' } }, 'tool'],
      ['tool_done', { name: 'read_file', status: 'ok', preview: 'p', arguments: '{}' }, 'tool_done'],
      ['draft', { action: 'create', file_name: 'C.md', content: 'x' }, 'draft'],
      ['sources', [{ index: 1, file_name: 'Go.md' }], 'sources'],
      ['answer', '完整正文', 'answer'],
    ]
    for (const [event, data, expected] of cases) {
      expect(decodeChatEvent({ event, data }).type).toBe(expected)
    }
  })

  it('形状不对的事件不会伪装成正文或引用', () => {
    expect(decodeChatEvent({ event: 'answer', data: 42 })).toEqual({
      type: 'unknown',
      event: 'answer',
    })
    expect(decodeChatEvent({ event: 'token', data: { a: 1 } })).toEqual({
      type: 'unknown',
      event: 'token',
    })
    expect(decodeChatEvent({ event: 'conversation', data: { title: 'no id' } })).toEqual({
      type: 'unknown',
      event: 'conversation',
    })
  })

  it('未知事件名落到 unknown，调用方可以选择忽略', () => {
    expect(decodeChatEvent({ event: 'future_thing', data: 'x' })).toEqual({
      type: 'unknown',
      event: 'future_thing',
    })
  })

  it('sources 不是数组时给空列表而不是 undefined', () => {
    expect(decodeChatEvent({ event: 'sources', data: null })).toEqual({
      type: 'sources',
      citations: [],
    })
  })
})

describe('TurnAccumulator 的一轮状态', () => {
  function feed(events: Array<[string, unknown]>): TurnAccumulator {
    const turn = new TurnAccumulator()
    for (const [event, data] of events) turn.apply(decodeChatEvent({ event, data }))
    return turn
  }

  it('token 逐段追加', () => {
    const turn = feed([
      ['token', 'Go '],
      ['token', '用 '],
      ['token', 'goroutine'],
    ])
    expect(turn.rawText).toBe('Go 用 goroutine')
  })

  it('answer 整体替换 token 缓冲，且引用保留', () => {
    const citations = [{ index: 1, file_name: 'Go.md', quote: 'q' }]
    const turn = feed([
      ['token', '草稿'],
      ['sources', citations],
      ['token', '片段'],
      ['answer', '服务端清理后的完整正文 [[cite:1]]'],
    ])
    expect(turn.rawText).toBe('服务端清理后的完整正文 [[cite:1]]')
    expect(turn.citations).toEqual(citations)
  })

  it('sources 晚于 answer 到达也不丢引用', () => {
    const citations = [{ index: 1, file_name: 'Go.md', quote: 'q' }]
    const late = feed([
      ['answer', '正文 [[cite:1]]'],
      ['sources', citations],
    ])
    expect(late.citations).toEqual(citations)

    const early = feed([
      ['sources', citations],
      ['answer', '正文 [[cite:1]]'],
    ])
    expect(early.citations).toEqual(citations)
  })

  it('thinking → 工具 → 生成：阶段不会同时挂着两个进行中步骤', () => {
    const turn = feed([
      ['thinking', 'x'],
      ['think', '先看看'],
      ['tool', { name: 'search_relative_from_chromadb', args: { query: 'go' } }],
      ['tool_done', { name: 'search_relative_from_chromadb', status: 'ok', preview: '3 命中', arguments: '{}' }],
      ['token', '答案'],
    ])
    const names = turn.steps.map((step) => `${step.name}:${step.status || 'open'}`)
    expect(names).toEqual(['_think:ok', 'search_relative_from_chromadb:ok', '_gen:open'])
    expect(turn.steps[0].content).toBe('先看看')
    expect(turn.steps[1].preview).toBe('3 命中')
  })

  it('同一轮里同名工具再次调用会追加新步骤', () => {
    const turn = feed([
      ['tool', { name: 'read_file', args: { file_name: 'A.md' } }],
      ['tool_done', { name: 'read_file', status: 'ok', preview: '', arguments: '{}' }],
      ['tool', { name: 'read_file', args: { file_name: 'B.md' } }],
    ])
    expect(turn.steps.filter((step) => step.name === 'read_file')).toHaveLength(2)
  })

  it('finish 把未结束的步骤收尾', () => {
    const turn = feed([['thinking', 'x'], ['token', 'a']])
    turn.finish()
    expect(turn.steps.every((step) => step.status === 'ok')).toBe(true)
  })

  it('长思考内容被截断', () => {
    const turn = feed([['think', 'x'.repeat(5000)]])
    expect(turn.steps[0].content.length).toBe(4001)
    expect(turn.steps[0].content.endsWith('…')).toBe(true)
  })
})

describe('历史消息与实时流共用同一套引用数据', () => {
  it('历史消息里的 citations 能被解码器原样接受', () => {
    // 历史引用与实时 sources 是同一个形状，迁移后必须走同一套渲染逻辑。
    const cited = messages[1].citations
    const decoded = decodeChatEvent({ event: 'sources', data: cited })
    expect(decoded).toEqual({ type: 'sources', citations: cited })
  })
})
