/**
 * 工具轨迹的文案。只负责"把步骤翻译成人话"，阶段推进本身在 TurnAccumulator 里。
 *
 * 实时与历史用两套措辞（Thinking... vs Thought、Exploring vs Explored），
 * 这是原页面的既有行为，迁移保持一致。
 */

import type { ToolStepState } from './sse'

/** 用参数里最像文件名的字段，取不到就退回 query。 */
export function toolFileName(args: unknown): string {
  if (!args) return ''
  if (typeof args === 'object') {
    const record = args as Record<string, unknown>
    return String(record.file_name ?? record.query ?? '')
  }
  try {
    const parsed = JSON.parse(String(args)) as Record<string, unknown>
    return String(parsed.file_name ?? parsed.query ?? '')
  } catch {
    return ''
  }
}

/** 同上，优先 query。 */
export function toolQuery(args: unknown): string {
  if (!args) return ''
  if (typeof args === 'object') {
    const record = args as Record<string, unknown>
    return String(record.query ?? record.file_name ?? '')
  }
  try {
    const parsed = JSON.parse(String(args)) as Record<string, unknown>
    return String(parsed.query ?? parsed.file_name ?? '')
  } catch {
    return ''
  }
}

/** 用过真正的笔记工具（非 _think / _gen）才值得展开轨迹。 */
export function hasRealTools(steps: ToolStepState[]): boolean {
  return steps.some((step) => step.name && step.name[0] !== '_')
}

/** 进行中的一句话。 */
export function toolLiveLabel(step: ToolStepState | string): string {
  const name = typeof step === 'string' ? step : step.name
  const args = typeof step === 'string' ? '' : step.arguments
  if (name === '_think') return 'Thinking...'
  if (name === '_gen') return 'Generating...'
  if (name === 'read_file') {
    const file = toolFileName(args)
    return file ? `Reading ${file}...` : 'Reading notes...'
  }
  if (name === 'list_files') return 'Listing notes...'
  if (name === 'search_relative_from_chromadb') return 'Searching notes...'
  if (name === 'propose_note') return 'Proposing a note...'
  return name ? `Calling ${name}...` : 'Thinking...'
}

/** 结束后的完成态。 */
export function toolFlowLabel(step: ToolStepState): string {
  const name = step.name ?? ''
  if (step.status === 'error') return `Failed ${name || 'tool'}`
  if (name === '_think') return 'Thought'
  if (name === '_gen') return 'Generated'
  if (name === 'read_file') {
    const file = toolFileName(step.arguments)
    return file ? `Read ${file}` : 'Read notes'
  }
  if (name === 'list_files') return 'Listed notes'
  if (name === 'search_relative_from_chromadb') {
    const query = toolQuery(step.arguments)
    return query ? `Searched ${query}` : 'Searched notes'
  }
  if (name === 'propose_note') {
    const file = toolFileName(step.arguments)
    return file ? `Proposed ${file}` : 'Proposed a note'
  }
  return name ? `Called ${name}` : ''
}

/** 一轮结束后的汇总：把这一步做过什么压成一句话。 */
export function englishSummary(steps: ToolStepState[], live: boolean): string {
  const tools = steps.filter((step) => step.name && step.name[0] !== '_')
  const count = (name: string) => tools.filter((step) => step.name === name).length
  const reads = count('read_file')
  const searches = count('search_relative_from_chromadb')
  const lists = count('list_files')
  const proposals = count('propose_note')
  const errors = tools.filter((step) => step.status === 'error').length

  const bits: string[] = []
  if (reads) bits.push(reads === 1 ? '1 file' : `${reads} files`)
  if (searches) bits.push(searches === 1 ? '1 search' : `${searches} searches`)
  if (lists) bits.push(live ? 'Listing notes...' : 'Listed notes')
  if (proposals) {
    bits.push(
      proposals === 1
        ? live
          ? 'Proposing a note...'
          : '1 proposal'
        : live
          ? `${proposals} proposals...`
          : `${proposals} proposals`,
    )
  }
  if (errors) bits.push(`${errors} failed`)
  if (!bits.length) return live ? 'Thinking...' : 'Thought'
  if (reads || searches) return (live ? 'Exploring ' : 'Explored ') + bits.join(', ')
  return bits.join(', ')
}

/** 轨迹标题：优先显示"正在做什么"，没有在跑的就汇总。 */
export function liveTraceLabel(steps: ToolStepState[]): string {
  const running = [...steps].reverse().find((step) => !step.status)
  if (running) return toolLiveLabel(running)
  if (hasRealTools(steps)) return englishSummary(steps, true)
  if (steps.some((step) => step.name === '_gen')) return 'Generating...'
  return 'Thinking...'
}
