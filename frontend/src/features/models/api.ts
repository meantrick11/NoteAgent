import { jsonRequest, requestJson } from '@/shared/api/http'
import type {
  EmbeddingCandidate,
  EmbeddingJob,
  EmbeddingSwitchResult,
  ModelActivateIn,
  ModelConfig,
  ModelConfigInput,
  ModelConfigWriteIn,
  ModelSettingsStatus,
  ModelTestResult,
  ProviderSpec,
} from '@/shared/api/types'

/** 除 GET 状态外的端点都相对这个前缀。 */
const BASE = '/model-settings'

/** GET /model-settings —— 模型列表、active 与独立的检索状态。 */
export function fetchModelSettings(): Promise<ModelSettingsStatus> {
  return requestJson<ModelSettingsStatus>(BASE)
}

/** GET /model-settings/providers —— 表单的 Provider 规格。 */
export function listProviders(): Promise<ProviderSpec[]> {
  return requestJson<ProviderSpec[]>(`${BASE}/providers`)
}

/** POST /model-settings/models —— 新增配置，保存不启用。 */
export function createModel(body: ModelConfigInput): Promise<ModelConfig> {
  return jsonRequest<ModelConfig>(`${BASE}/models`, 'POST', body)
}

/** PUT /model-settings/models/{id} —— 编辑非 active 配置。 */
export function updateModel(id: string, body: ModelConfigWriteIn): Promise<ModelConfig> {
  return jsonRequest<ModelConfig>(
    `${BASE}/models/${encodeURIComponent(id)}`,
    'PUT',
    body,
  )
}

/** DELETE /model-settings/models/{id} —— 204；revision 走查询参数。 */
export function deleteModel(id: string, expectedRevision: number): Promise<null> {
  const query = `?expected_revision=${encodeURIComponent(String(expectedRevision))}`
  return requestJson<null>(`${BASE}/models/${encodeURIComponent(id)}${query}`, {
    method: 'DELETE',
  })
}

/** POST /model-settings/models/{id}/test —— 只探测，不保存也不切换。 */
export function testModel(
  id: string,
  body?: ModelConfigInput,
): Promise<ModelTestResult> {
  return jsonRequest<ModelTestResult>(
    `${BASE}/models/${encodeURIComponent(id)}/test`,
    'POST',
    body ?? null,
  )
}

/** POST /model-settings/models/{id}/activate —— 校验、可选保存、启用并发布快照。 */
export function activateModel(id: string, body: ModelActivateIn): Promise<ModelConfig> {
  return jsonRequest<ModelConfig>(
    `${BASE}/models/${encodeURIComponent(id)}/activate`,
    'POST',
    body,
  )
}

export function verifyCapability(
  id: string,
  capability: 'text' | 'vision',
  expectedRevision: number,
): Promise<ModelConfig> {
  return jsonRequest<ModelConfig>(
    `${BASE}/models/${encodeURIComponent(id)}/capabilities/${capability}/verify`,
    'POST',
    { expected_revision: expectedRevision },
  )
}

export function disableCapability(
  id: string,
  capability: 'text' | 'vision',
  expectedRevision: number,
): Promise<ModelConfig> {
  return requestJson<ModelConfig>(
    `${BASE}/models/${encodeURIComponent(id)}/capabilities/${capability}?expected_revision=${encodeURIComponent(String(expectedRevision))}`,
    { method: 'DELETE' },
  )
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
