/**
 * /chat 的 SSE 协议：解析、事件解码与一轮对话的状态累积。
 *
 * 三层分开是为了让每一层都能单独验证：
 *   consumeSse      只认字节流 → {event, data}，负责分片与心跳
 *   decodeChatEvent 只认 {event, data} → 带类型的 ChatStreamEvent，负责协议校验
 *   TurnAccumulator 只认 ChatStreamEvent → 本轮正文、引用与工具步骤
 *
 * 协议事实（来自 chat/router.py 与 chat/agent.py）：`answer` 是服务端清理后的完整正文，
 * 必须整体替换而不是追加；`sources` 可能早于或晚于 `answer` 到达，所以引用单独存，
 * 不挂在正文缓冲上。
 */

import type { Citation, PendingDraft } from '@/shared/api/types'

export interface RawSseEvent {
  event: string
  data: unknown
}

/** 服务端没有给事件名时的默认值，与旧实现一致。 */
const DEFAULT_EVENT = 'token'

/** 把 data 行还原成对象或字符串：不是 JSON 就当纯文本，与旧实现一致。 */
function parseData(raw: string): unknown {
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

/**
 * 解析 SSE 流并逐个派发事件。
 *
 * 不假设一次 read 就是一个完整事件：按 `\n` 切行、保留最后一段不完整行，
 * 因此 UTF-8 字符跨块、一个事件跨多次 read、一次 read 含多个事件都能正确还原。
 * 空行把事件名复位成 token；注释心跳（以 `:` 开头）忽略；流结束后再冲一次解码器，
 * 处理末行没有换行结尾的情况。
 */
export async function consumeSse(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: RawSseEvent) => void,
): Promise<void> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let event = DEFAULT_EVENT

  const handleLine = (line: string): void => {
    if (line.trim() === '') {
      event = DEFAULT_EVENT
      return
    }
    if (line.startsWith('event: ')) {
      event = line.slice(7).trim() || DEFAULT_EVENT
      return
    }
    if (line.startsWith('data: ')) {
      onEvent({ event, data: parseData(line.slice(6)) })
      return
    }
    // 其余（注释心跳、id/retry 等未使用字段）按协议忽略。
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) handleLine(line)
    }
  } finally {
    reader.releaseLock()
  }

  buffer += decoder.decode()
  if (buffer.trim() !== '') handleLine(buffer)
}

export type ChatStreamEvent =
  | { type: 'conversation'; id: string; title: string }
  | { type: 'thinking' }
  | { type: 'generating' }
  | { type: 'think'; text: string }
  | { type: 'tool'; name: string; args: unknown }
  | { type: 'tool_done'; name: string; status: string; preview: string; arguments: string }
  | { type: 'draft'; draft: PendingDraft }
  | { type: 'sources'; citations: Citation[] }
  | { type: 'answer'; text: string }
  | { type: 'token'; text: string }
  | { type: 'unknown'; event: string }

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

/**
 * 把一个原始事件解码成带类型的领域事件。
 * 协议判断集中在这里，组件与 store 都不再自己分辨事件名。
 */
export function decodeChatEvent(raw: RawSseEvent): ChatStreamEvent {
  const { event, data } = raw
  switch (event) {
    case 'conversation':
      if (isRecord(data) && typeof data.id === 'string') {
        return { type: 'conversation', id: data.id, title: asString(data.title) }
      }
      return { type: 'unknown', event }
    case 'thinking':
      return { type: 'thinking' }
    case 'generating':
      return { type: 'generating' }
    case 'think':
      return { type: 'think', text: asString(data) }
    case 'tool': {
      const record = isRecord(data) ? data : {}
      return { type: 'tool', name: asString(record.name), args: record.args ?? {} }
    }
    case 'tool_done': {
      const record = isRecord(data) ? data : {}
      return {
        type: 'tool_done',
        name: asString(record.name),
        status: asString(record.status) || 'ok',
        preview: asString(record.preview),
        arguments: asString(record.arguments),
      }
    }
    case 'draft':
      if (isRecord(data)) return { type: 'draft', draft: data as unknown as PendingDraft }
      return { type: 'unknown', event }
    case 'sources':
      return { type: 'sources', citations: Array.isArray(data) ? (data as Citation[]) : [] }
    case 'answer':
      return typeof data === 'string'
        ? { type: 'answer', text: data }
        : { type: 'unknown', event }
    case 'token':
      return typeof data === 'string'
        ? { type: 'token', text: data }
        : { type: 'unknown', event }
    default:
      return { type: 'unknown', event }
  }
}

