import { describe, expect, it } from 'vitest'

import {
  citationMap,
  citeMark,
  localizeCitations,
  locateQuote,
  renderAssistantHtml,
} from '@/features/chat/citations'
import type { Citation } from '@/shared/api/types'

const citations: Citation[] = [
  { index: 1, file_name: 'Go.md', quote: 'goroutine 是 Go 的并发单元' },
  { index: 2, file_name: 'docs/Rust.md', quote: '所有权' },
  { index: 7, file_name: 'C.md', quote: '段错误' },
]

describe('citeMark', () => {
  it('1..20 用带圈数字，超出退回普通数字', () => {
    expect(citeMark(1)).toBe('①')
    expect(citeMark(2)).toBe('②')
    expect(citeMark(20)).toBe('⑳')
    expect(citeMark(21)).toBe('21')
    expect(citeMark(0)).toBe('0')
  })
})

describe('citationMap', () => {
  it('按服务端的 index 建表', () => {
    expect(Object.keys(citationMap(citations)).sort()).toEqual(['1', '2', '7'])
  })

  it('容忍空值与缺 index 的项', () => {
    expect(citationMap(null)).toEqual({})
    expect(citationMap([{ file_name: 'x.md' } as Citation])).toEqual({})
  })
})

describe('localizeCitations', () => {
  it('按首次出现重排成 1..n', () => {
    const text = '先说 [[cite:7]]，再说 [[cite:1]]，最后又提到 [[cite:7]]。'
    const result = localizeCitations(text, citations)
    expect(result.text).toBe('先说 [[cite:1]]，再说 [[cite:2]]，最后又提到 [[cite:1]]。')
    expect(result.citations.map((item) => item.index)).toEqual([1, 2])
    expect(result.citations[0].file_name).toBe('C.md')
    expect(result.citations[1].file_name).toBe('Go.md')
  })

  it('丢掉 citations 里没有的编号，不占位也不影响后面的编号', () => {
    const result = localizeCitations('a [[cite:99]] b [[cite:2]]', citations)
    expect(result.text).toBe('a  b [[cite:1]]')
    expect(result.citations).toHaveLength(1)
    expect(result.citations[0].file_name).toBe('docs/Rust.md')
  })

  it('没有引用时原样返回', () => {
    const result = localizeCitations('纯正文', citations)
    expect(result.text).toBe('纯正文')
    expect(result.citations).toEqual([])
  })
})

describe('renderAssistantHtml', () => {
  it('引用编号在 Markdown 解析前替换成可点的角标', () => {
    const html = renderAssistantHtml('用 [[cite:1]] 表达并发。', citations)
    expect(html).toContain('<sup class="cite-ref" data-cite="1">①</sup>')
    expect(html).toContain('<p>')
  })

  it('未知编号不会渲染出空的角标', () => {
    const html = renderAssistantHtml('x [[cite:42]] y', citations)
    expect(html).not.toContain('cite-ref')
  })

  it('空正文渲染成空串而不是空段落', () => {
    expect(renderAssistantHtml('', citations)).toBe('')
  })

  it('Markdown 结构照旧解析', () => {
    const html = renderAssistantHtml('## 标题\n\n- 一条\n', [])
    expect(html).toContain('<h2>标题</h2>')
    expect(html).toContain('<li>一条</li>')
  })
})

describe('locateQuote 的匹配优先级', () => {
  const haystack = '前言\n\ngoroutine 是 Go 的并发单元，通道用于通信。\n\n后记'

  it('原文精确匹配', () => {
    const located = locateQuote(haystack, 'goroutine 是 Go 的并发单元')
    expect(located.start).toBe(haystack.indexOf('goroutine 是 Go 的并发单元'))
    expect(located.length).toBe('goroutine 是 Go 的并发单元'.length)
  })

  it('带首尾空白时退一步用 trim 后的文本', () => {
    const located = locateQuote(haystack, '  goroutine 是 Go 的并发单元  ')
    expect(located.start).toBe(haystack.indexOf('goroutine 是 Go 的并发单元'))
    expect(located.length).toBe('goroutine 是 Go 的并发单元'.length)
  })

  it('空白形态不同时用前 32 字符种子定位', () => {
    const quote = 'goroutine\n是 Go 的并发单元'
    const located = locateQuote(haystack, quote)
    // 压缩空白后仍能找到，就退化成只选中种子片段。
    expect(located.start).toBe(haystack.indexOf('goroutine'))
    expect(located.length).toBeLessThanOrEqual(32)
  })

  it('完全找不到时返回 -1，调用方据此提示"原片段无法定位"', () => {
    expect(locateQuote(haystack, '这段内容根本不在笔记里')).toEqual({ start: -1, length: 0 })
  })

  it('空 quote 直接返回 -1（文件级引用只有文件名）', () => {
    expect(locateQuote(haystack, '')).toEqual({ start: -1, length: 0 })
    expect(locateQuote(haystack, null)).toEqual({ start: -1, length: 0 })
    expect(locateQuote(haystack, undefined)).toEqual({ start: -1, length: 0 })
  })

  it('重复引文命中首次出现的位置', () => {
    const twice = '甲 目标 乙 目标 丙'
    expect(locateQuote(twice, '目标').start).toBe(2)
  })
})
