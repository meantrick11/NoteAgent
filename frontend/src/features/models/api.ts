import { jsonRequest, requestJson } from '@/shared/api/http'
import type {
  ChatActivateIn,
  ChatProfile,
  ChatProfileWriteIn,
  ChatTestResult,
  EmbeddingCandidate,
  EmbeddingJob,
  EmbeddingSwitchResult,
  ModelSettingsStatus,
} from '@/shared/api/types'

/** 除 GET 状态外的端点都相对这个前缀。 */
const BASE = '/model-settings'

/** GET /model-settings —— 两个选择器与任务进度所需的全部状态。 */
export function fetchModelSettings(): Promise<ModelSettingsStatus> {
  return requestJson<ModelSettingsStatus>(BASE)
}

/** POST /model-settings/chat/test —— 只探测，不保存也不切换。 */
export function testChatProfile(profile: ChatProfileWriteIn | Record<string, unknown>) {
  return jsonRequest<ChatTestResult>(`${BASE}/chat/test`, 'POST', profile)
}

/** POST /model-settings/chat/profiles —— 新增配置，保存不启用。 */
export function createChatProfile(body: ChatProfileWriteIn): Promise<ChatProfile> {
  return jsonRequest<ChatProfile>(`${BASE}/chat/profiles`, 'POST', body)
}

/** PUT /model-settings/chat/profiles/{id} —— 编辑；当前启用的那条必须走 activate。 */
export function updateChatProfile(
  id: string,
  body: ChatProfileWriteIn,
): Promise<ChatProfile> {
  return jsonRequest<ChatProfile>(
    `${BASE}/chat/profiles/${encodeURIComponent(id)}`,
    'PUT',
    body,
  )
}

/** DELETE /model-settings/chat/profiles/{id} —— 204；revision 走查询参数。 */
export function deleteChatProfile(id: string, expectedRevision: number): Promise<null> {
  const query = `?expected_revision=${encodeURIComponent(String(expectedRevision))}`
  return requestJson<null>(`${BASE}/chat/profiles/${encodeURIComponent(id)}${query}`, {
    method: 'DELETE',
  })
}

/** POST /model-settings/chat/activate —— 校验、保存、启用一步完成。 */
export function activateChatProfile(body: ChatActivateIn): Promise<ChatProfile> {
  return jsonRequest<ChatProfile>(`${BASE}/chat/activate`, 'POST', body)
}

/** GET /model-settings/embeddings —— 本地缓存的候选模型与真实可用性。 */
export function listEmbeddingCandidates(): Promise<EmbeddingCandidate[]> {
  return requestJson<EmbeddingCandidate[]>(`${BASE}/embeddings`)
}

/** POST /model-settings/embedding/switch —— 202 表示已开始重建，不是已切换。 */
export function switchEmbedding(
  modelId: string,
  expectedRevision: number,
): Promise<EmbeddingSwitchResult> {
  return jsonRequest<EmbeddingSwitchResult>(`${BASE}/embedding/switch`, 'POST', {
    model_id: modelId,
    expected_revision: expectedRevision,
  })
}

/** GET /model-settings/jobs/{id} —— 重建进度，重启后也能恢复。 */
export function fetchEmbeddingJob(jobId: string): Promise<EmbeddingJob> {
  return requestJson<EmbeddingJob>(`${BASE}/jobs/${encodeURIComponent(jobId)}`)
}
