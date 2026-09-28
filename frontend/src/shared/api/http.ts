/**
 * 唯一的 HTTP 入口：负责 JSON 解析、空响应体、网络错误与错误文案提取。
 * 写请求一律不自动重试——重试一次草稿保存或模型切换都可能造成用户没预期的副作用。
 */

/** 后端错误统一成这个类型，UI 只读 status 与 message。 */
export class ApiError extends Error {
  /** status 为 0 表示请求根本没拿到响应（断网、被中断）。 */
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/**
 * 沿用旧页面的文案优先级：模型管理的 message → FastAPI 的 detail → 审批结果的 error
 * → 兜底 HTTP 状态码。顺序变了会让错误提示倒退成 "HTTP 500"。
 */
export function extractErrorMessage(payload: unknown, status: number): string {
  if (payload && typeof payload === 'object') {
    const body = payload as Record<string, unknown>
    for (const key of ['message', 'detail', 'error'] as const) {
      const value = body[key]
      if (typeof value === 'string' && value) return value
    }
  }
  return `HTTP ${status}`
}

/** 读取响应体；空体或非 JSON 都返回 null，不抛异常。 */
export async function readJsonBody(response: Response): Promise<unknown> {
  const text = await response.text()
  if (!text.trim()) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

async function send(path: string, init: RequestInit): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(path, init)
  } catch (error) {
    throw new ApiError(0, `网络请求失败：${(error as Error).message}`)
  }
  const payload = await readJsonBody(response)
  if (!response.ok) {
    throw new ApiError(response.status, extractErrorMessage(payload, response.status))
  }
  return payload
}

export function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  return send(path, init) as Promise<T>
}

/** 带 JSON body 的写请求；method 必填，避免默认成 GET 后 body 被静默忽略。 */
export function jsonRequest<T>(path: string, method: string, body: unknown): Promise<T> {
  return requestJson<T>(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}
