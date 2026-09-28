/**
 * 模型配置、revision、维护窗口与向量重建任务的唯一来源。
 *
 * Settings 页面与 Assistant 的模型快捷弹层共用这一个 store，所以：
 *   - 轮询只有一份，由 init() 统一注册 visibilitychange／focus，dispose() 统一清理；
 *   - 「维护窗口」是全局状态，聊天发送与笔记写入都读同一个 canSend；
 *   - 保存／启用／删除都必须带 expected_revision，409 时刷新状态让用户重试。
 */

import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

import type {
  ActiveEmbedding,
  ChatProfile,
  ChatProfileInput,
  EmbeddingCandidate,
  EmbeddingJob,
  RetrievalState,
} from '@/shared/api/types'
import * as api from './api'

/** 状态超过这个年龄就必须在写操作前重新拉一次。 */
export const STATUS_MAX_AGE_MS = 5000
/** 重建任务进行中的轮询间隔。 */
export const POLL_INTERVAL_MS = 1000
/** 同一个标签页里 1 秒内重复读状态直接复用上一次结果。 */
const FRESH_ENOUGH_MS = 1000

/** 弹层里的成功／失败提示；聊天与向量各有自己的槽位，不能互相串。 */
export interface Notice {
  kind: 'ok' | 'error'
  text: string
}

/** 重建阶段的中文名。未知阶段直接显示原值，不猜。 */
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
  const revision = ref(0)
  const chatProfiles = shallowRef<ChatProfile[]>([])
  const activeChat = shallowRef<ChatProfile | null>(null)
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

  // 下面这些不参与渲染，放在闭包里避免进入响应式系统。
  let loadedAt = 0
  let inFlight: Promise<void> | null = null
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let listenersBound = false

  const jobRunning = computed(() => embeddingJob.value?.status === 'running')
  /** 维护窗口：busy 期间不能发送消息、不能写笔记。 */
  const canSend = computed(() => !busy.value)
  /** 配置类操作在流式输出或重建期间都要禁用。 */
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

  /** 只写一个方向：成功提示出现时清掉错误，反之亦然。 */
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
    revision.value = json.revision
    chatProfiles.value = json.chat_profiles ?? []
    activeChat.value = json.active_chat ?? null
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
    // 未过期就不重复读；已有请求在飞就复用它，避免并发状态互相覆盖。
    if (!force && Date.now() - loadedAt < FRESH_ENOUGH_MS) return
    if (inFlight) return inFlight
    inFlight = (async () => {
      try {
        applyStatus(await api.fetchModelSettings())
      } catch {
        // 状态读不到不影响聊天本身：保持上一次已知状态，错误由具体操作反馈。
      } finally {
        inFlight = null
      }
    })()
    return inFlight
  }

  /** 发送消息或写笔记前调用：过期就强制刷新一次。 */
  async function refreshIfStale(): Promise<void> {
    if (Date.now() - loadedAt > STATUS_MAX_AGE_MS) await fetchStatus(true)
  }

  async function pollJob(): Promise<void> {
    // 页面不可见时停掉高频轮询，回到前台由 visibilitychange 再刷新。
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
      // 单次轮询失败先不动状态，下个周期再试。
      return
    }
    if (jobRunning.value) return
    stopPolling()
    await fetchStatus(true)
    await loadCandidates()
  }

  /** 写操作前统一刷新并取当前 revision，避免用到过期值。 */
  async function currentRevision(): Promise<number> {
    await refreshIfStale()
    return revision.value
  }

  async function testConnection(profile: ChatProfileInput): Promise<void> {
    formBusy.value = true
    showChatError('')
    showChatOk('')
    try {
      const result = await api.testChatProfile({ ...profile })
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

  /** 保存配置。activate=true 走「保存并启用」，否则只落盘不切换。 */
  async function submitProfile(
    profile: ChatProfileInput,
    editingId: string | null,
    activate: boolean,
  ): Promise<boolean> {
    formBusy.value = true
    showChatError('')
    showChatOk('')
    try {
      const expected = await currentRevision()
      if (activate) {
        const saved = await api.activateChatProfile({
          expected_revision: expected,
          profile,
        })
        showChatOk(`已启用「${saved.label}」，下一个问题就会用 ${saved.model}。`)
      } else if (editingId) {
        const saved = await api.updateChatProfile(editingId, {
          ...profile,
          id: editingId,
          expected_revision: expected,
        })
        showChatOk(`已保存「${saved.label}」（未启用）。`)
      } else {
        const saved = await api.createChatProfile({ ...profile, expected_revision: expected })
        showChatOk(`已保存「${saved.label}」（未启用）。`)
      }
      await fetchStatus(true)
      return true
    } catch (error) {
      // 409 说明别的标签页改过配置：刷新后让用户重试，表单内容不丢。
      showChatError((error as Error).message)
      await fetchStatus(true)
      return false
    } finally {
      formBusy.value = false
    }
  }

  async function activateProfile(profileId: string): Promise<boolean> {
    showChatError('')
    showChatOk('')
    try {
      const saved = await api.activateChatProfile({
        expected_revision: await currentRevision(),
        profile_id: profileId,
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

  async function deleteProfile(profile: ChatProfile): Promise<boolean> {
    showChatError('')
    showChatOk('')
    try {
      await api.deleteChatProfile(profile.id, await currentRevision())
      await fetchStatus(true)
      showChatOk(`已删除「${profile.label}」。`)
      return true
    } catch (error) {
      showChatError((error as Error).message)
      await fetchStatus(true)
      return false
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
    // 向量相关的成败只写向量弹层，不串到聊天弹层。
    showEmbeddingError('')
    showEmbeddingOk('')
    try {
      const result = await api.switchEmbedding(modelId, await currentRevision())
      if (result.unchanged) {
        showEmbeddingOk('当前已经在使用这个向量模型，索引也在。')
        await fetchStatus(true)
        return
      }
      embeddingJob.value = result.job
      // 202 即已进入维护窗口：立刻反映到按钮状态，不等下一次整轮刷新。
      busy.value = true
      if (jobRunning.value) startPolling()
    } catch (error) {
      showEmbeddingError((error as Error).message)
      await fetchStatus(true)
    }
  }

  /** 索引状态文案：丢失、指纹不符、空索引与已就绪各自可辨。 */
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

  /** 本轮生成期间禁用模型入口；不打断已经开始的这一轮。 */
  function setStreaming(value: boolean): void {
    streaming.value = Boolean(value)
  }

  function onVisibilityChange(): void {
    if (document.hidden) stopPolling()
    else void fetchStatus(true)
  }

  function onWindowFocus(): void {
    // 另一个标签页可能刚切换过模型，回到本页时刷新一次。
    void fetchStatus(true)
  }

  /** 应用启动时调用一次：绑定跨标签与可见性监听，并读一次状态。 */
  function init(): void {
    if (!listenersBound && typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisibilityChange)
      window.addEventListener('focus', onWindowFocus)
      listenersBound = true
    }
    void fetchStatus(true)
  }

  /** 应用卸载时调用：移除监听并停止轮询，避免留下游离的定时器。 */
  function dispose(): void {
    stopPolling()
    if (listenersBound && typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('focus', onWindowFocus)
      listenersBound = false
    }
  }

  return {
    revision,
    chatProfiles,
    activeChat,
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
    testConnection,
    submitProfile,
    activateProfile,
    deleteProfile,
    loadCandidates,
    switchEmbedding,
    setStreaming,
    init,
    dispose,
  }
})
