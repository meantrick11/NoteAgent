/**
 * 模型配置、revision、维护窗口与向量重建任务的唯一来源。
 *
 * 模型与检索各自持有 revision：模型行使用行级 revision，embedding 使用
 * embedding_revision。写操作不允许把两者混用。
 */

import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

import type {
  ActiveEmbedding,
  EmbeddingCandidate,
  EmbeddingJob,
  ModelConfig,
  ModelConfigInput,
  ProviderSpec,
  RetrievalState,
} from '@/shared/api/types'
import * as api from './api'

export const STATUS_MAX_AGE_MS = 5000
export const POLL_INTERVAL_MS = 1000
const FRESH_ENOUGH_MS = 1000

export interface Notice {
  kind: 'ok' | 'error'
  text: string
}

export const STAGE_TEXT: Record<string, string> = {
  queued: '排队中',
  loading: '加载模型',
  indexing: '建立索引',
  verifying: '校验索引',
  publishing: '发布切换',
  done: '完成',
}

const AVAILABILITY_TEXT: Record<string, string> = {
  available: '可用',
  incomplete: '缓存不完整',
  unsupported: '不支持',
}

export function availabilityLabel(value: string): string {
  return AVAILABILITY_TEXT[value] ?? '不可用'
}

export const useModelsStore = defineStore('models', () => {
  const models = shallowRef<ModelConfig[]>([])
  const activeModel = shallowRef<ModelConfig | null>(null)
  const providerSpecs = shallowRef<ProviderSpec[]>([])
  const embeddingRevision = ref(0)
  const activeEmbedding = shallowRef<ActiveEmbedding | null>(null)
  const embeddingCandidates = shallowRef<EmbeddingCandidate[]>([])
  const retrievalAvailable = ref(true)
  const retrievalProblem = ref<string | null>(null)
  const retrievalState = ref<RetrievalState>('ok')
  const indexedFiles = ref(0)
  const corpusFiles = ref(0)
  const busy = ref(false)
  const embeddingJob = shallowRef<EmbeddingJob | null>(null)

  const streaming = ref(false)
  const formBusy = ref(false)
  const chatNotice = shallowRef<Notice | null>(null)
  const embeddingNotice = shallowRef<Notice | null>(null)

  let loadedAt = 0
  let inFlight: Promise<void> | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let listenersBound = false

  const jobRunning = computed(() => embeddingJob.value?.status === 'running')
  const canSend = computed(() => !busy.value)
  const activeTextCapability = computed(
    () => activeModel.value?.capabilities?.find(item => item.capability === 'text') ?? null,
  )
  const activeTextDisabled = computed(
    () => activeTextCapability.value?.status === 'disabled',
  )
  const canChat = computed(
    () => canSend.value && Boolean(activeModel.value) && !activeTextDisabled.value,
  )
  const modelActionsLocked = computed(() => streaming.value || jobRunning.value)
  const activeEmbeddingId = computed(
    () => activeEmbedding.value?.model_id ?? '原模型',
  )

  function setChatNotice(notice: Notice | null): void {
    chatNotice.value = notice
  }

  function setEmbeddingNotice(notice: Notice | null): void {
    embeddingNotice.value = notice
  }

  function showChatOk(text: string): void {
    setChatNotice(text ? { kind: 'ok', text } : null)
  }

  function showChatError(text: string): void {
    setChatNotice(text ? { kind: 'error', text } : null)
  }

  function showEmbeddingOk(text: string): void {
    setEmbeddingNotice(text ? { kind: 'ok', text } : null)
  }

  function showEmbeddingError(text: string): void {
    setEmbeddingNotice(text ? { kind: 'error', text } : null)
  }

  function stopPolling(): void {
    if (pollTimer === null) return
    clearInterval(pollTimer)
    pollTimer = null
  }

  function startPolling(): void {
    if (pollTimer !== null) return
    pollTimer = setInterval(() => {
      void pollJob()
    }, POLL_INTERVAL_MS)
  }

  function applyStatus(json: Awaited<ReturnType<typeof api.fetchModelSettings>>): void {
    models.value = json.models ?? []
    activeModel.value = json.active_model ?? null
    embeddingRevision.value = json.embedding_revision ?? 0
    activeEmbedding.value = json.active_embedding ?? null
    retrievalAvailable.value = json.retrieval_available !== false
    retrievalProblem.value = json.retrieval_problem ?? null
    retrievalState.value = json.retrieval_state ?? 'ok'
    indexedFiles.value = json.indexed_files ?? 0
    corpusFiles.value = json.corpus_files ?? 0
    busy.value = json.busy === true
    embeddingJob.value = json.embedding_job ?? null
    loadedAt = Date.now()
    if (jobRunning.value) startPolling()
    else stopPolling()
  }

  async function fetchStatus(force = false): Promise<void> {
    if (!force && Date.now() - loadedAt < FRESH_ENOUGH_MS) return
    if (inFlight) return inFlight
    inFlight = (async () => {
      try {
        applyStatus(await api.fetchModelSettings())
      } catch {
        // 保持上一次已知状态；具体操作会反馈错误。
      } finally {
        inFlight = null
      }
    })()
    return inFlight
  }

  async function refreshIfStale(): Promise<void> {
    if (Date.now() - loadedAt > STATUS_MAX_AGE_MS) await fetchStatus(true)
  }

  async function pollJob(): Promise<void> {
    if (typeof document !== 'undefined' && document.hidden) {
      stopPolling()
      return
    }
    const job = embeddingJob.value
    if (!job) {
      stopPolling()
      return
    }
    try {
      embeddingJob.value = await api.fetchEmbeddingJob(job.id)
    } catch {
      return
    }
    if (jobRunning.value) return
    stopPolling()
    await fetchStatus(true)
    await loadCandidates()
  }

  async function loadProviders(): Promise<void> {
    try {
      providerSpecs.value = await api.listProviders()
    } catch {
      // 保留上一次列表；表单会提示加载失败。
    }
  }

  function providerSpec(providerId: string): ProviderSpec | undefined {
    return providerSpecs.value.find(item => item.id === providerId)
  }

  async function testConnection(id: string, body?: ModelConfigInput): Promise<void> {
    formBusy.value = true
    showChatError('')
    showChatOk('')
    try {
      const result = await api.testModel(id, body)
      const parts = [
        result.streaming ? '流式输出正常' : '流式输出不可用',
        result.tool_calling ? '工具调用正常' : '不支持工具调用',
      ]
      if (result.message) parts.push(result.message)
      if (result.verified) showChatOk(`连接测试通过：${parts.join('；')}`)
      else showChatError(`连接测试未通过：${parts.join('；')}`)
    } catch (error) {
      showChatError((error as Error).message)
    } finally {
      formBusy.value = false
    }
  }

  /** 保存配置；activate=true 时在保存后走测试与发布流程。 */
  async function submitModel(
    body: ModelConfigInput,
    editing: ModelConfig | null,
    activate: boolean,
  ): Promise<boolean> {
    formBusy.value = true
    showChatError('')
    showChatOk('')
    try {
      let saved: ModelConfig
      if (editing) {
        if (activate) {
          saved = await api.activateModel(editing.id, {
            expected_revision: editing.revision,
            config: body,
          })
        } else {
          saved = await api.updateModel(editing.id, {
            ...body,
            expected_revision: editing.revision,
          })
        }
      } else {
        saved = await api.createModel(body)
        if (activate) {
          saved = await api.activateModel(saved.id, {
            expected_revision: saved.revision,
          })
        }
      }
      showChatOk(
        activate
          ? `已启用「${saved.label}」，下一个问题就会用 ${saved.model}。`
          : `已保存「${saved.label}」（未启用）。`,
      )
      await fetchStatus(true)
      return true
    } catch (error) {
      showChatError((error as Error).message)
      await fetchStatus(true)
      return false
    } finally {
      formBusy.value = false
    }
  }

  async function activateExisting(model: ModelConfig): Promise<boolean> {
    showChatError('')
    showChatOk('')
    try {
      const saved = await api.activateModel(model.id, {
        expected_revision: model.revision,
      })
      showChatOk(`已启用「${saved.label}」。`)
      await fetchStatus(true)
      return true
    } catch (error) {
      showChatError((error as Error).message)
      await fetchStatus(true)
      return false
    }
  }

  async function removeModel(model: ModelConfig): Promise<boolean> {
    showChatError('')
    showChatOk('')
    try {
      await api.deleteModel(model.id, model.revision)
      await fetchStatus(true)
      showChatOk(`已删除「${model.label}」。`)
      return true
    } catch (error) {
      showChatError((error as Error).message)
      await fetchStatus(true)
      return false
    }
  }

  /** 点击能力徽章：已验证则停用，否则重新探测。 */
  async function changeCapability(
    model: ModelConfig,
    capability: 'text' | 'vision',
  ): Promise<void> {
    const record = model.capabilities.find(item => item.capability === capability)
    const verified = record?.verification === 'verified' && record?.status === 'enabled'
    try {
      if (verified) {
        await api.disableCapability(model.id, capability, model.revision)
      } else {
        await api.verifyCapability(model.id, capability, model.revision)
      }
    } finally {
      await fetchStatus(true)
    }
  }

  async function loadCandidates(): Promise<void> {
    try {
      embeddingCandidates.value = await api.listEmbeddingCandidates()
    } catch {
      // 保持上一次列表；状态区会显示维护提示。
    }
  }

  async function switchEmbedding(modelId: string): Promise<void> {
    showEmbeddingError('')
    showEmbeddingOk('')
    try {
      const result = await api.switchEmbedding(modelId, embeddingRevision.value)
      if (result.unchanged) {
        showEmbeddingOk('当前已经在使用这个向量模型，索引也在。')
        await fetchStatus(true)
        return
      }
      embeddingJob.value = result.job
      busy.value = true
      if (jobRunning.value) startPolling()
    } catch (error) {
      showEmbeddingError((error as Error).message)
      await fetchStatus(true)
    }
  }

  const retrievalStatus = computed<Notice | null>(() => {
    if (jobRunning.value) return null
    switch (retrievalState.value) {
      case 'missing':
        return { kind: 'error', text: retrievalProblem.value ?? '索引 collection 不存在，需要重建。' }
      case 'config_mismatch':
        return { kind: 'error', text: retrievalProblem.value ?? '索引配置已变化，需要重建。' }
      case 'unavailable':
        return { kind: 'error', text: retrievalProblem.value ?? '向量索引当前不可用。' }
      case 'empty':
        if (corpusFiles.value > 0) {
          return {
            kind: 'ok',
            text: `索引里还没有任何片段，但笔记目录有 ${corpusFiles.value} 篇：可能需要重建。`,
          }
        }
        return { kind: 'ok', text: '笔记目录为空，索引为空（状态正常）。' }
      default:
        return {
          kind: 'ok',
          text: `已索引 ${indexedFiles.value} 个片段，覆盖 ${corpusFiles.value} 篇笔记。`,
        }
    }
  })

  function setStreaming(value: boolean): void {
    streaming.value = Boolean(value)
  }

  function onVisibilityChange(): void {
    if (document.hidden) stopPolling()
    else void fetchStatus(true)
  }

  function onWindowFocus(): void {
    void fetchStatus(true)
  }

  function init(): void {
    if (!listenersBound && typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange)
      window.addEventListener('focus', onWindowFocus)
      listenersBound = true
    }
    void fetchStatus(true)
    void loadProviders()
  }

  function dispose(): void {
    stopPolling()
    if (listenersBound && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('focus', onWindowFocus)
      listenersBound = false
    }
  }

  return {
    models,
    activeModel,
    providerSpecs,
    embeddingRevision,
    activeEmbedding,
    embeddingCandidates,
    retrievalAvailable,
    retrievalProblem,
    retrievalState,
    indexedFiles,
    corpusFiles,
    busy,
    embeddingJob,
    streaming,
    formBusy,
    chatNotice,
    embeddingNotice,
    jobRunning,
    canSend,
    canChat,
    activeTextDisabled,
    modelActionsLocked,
    activeEmbeddingId,
    retrievalStatus,
    showChatOk,
    showChatError,
    showEmbeddingOk,
    showEmbeddingError,
    fetchStatus,
    refreshIfStale,
    pollJob,
    loadProviders,
    providerSpec,
    testConnection,
    submitModel,
    activateExisting,
    removeModel,
    changeCapability,
    loadCandidates,
    switchEmbedding,
    setStreaming,
    init,
    dispose,
  }
})