/** 一轮对话里一个工具／思考步骤的状态。`_think` 与 `_gen` 是内部伪步骤。 */
export interface ToolStepState {
  name: string
  status: string
  preview: string
  arguments: string
  content: string
}

/** 思考内容的上限，避免长思考把 DOM 撑爆。 */
const THINK_CONTENT_LIMIT = 4000

function blankStep(name: string): ToolStepState {
  return { name, status: '', preview: '', arguments: '', content: '' }
}

/**
 * 累积一轮对话的状态：正文缓冲、引用与工具步骤。
 *
 * 与旧 ask() 里的内联状态一一对应，抽出来是为了能在没有 DOM 的情况下验证
 * 「answer 整体替换 token 缓冲」「sources 先后顺序都不丢引用」这两条约束。
 */
export class TurnAccumulator {
  /** token 累积的正文；收到 answer 时被整体替换。 */
  private text = ''
  citations: Citation[] = []
  steps: ToolStepState[] = []

  get rawText(): string {
    return this.text
  }

  /** 把尚未结束的伪步骤收尾，避免同时挂着两个进行中的阶段。 */
  private completeOpenPhase(name: string): void {
    const open = this.steps.find((step) => step.name === name && !step.status)
    if (open) open.status = 'ok'
  }

  /** 收掉思考阶段，并保证有一个进行中的生成步骤。 */
  private ensureGenerating(): void {
    this.completeOpenPhase('_think')
    if (!this.steps.some((step) => step.name === '_gen' && !step.status)) {
      this.steps.push(blankStep('_gen'))
    }
  }

  apply(event: ChatStreamEvent): void {
    switch (event.type) {
      case 'thinking':
        this.completeOpenPhase('_think')
        this.completeOpenPhase('_gen')
        this.steps.push(blankStep('_think'))
        break
      case 'generating':
        this.ensureGenerating()
        break
      case 'think': {
        if (!event.text) break
        let think = [...this.steps].reverse().find((step) => step.name === '_think')
        if (!think) {
          think = blankStep('_think')
          this.steps.push(think)
        }
        think.content += event.text
        if (think.content.length > THINK_CONTENT_LIMIT) {
          think.content = `${think.content.slice(0, THINK_CONTENT_LIMIT)}…`
        }
        break
      }
      case 'tool': {
        this.completeOpenPhase('_think')
        this.completeOpenPhase('_gen')
        const existing = this.steps.find(
          (step) => step.name === event.name && !step.status,
        )
        if (existing) existing.arguments = JSON.stringify(event.args)
        else {
          const step = blankStep(event.name)
          step.arguments = JSON.stringify(event.args)
          this.steps.push(step)
        }
        break
      }
      case 'tool_done': {
        const step =
          this.steps.find((item) => item.name === event.name && !item.status) ??
          this.steps[this.steps.length - 1]
        if (step) {
          step.status = event.status
          step.preview = event.preview
          step.arguments = event.arguments || step.arguments
        }
        break
      }
      case 'sources':
        this.citations = event.citations
        break
      case 'answer':
        // 服务端已清理过的完整正文，替换而不是追加。
        this.text = event.text
        break
      case 'token':
        this.text += event.text
        this.ensureGenerating()
        break
      default:
        break
    }
  }

  /** 流结束：把所有未结束的步骤标成完成。 */
  finish(): void {
    for (const step of this.steps) {
      if (!step.status) step.status = 'ok'
    }
  }
}
