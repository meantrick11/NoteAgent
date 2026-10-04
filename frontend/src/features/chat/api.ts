import { jsonRequest, requestJson } from '@/shared/api/http'
import type {
  Conversation,
  ConversationDetail,
  Message,
  PendingDraft,
  ReviewRequest,
  ReviewResult,
} from '@/shared/api/types'

/** GET /conversations —— 侧栏会话列表。 */
export function listConversations(): Promise<Conversation[]> {
  return requestJson<Conversation[]>('/conversations')
}

/** GET /conversations/{id} —— 详情，含服务端待审草稿。 */
export function getConversation(id: string): Promise<ConversationDetail> {
  return requestJson<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`)
}

/** GET /conversations/{id}/messages —— 历史消息（含 citations 与 tool_steps）。 */
export function listMessages(id: string): Promise<Message[]> {
  return requestJson<Message[]>(`/conversations/${encodeURIComponent(id)}/messages`)
}

/** PATCH /conversations/{id} —— 重命名，服务端会 trim 并校验长度。 */
export function renameConversation(id: string, title: string): Promise<Conversation> {
  return jsonRequest<Conversation>(`/conversations/${encodeURIComponent(id)}`, 'PATCH', {
    title,
  })
}

/** DELETE /conversations/{id} —— 204，无响应体。 */
export async function deleteConversation(id: string): Promise<void> {
  await requestJson<null>(`/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

/** PUT /chat/draft —— 只改待审草稿正文，不写正式笔记。 */
export function saveDraftContent(
  threadId: string,
  content: string,
): Promise<{ status: string; pending_draft: PendingDraft }> {
  return jsonRequest('/chat/draft', 'PUT', { thread_id: threadId, content })
}

/** POST /chat/review —— 审批草稿。业务失败也是 200，必须看返回体的 status／error。 */
export function reviewDraft(body: ReviewRequest): Promise<ReviewResult> {
  return jsonRequest<ReviewResult>('/chat/review', 'POST', body)
}

/** POST /chat —— 返回原始响应，由调用方读取 SSE 流。 */
export async function openChatStream(
  question: string,
  conversationId: string | null,
  requestId?: string,
) {
  const response = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      request_id: requestId,
    }),
  })
  return response
}
