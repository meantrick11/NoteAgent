/**
 * 引用渲染与定位。这里是**原算法**的等价搬运，不趁机重写：
 *
 *  - 每条消息内的编号按"首次出现"重排成 1..n，未知编号的标记直接丢掉；
 *  - `locateQuote` 的匹配优先级是 原文 → trim 后 → 压缩空白后取前 32 字符种子；
 *  - `read_file` 的引用只有文件名没有 quote，点击打开整篇，仍然不做段落定位。
 *
 * 历史消息与实时 sources 走同一套函数，两边的引用样式与行为必须一致。
 */

import { marked } from 'marked'

import type { Citation } from '@/shared/api/types'

/** 引用标记的字形：1..20 用带圈的 ①②…，超出就退回普通数字。 */
export function citeMark(index: number): string {
  if (index >= 1 && index <= 20) return String.fromCharCode(0x245f + index)
  return String(index)
}

/** 按服务端给的 index 建索引表；缺 index 的项忽略。 */
export function citationMap(citations: Citation[] | undefined | null): Record<number, Citation> {
  const map: Record<number, Citation> = {}
  for (const item of citations ?? []) {
    if (item && item.index != null) map[item.index] = item
  }
  return map
}

export interface LocalizedCitations {
  text: string
  citations: Citation[]
}

/**
 * 把 [[cite:n]] 重排成 1..n：只在标签实际出现且能在 citations 里找到时才占用编号，
 * 因此正文里引用了几条，面板里就只有几条。
 */
export function localizeCitations(
  text: string,
  citations: Citation[] | undefined | null,
): LocalizedCitations {
  const byOld = citationMap(citations)
  const oldToNew: Record<number, number> = {}
  const used: Citation[] = []
  const rewritten = String(text ?? '').replace(/\[\[cite:(\d+)\]\]/g, (_match, raw: string) => {
    const old = Number(raw)
    const item = byOld[old]
    if (!item) return ''
    if (oldToNew[old] == null) {
      oldToNew[old] = used.length + 1
      used.push({ ...item, index: oldToNew[old] })
    }
    return `[[cite:${oldToNew[old]}]]`
  })
  return { text: rewritten, citations: used }
}

/**
 * 助手正文的渲染：先重排引用并换成 <sup class="cite-ref" data-cite="n">，再交给 marked。
 * 引用标记必须在 Markdown 解析之前插入，否则会被当成普通文字。
 */
export function renderAssistantHtml(
  text: string,
  citations: Citation[] | undefined | null,
): string {
  const local = localizeCitations(text, citations)
  const map = citationMap(local.citations)
  const withMarks = local.text.replace(/\[\[cite:(\d+)\]\]/g, (_match, raw: string) => {
    const n = Number(raw)
    if (!map[n]) return ''
    return `<sup class="cite-ref" data-cite="${n}">${citeMark(n)}</sup>`
  })
  return withMarks ? (marked.parse(withMarks) as string) : ''
}

export interface QuoteLocation {
  start: number
  length: number
}

/** 找不到返回 start = -1。 */
export function locateQuote(haystack: string, quote: string | null | undefined): QuoteLocation {
  if (!quote) return { start: -1, length: 0 }
  let index = haystack.indexOf(quote)
  if (index >= 0) return { start: index, length: quote.length }

  const trimmed = quote.trim()
  index = haystack.indexOf(trimmed)
  if (index >= 0) return { start: index, length: trimmed.length }

  const compactHaystack = haystack.replace(/\s+/g, ' ')
  const compactQuote = trimmed.replace(/\s+/g, ' ')
  if (compactHaystack.indexOf(compactQuote) < 0) return { start: -1, length: 0 }

  // 空白被改写后没法直接映射回原文，退化成用前 32 字符定位并只选中这一段。
  const seed = compactQuote.slice(0, Math.min(32, compactQuote.length))
  index = haystack.indexOf(seed)
  if (index >= 0) return { start: index, length: seed.length }
  return { start: -1, length: 0 }
}
