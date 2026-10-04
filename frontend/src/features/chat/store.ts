/**
 * Assistant 页的状态中枢：会话、消息、发送门闩、以及按会话隔离的右侧面板。
 *
 * 几条不能丢的既有约定：
 *  - 发送门闩在**第一次 await 之前**置位，否则双击的第二次调用会在 refreshIfStale 期间
 *    看到还在 false，从而多发一轮请求、多写一条消息；
 *  - 回包按"发起时的会话"归属，不回包时读当前选中的 id 决定写哪里；
 *  - 每个会话各有一份面板快照（正文、未保存标记、选区、滚动位置），切会话不串内容；
 *  - 草稿只读写 conversations.pending_draft：保存草稿不写笔记，同意才写。
 */

import { computed, reactive, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

import { ApiError, extractErrorMessage, readJsonBody } from '@/shared/api/http'
import { alertDialog, confirmDialog, reportError } from '@/shared/ui/confirm'
import { showSaveToast } from '@/shared/ui/toast'
import type { Citation, Conversation, ConversationDetail, Message, PendingDraft, RecoveryJob, RecoveryPreview } from '@/shared/api/types'
// 引用面板读写的是正式笔记，所以走 notes 的接口而不是 chat 的。
import { readNote, writeNote } from '@/features/notes/api'
import { useNotesStore } from '@/features/notes/store'
import * as api from './api'
import * as recoveryApi from './recovery'
import { locateQuote } from './citations'

import { consumeSse, decodeChatEvent, TurnAccumulator, type ToolStepState } from './sse'
import { liveTraceLabel } from './trace'
import { useModelsStore } from '@/features/models/store'

export type PanelMode = 'citation' | 'draft'

/** 还没拿到服务端 id 的新会话用这个键，拿到后整体迁移到真实 id。 */
export const CITE_PENDING_KEY = '__pending__'

export function citePaneKey(id: string | null | undefined): string {
  return id || CITE_PENDING_KEY
}

export interface PanelSnapshot {
  hidden: boolean
  mode: PanelMode
  fileName: string | null
  draft: PendingDraft | null
  text: string
  textDisabled: boolean
  dirty: boolean
  hintLocate: string
  selStart: number
  selEnd: number
  scrollTop: number
  busy: boolean
  /** Revision of the draft buffer; dirty text retains its original token. */
  draftRevision: number | null
}

export function blankPanel(): PanelSnapshot {
  return {
    hidden: true,
    mode: 'citation',
    fileName: null,
    draft: null,
    text: '',
    textDisabled: true,
    dirty: false,
    hintLocate: '',
    selStart: 0,
    selEnd: 0,
    scrollTop: 0,
    busy: false,
    draftRevision: null,
  }
}

export interface ChatMessage {
  key: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  toolSteps: ToolStepState[]
  live: boolean
  /** 实时轨迹标题（仅助手消息、仅流式期间）。 */
  traceLabel: string
  /** 这一轮归属的会话键；新会话拿到正式 id 后会就地改写。 */
  ownerKey: string
  /** 服务端消息 id；乐观行为 null，收到 user_message 后换成正式 id。 */
  id: string | null
  turnId: string | null
  /** 客户端幂等键，用于把乐观行替换成服务端身份（不按文本或下标匹配）。 */
  requestId: string | null
  /** 可回退编辑能力；阶段 B 未完成前始终为 false。 */
  editable: boolean
  editUnavailableReason: string | null
  selectionAtStart: number
}

let messageSeq = 0

function newMessage(role: 'user' | 'assistant', content: string): ChatMessage {
  messageSeq += 1
  return {
    key: `m-${messageSeq}`,
    role,
    content,
    citations: [],
    toolSteps: [],
    live: false,
    traceLabel: '',
    ownerKey: '',
    id: null,
    turnId: null,
    requestId: null,
    editable: false,
    editUnavailableReason: null,
    selectionAtStart: 0,
  }
}

/** 编辑入口的禁用原因；可编辑时返回 null。 */
export function editUnavailableMessage(message: ChatMessage): string | null {
  if (message.editable) return null
  return message.editUnavailableReason ?? '历史消息暂不支持编辑'
}

/** 一轮请求的幂等键；服务端原样回传，用来替换乐观行的身份。 */
function newRequestId(): string {
  const cryptoObj = globalThis.crypto
  if (cryptoObj && typeof cryptoObj.randomUUID === 'function') return cryptoObj.randomUUID()
  messageSeq += 1
  return `req-${Date.now()}-${messageSeq}`
}

/** 提交审批动作的中文名。 */
const DRAFT_ACTION_LABEL: Record<string, string> = {
  append: '追加',
  replace: '覆盖',
  delete: '删除',
  create: '新建',
}

export function draftApproveLabel(action: string): string {
  if (action === 'append') return '同意追加'
  if (action === 'replace') return '同意覆盖'
  if (action === 'delete') return '同意删除'
  return '同意新建'
}

export function draftPaneTitle(draft: PendingDraft): string {
  return `${DRAFT_ACTION_LABEL[draft.action] ?? '草稿'} · ${draft.file_name}`
}

/** 审批前的一句确认语，沿用改动前草稿卡片的措辞。 */
export function draftAsk(draft: PendingDraft): string {
  const similar = (draft.similar ?? []).filter(Boolean)
  if (draft.action === 'append') {
    const extra = similar.length ? `，相近：${similar.join('、')}` : ''
    return `识别到已经有笔记「${draft.file_name}」${extra}，是否要追加？`
  }
  if (draft.action === 'replace') {
    return `是否用以下内容覆盖「${draft.file_name}」？旧内容将被替换。`
  }
  if (draft.action === 'delete') {
    return `是否删除笔记「${draft.file_name}」？删除后无法从本页恢复。`
  }
  return `没有相关笔记，是否要新建笔记文件（提议文件名：${draft.file_name}）？`
}

/** 覆盖入口只在能换目标时才有意义。 */
export function draftOverrideAvailable(draft: PendingDraft | null): boolean {
  return !!draft && (draft.action === 'append' || draft.action === 'create')
}

export type SendOutcome = 'sent' | 'refused' | 'failed'

export const useChatStore = defineStore('chat', () => {
  const models = useModelsStore()
  const notes = useNotesStore()

  const conversations = shallowRef<Conversation[]>([])
  const currentId = ref<string | null>(null)
  // 深度响应式：进行中的那一轮是**就地更新**（正文、步骤、轨迹标题），
  // shallowRef 不会跟踪嵌套对象上的赋值。
  const messages = ref<ChatMessage[]>([])
  /**
   * 进行中的那一轮。全局最多一个（发送是串行的），所以用单个引用而不是映射：
   * 归属会话写在消息的 ownerKey 上，新会话拿到正式 id 后就地改写，不必搬来搬去。
   */
  const liveTurn = ref<ChatMessage | null>(null)
  const panels = ref<Record<string, PanelSnapshot>>({})
  const streaming = ref(false)
  /**
   * 每次用户主动切换会话（点开某条会话或点「新对话」）都自增。
   * 首屏"自动打开最近一条"在等待列表返回期间，如果用户已经自己选过了，
   * 就靠它判断并放弃自动打开，不抢用户的动作。
   */
  const selectionVersion = ref(0)
  /** 当前会话活动 head 的 revision；草稿保存／审批要原样回传做 stale 校验。 */
  const revisions = ref<Record<string, number>>({})
  const runs = ref<Record<string, ConversationDetail['active_run']>>({})
  const stateRevision = computed(() => revisions.value[citePaneKey(currentId.value)] ?? 0)
  const activeRun = computed(() => runs.value[citePaneKey(currentId.value)] ?? null)

  /** 当前会话的面板；不存在时返回默认值，写操作一律走 patchPanel。 */
  const panel = computed<PanelSnapshot>(
    () => panels.value[citePaneKey(currentId.value)] ?? blankPanel(),
  )

  const visibleMessages = computed<ChatMessage[]>(() => {
    const turn = liveTurn.value
    // 用户切到别的会话时，这一轮不属于当前视图，先不显示；它已经在服务端，重开会拉到。
    if (!turn || turn.ownerKey !== citePaneKey(currentId.value)) return messages.value
    return [...messages.value, turn]
  })

  const hasMessages = computed(() => visibleMessages.value.length > 0)

  /** 面板标题下的提示：未保存与定位失败各自成段。 */
  const panelHint = computed(() => {
    const parts: string[] = []
    if (panel.value.dirty) parts.push('未保存')
    if (panel.value.hintLocate) parts.push(panel.value.hintLocate)
    return parts.join(' · ')
  })

  /** 保存按钮：草稿模式要有非空正文，引用模式要已载入内容。 */
  const panelSaveDisabled = computed(() => {
    const current = panel.value
    if (current.busy) return true
    if (current.mode === 'draft') return current.text.trim().length === 0
    return current.textDisabled
  })

  const panelSaveLabel = computed(() =>
    panel.value.mode === 'draft' ? '保存草稿' : '保存到 Markdown',
  )

  const panelTitle = computed(() => {
    const current = panel.value
    if (current.mode === 'draft' && current.draft) return draftPaneTitle(current.draft)
    return current.fileName ?? ''
  })

  /** 任何会话有未保存的面板编辑都算脏：离开页面与关窗前都要问。 */
  const anyPanelDirty = computed(
    () => panel.value.dirty || Object.values(panels.value).some((item) => item.dirty),
  )

  function patchPanel(key: string, patch: Partial<PanelSnapshot>): void {
    const existing = panels.value[key] ?? blankPanel()
    panels.value = { ...panels.value, [key]: { ...existing, ...patch } }
  }

  function patchActivePanel(patch: Partial<PanelSnapshot>): void {
    patchPanel(citePaneKey(currentId.value), patch)
  }

  function pushNotice(text: string): void {
    messages.value = [...messages.value, newMessage('assistant', text)]
  }

  // ---------- 会话列表 ----------

  async function loadConversations(): Promise<Conversation[]> {
    try {
      const list = await api.listConversations()
      conversations.value = Array.isArray(list) ? list : []
    } catch {
      conversations.value = []
    }
    return conversations.value
  }

  async function openConversation(id: string): Promise<void> {
    if (id === currentId.value) return
    selectionVersion.value += 1
    currentId.value = id
    await loadMessages(id)
    await reloadPanel(id)
  }

  /** 读取并恢复该会话的历史消息；进行中的那一轮若属于它，仍接在后面。 */
  async function loadMessages(id: string): Promise<void> {
    const requested = id
    try {
      const [list, detail] = await Promise.all([
        api.listMessages(requested),
        api.getConversation(requested).catch(() => null),
      ])
      // 慢请求不能覆盖用户后来选中的会话。
      if (currentId.value !== requested) return
      messages.value = (Array.isArray(list) ? list : []).map((item) => fromServerMessage(item))
      if (detail) {
        revisions.value[requested] = detail.state_revision ?? 0
        runs.value[requested] = detail.active_run ?? null
        applyServerDraft(requested, detail.pending_draft, detail.state_revision ?? 0)
      }
    } catch {
      if (currentId.value !== requested) return
      messages.value = []
    }
  }

  function fromServerMessage(item: Message): ChatMessage {
    const message = newMessage(item.role === 'user' ? 'user' : 'assistant', item.content ?? '')
    message.id = item.id
    message.turnId = item.turn_id ?? null
    message.editable = item.editable === true
    message.editUnavailableReason = item.edit_unavailable_reason ?? null
    message.citations = item.citations ?? []
    message.toolSteps = (item.tool_steps ?? []).map((step) => ({
      name: step.name,
      status: step.status,
      preview: step.preview,
      arguments: step.arguments,
      content: '',
    }))
    return message
  }

  function newChat(): void {
    selectionVersion.value += 1
    currentId.value = null
    messages.value = []
    // 保留 __pending__ 的面板：用户可能正在新会话里编辑引用。
    if (!panels.value[CITE_PENDING_KEY]) patchPanel(CITE_PENDING_KEY, blankPanel())
  }

  async function renameConversation(id: string, title: string): Promise<string | null> {
    try {
      const updated = await api.renameConversation(id, title)
      conversations.value = conversations.value.map((item) =>
        item.id === id ? { ...item, title: updated.title } : item,
      )
      return updated.title
    } catch {
      return null
    }
  }

  async function removeConversation(id: string): Promise<boolean> {
    try {
      await api.deleteConversation(id)
    } catch {
      return false
    }
    conversations.value = conversations.value.filter((item) => item.id !== id)
    const { [id]: _removed, ...rest } = panels.value
    panels.value = rest
    if (currentId.value === id) newChat()
    return true
  }

  // ---------- 面板：引用模式 ----------

  /** 服务端草稿进快照；本地未保存的编辑缓冲优先保留。 */
  function applyServerDraft(id: string, draft: PendingDraft | null, revision = revisions.value[id] ?? 0): void {
    const key = citePaneKey(id)
    const existing = panels.value[key]
    if (existing?.mode === 'draft' && existing.dirty) {
      if (existing.draftRevision !== revision) {
        patchPanel(key, { hintLocate: '草稿已在其他页面更新，本地编辑已保留；请重新核对后再保存。' })
      }
      return
    }
    if (!draft) {
      if (existing?.mode === 'draft') {
        // 草稿已在别处完成（批准／拒绝），本会话的草稿模式作废。
        patchPanel(key, { mode: 'citation', draft: null, dirty: false, text: '' })
      }
      return
    }
    // 有待审草稿就该让人看见：只有"用户主动收起过这份快照"才维持隐藏。
    patchPanel(key, {
      hidden: existing ? existing.hidden : false,
      mode: 'draft',
      draft,
      dirty: false,
      text: draft.content || '',
      textDisabled: false,
      draftRevision: revision,
    })
  }

  /** 切到引用模式并载入笔记正文；有未保存编辑时不覆盖。 */
  async function openCitation(cite: Citation): Promise<void> {
    if (!cite?.file_name) return
    const key = citePaneKey(currentId.value)
    const existing = panels.value[key]
    // 离开草稿，或换到另一篇笔记，都会丢掉当前未保存的正文，必须先问一次。
    const leavingDraft = existing?.mode === 'draft'
    const switchingFile = !!existing?.fileName && existing.fileName !== cite.file_name
    if ((leavingDraft || switchingFile) && !(await confirmPanelDiscard(true))) return
    patchPanel(key, {
      hidden: false,
      mode: 'citation',
      draft: null,
      fileName: cite.file_name,
      dirty: false,
      hintLocate: '',
      text: '',
      textDisabled: true,
      selStart: 0,
      selEnd: 0,
      scrollTop: 0,
    })
    await loadCitationText(key, cite.file_name, cite.quote ?? '')
  }

  /** 重新载入面板正文；dirty 时保留本地缓冲，不被服务端内容覆盖。 */
  async function reloadPanel(id: string | null): Promise<void> {
    const key = citePaneKey(id)
    const snapshot = panels.value[key]
    if (!snapshot || snapshot.hidden) return
    if (snapshot.mode === 'draft' || snapshot.dirty || !snapshot.fileName) return
    await loadCitationText(key, snapshot.fileName, '')
  }

  async function loadCitationText(
    key: string,
    fileName: string,
    quote: string,
  ): Promise<void> {
    try {
      const note = await readNote(fileName)
      // 期间用户可能已经切走：键还在才算数。
      if (citePaneKey(currentId.value) !== key) return
      patchPanel(key, {
        text: note.content ?? '',
        textDisabled: false,
        dirty: false,
      })
      if (!quote) return
      const located = locateQuote(note.content ?? '', quote)
      if (located.start >= 0) {
        patchPanel(key, { selStart: located.start, selEnd: located.start + located.length })
      } else {
        patchPanel(key, { hintLocate: '笔记已更新，原片段无法定位。' })
      }
    } catch {
      if (citePaneKey(currentId.value) !== key) return
      patchPanel(key, { hintLocate: '无法打开笔记。', textDisabled: true })
    }
  }

  async function saveCitation(): Promise<boolean> {
    const current = panel.value
    if (current.mode !== 'citation' || !current.fileName || current.textDisabled) return false
    try {
      await writeNote(current.fileName, current.text)
    } catch (error) {
      await reportError('保存失败', error)
      return false
    }
    patchActivePanel({ dirty: false, hintLocate: '' })
    showSaveToast()
    /* Library 可能也开着这篇：刷新目录与索引；它没有未保存编辑时才换上新正文。 */
    await notes.syncAfterExternalWrite(current.fileName, current.text)
    return true
  }

  async function closePanel(): Promise<boolean> {
    if (!(await confirmPanelDiscard(true))) return false
    patchActivePanel({ hidden: true })
    return true
  }

  // ---------- 面板：草稿模式 ----------

  /** 把草稿切进面板；已有未保存的引用编辑时先按既有约定问一次。 */
  async function openDraft(draft: PendingDraft | unknown): Promise<void> {
    if (!draft || typeof draft !== 'object') return
    const key = citePaneKey(currentId.value)
    const existing = panels.value[key]
    if (existing?.mode === 'draft' && existing.dirty) {
      patchPanel(key, { hintLocate: '服务器草稿已更新，本地未保存编辑已保留。' })
      return
    }
    if (existing?.mode === 'citation' && existing.dirty) {
      const ok = await confirmDialog({
        title: '未保存修改',
        body: '引用笔记有未保存修改，切换到待审草稿会放弃这些修改。',
        confirmText: '放弃修改',
        danger: false,
      })
      if (!ok) return
    }
    const value = draft as PendingDraft
    patchPanel(key, {
      hidden: false,
      mode: 'draft',
      draft: {
        ...value,
        similar: [...(value.similar ?? [])],
        existing_files: [...(value.existing_files ?? [])],
      },
      text: value.content ?? '',
      textDisabled: false,
      dirty: false,
      hintLocate: '',
      draftRevision: revisions.value[key] ?? 0,
    })
  }

  /** 草稿属于别的会话时只进它自己的快照，不动可见面板。 */
  function stashDraftForConversation(id: string, draft: PendingDraft): void {
    const existing = panels.value[citePaneKey(id)]
    if (existing?.mode === 'draft' && existing.dirty) {
      patchPanel(id, { hintLocate: '服务器草稿已更新，本地未保存编辑已保留。' })
      return
    }
    patchPanel(citePaneKey(id), {
      mode: 'draft',
      draft,
      dirty: false,
      text: draft.content ?? '',
      textDisabled: false,
      draftRevision: revisions.value[id] ?? 0,
    })
  }

  /** 只改待审草稿正文，不写正式笔记。 */
  async function saveDraftContent(): Promise<boolean> {
    const current = panel.value
    const threadId = currentId.value
    if (current.mode !== 'draft' || !current.draft || !threadId) return false
    const content = current.text
    if (!content.trim()) {
      await alertDialog('无法保存', '草稿正文不能为空。')
      return false
    }
    try {
      const result = await api.saveDraftContent(threadId, content, current.draftRevision ?? revisions.value[threadId] ?? 0)
      const revision = result.state_revision ?? current.draftRevision ?? 0
      revisions.value[threadId] = revision
      patchPanel(threadId, { draft: result.pending_draft, dirty: false, draftRevision: revision })
      showSaveToast()
      return true
    } catch (error) {
      // 失败保留编辑文本与未保存状态，可重试；409 说明版本已过期。
      await reportError('保存失败', error)
      return false
    }
  }

  /**
   * 审批入口：未保存的正文先落库，再调用既有 /chat/review。
   * 保存失败就停下，不带着没落库的正文去审批。
   */
  async function reviewDraft(
    body: { action: string; write_action?: string; file_name?: string },
  ): Promise<void> {
    const current = panel.value
    const threadId = currentId.value
    if (!current.draft || !threadId) return
    const notice = (text: string) => { if (currentId.value === threadId) pushNotice(text) }
    patchPanel(threadId, { busy: true })
    try {
      if (current.dirty && !(await saveDraftContent())) return
      const draft = current.draft
      const result = await api.reviewDraft({
        thread_id: threadId,
        ...body,
        expected_revision: panels.value[threadId]?.draftRevision ?? revisions.value[threadId] ?? 0,
      })
      if (typeof result.state_revision === 'number') revisions.value[threadId] = result.state_revision
      if (result.status === 'written') {
        const text =
          result.action === 'delete'
            ? `已删除 ${result.file_name}`
            : `已写入 ${result.file_name}`
        clearDraft(threadId)
        notice(text)
        /* 批准会写盘并重建向量：目录与索引状态都要跟着更新。 */
        await notes.refreshAfterExternalChange()
      } else if (result.status === 'rejected') {
        clearDraft(threadId)
        notice('已取消写入')
      } else {
        // 失败保留草稿、正文与动作选择，按钮恢复后可重试。
        const reason = result.error ?? '未知原因'
        patchPanel(threadId, {
          draft,
          hintLocate: `审批失败：${reason}，可修正后重试。`,
        })
        notice(`审批失败：${reason}`)
      }
    } catch (error) {
      const reason = (error as Error).message
      patchPanel(threadId, { hintLocate: `审批失败：${reason}，可修正后重试。` })
      notice(`审批失败：${reason}`)
    } finally {
      patchPanel(threadId, { busy: false })
    }
  }

  /** 审批完成后丢弃草稿状态；没有引用内容就关掉面板。 */
  function clearDraft(owner = citePaneKey(currentId.value)): void {
    const current = panels.value[owner] ?? blankPanel()
    const keepCitation = !current.hidden && !!current.fileName
    patchPanel(owner, {
      draft: null,
      mode: 'citation',
      dirty: false,
      text: '',
      hintLocate: '',
    })
    if (!keepCitation) patchPanel(owner, { hidden: true })
    else if (currentId.value === owner) void reloadPanel(owner)
  }

  /** 未保存提示的文案：草稿与引用的后果不同，不共用一句话。 */
  function panelUnsavedBody(leaving: boolean): string {
    const tail = leaving ? '确定离开？' : '确定放弃？'
    if (panel.value.mode === 'draft') {
      return `待审草稿有未保存修改，${tail}草稿本身仍保留在待审批状态。`
    }
    return `出处笔记有未保存修改，${tail}`
  }

  async function confirmPanelDiscard(leaving: boolean): Promise<boolean> {
    if (!panel.value.dirty) return true
    return confirmDialog({
      title: '未保存修改',
      body: panelUnsavedBody(leaving),
      confirmText: '放弃修改',
      danger: false,
    })
  }

  /** 离开 Assistant 页前调用；只放弃当前动作涉及的缓冲。 */
  async function confirmLeaveAssistant(): Promise<boolean> {
    if (!anyPanelDirty.value) return true
    return confirmDialog({
      title: '未保存修改',
      body: panelUnsavedBody(true),
      confirmText: '放弃修改',
      danger: false,
    })
  }

  /**
   * 确认放弃后清理当前会话这一份缓冲并收起面板。
   * 别的会话的快照不动——它们各自的未保存内容仍然留着。
   */
  function discardActivePanelEdits(): void {
    patchActivePanel({
      hidden: true,
      dirty: false,
      text: '',
      hintLocate: '',
      draft: null,
      mode: 'citation',
      textDisabled: true,
    })
  }

  /** 新会话拿到正式 id 后，把临时键下的面板搬到正式 id 下。 */
  function adoptPanelKey(from: string, newId: string): void {
    if (!newId || from === newId) return
    const pending = panels.value[from]
    if (!pending || panels.value[newId]) return
    const { [from]: _moved, ...rest } = panels.value
    panels.value = { ...rest, [newId]: pending }
  }

  // ---------- 发送 ----------

  /**
   * 发送一轮问题。返回值告诉输入框要不要把文字还给用户：
   * `refused` 是维护窗口，`failed` 是请求没发出去。
   */
  async function send(question: string): Promise<SendOutcome> {
    if (activeRun.value) return 'refused'
    return runStream(question)
  }

  async function resumeRun(): Promise<SendOutcome> {
    const run = activeRun.value
    if (!run || run.status !== 'interrupted' || !currentId.value) return 'refused'
    return runStream('', run.run_id)
  }

  async function runStream(
    question: string,
    resumeId?: string,
    preparedId?: string,
  ): Promise<SendOutcome> {
    // 同步门闩：必须在任何 await 之前置位。
    if (streaming.value) return 'refused'
    const text = question.trim()
    if (!text && !resumeId && !preparedId) return 'refused'
    const owner = citePaneKey(currentId.value)
    const revision = revisions.value[owner] ?? 0
    const selectedAtStart = selectionVersion.value

    streaming.value = true
    models.setStreaming(true)

    try {
      await models.refreshIfStale()
    } catch {
      // 刷新失败不影响发送本身：后端仍会按维护状态拒绝。
    }
    if (!models.canSend) {
      streaming.value = false
      models.setStreaming(false)
      pushNotice('向量索引重建中，暂时不能发送消息；已有内容仍可查看。')
      return 'refused'
    }

    // 必须拿响应式代理再往下用：写进 liveTurn 后组件读到的是代理，
    // 继续改原始对象既不会触发刷新，也会让 identity 比较失效（导致这一轮被重复追加）。
    const turn = reactive(newMessage('assistant', ''))
    turn.live = true
    turn.traceLabel = 'Thinking...'
    turn.ownerKey = owner
    turn.selectionAtStart = selectedAtStart
    const requestId = newRequestId()
    const userRow = newMessage('user', text)
    userRow.requestId = requestId
    userRow.ownerKey = turn.ownerKey
    // A recovered (prepared) turn already holds its edited user message on the server.
    if (!resumeId && !preparedId) messages.value = [...messages.value, userRow]
    liveTurn.value = turn
    const accumulator = new TurnAccumulator()

    let outcome: SendOutcome = 'sent'
    try {
      const response = preparedId
        ? await api.openChatStream('', owner === CITE_PENDING_KEY ? null : owner, undefined, preparedId)
        : resumeId
          ? await api.openResumeStream(owner, resumeId, revision)
          : await api.openChatStream(text, owner === CITE_PENDING_KEY ? null : owner, requestId)
      if (!response.ok) {
        const payload = await readJsonBody(response)
        const detail =
          response.status === 404
            ? '会话不存在'
            : extractErrorMessage(payload, response.status)
        throw new ApiError(response.status, detail)
      }
      if (!response.body) throw new ApiError(0, '响应没有可读的流')
      await consumeSse(response.body, (raw) => handleEvent(raw, turn, accumulator))
    } catch (error) {
      turn.content = `请求失败：${(error as Error).message}`
      turn.traceLabel = ''
      outcome = 'failed'
    } finally {
      finalizeTurn(turn, accumulator)
      streaming.value = false
      models.setStreaming(false)
      if (resumeId || preparedId || outcome === 'failed' || runs.value[turn.ownerKey]) {
        await refreshRun(turn.ownerKey)
      }
      if (resumeId && !runs.value[turn.ownerKey] && currentId.value === turn.ownerKey) {
        await loadMessages(turn.ownerKey)
      }
    }
    return outcome
  }

  async function refreshRun(owner: string): Promise<void> {
    if (owner === CITE_PENDING_KEY) return
    try {
      const detail = await api.getConversation(owner)
      runs.value[owner] = detail.active_run ?? null
      revisions.value[owner] = detail.state_revision ?? 0
      applyServerDraft(owner, detail.pending_draft, detail.state_revision ?? 0)
    } catch {
      // A failed refresh must not authorize a new question over a known run.
    }
  }

  /** 事件处理：归属以这一轮自己的 ownerKey 为准，不读当前选中的会话。 */
  function handleEvent(
    raw: { event: string; data: unknown },
    turn: ChatMessage,
    accumulator: TurnAccumulator,
  ): void {
    const event = decodeChatEvent(raw)
    if (event.type === 'conversation') {
      const previous = turn.ownerKey
      adoptPanelKey(previous, event.id)
      // 就地改写归属：面板与这一轮都不必搬来搬去。
      turn.ownerKey = event.id
      if (turn.selectionAtStart === selectionVersion.value) currentId.value = event.id
      void loadConversations()
      return
    }
    if (event.type === 'draft') {
      // 只有草稿属于当前正在看的会话时才动可见面板，否则进它自己的快照。
      const stillHere = citePaneKey(currentId.value) === turn.ownerKey
      if (stillHere) void openDraft(event.draft)
      else stashDraftForConversation(turn.ownerKey, event.draft)
      return
    }
    if (event.type === 'user_message') {
      if (event.runId) runs.value[turn.ownerKey] = { run_id: event.runId, status: 'running' }
      // 按客户端幂等键替换乐观行，不靠文本或下标匹配。
      const requestId = event.requestId
      if (requestId) {
        messages.value = messages.value.map((item) =>
          item.requestId === requestId
            ? { ...item, id: event.messageId, turnId: event.turnId }
            : item,
        )
      }
      return
    }
    if (event.type === 'turn_complete') {
      // The turn published a new head; keep the draft/approval token current.
      runs.value[turn.ownerKey] = null
      if (typeof event.stateRevision === 'number') {
        revisions.value[turn.ownerKey] = event.stateRevision
        const snapshot = panels.value[turn.ownerKey]
        if (snapshot?.mode === 'draft' && !snapshot.dirty) {
          patchPanel(turn.ownerKey, { draftRevision: event.stateRevision })
        }
      }
      return
    }
    if (event.type === 'unknown') return

    accumulator.apply(event)
    turn.content = accumulator.rawText
    turn.citations = accumulator.citations
    turn.toolSteps = [...accumulator.steps]
    turn.traceLabel = liveTraceLabel(accumulator.steps)
  }

  /** 流结束：收尾步骤，把进行中的那一轮落成普通消息。 */
  function finalizeTurn(turn: ChatMessage, accumulator: TurnAccumulator): void {
    accumulator.finish()
    turn.toolSteps = [...accumulator.steps]
    turn.live = false
    // 按 key 判断：turn 可能被 Vue 包装过，直接比对象引用并不可靠。
    if (liveTurn.value?.key === turn.key) liveTurn.value = null
    // 只有仍停在这一轮所属会话时才接进消息列表；否则它已经在服务端，重开会拉到。
    if (turn.ownerKey === citePaneKey(currentId.value)) {
      messages.value = [...messages.value, turn]
    }
  }

  // ---------- 编辑历史消息与整体回退 ----------

  const editingKey = ref<string | null>(null)
  const editingText = ref('')
  const recoveryPreview = ref<RecoveryPreview | null>(null)
  const recoveryJob = ref<RecoveryJob | null>(null)
  const recoveryPhase = ref<
    'idle' | 'editing' | 'previewing' | 'confirming' | 'running' | 'conflict' | 'failed'
  >('idle')
  const recoveryError = ref('')

  function resetRecovery(): void {
    editingKey.value = null
    editingText.value = ''
    recoveryPreview.value = null
    recoveryJob.value = null
    recoveryError.value = ''
    recoveryPhase.value = 'idle'
  }

  /** 同时只编辑一条；未持久化或不可编辑的消息不进入编辑态。 */
  function beginEdit(message: ChatMessage): void {
    if (!message.editable || !message.id) return
    editingKey.value = message.key
    editingText.value = message.content
    recoveryPhase.value = 'editing'
  }

  function updateEditingText(text: string): void {
    editingText.value = text
  }

  function cancelRecovery(): void {
    resetRecovery()
  }

  /** 提交编辑：先存未保存草稿，再预览；冲突只展示取消，不退化为强制覆盖。 */
  async function submitEdit(): Promise<void> {
    const key = editingKey.value
    const conversationId = currentId.value
    if (!key || !conversationId || recoveryPhase.value === 'running') return
    const message = visibleMessages.value.find((item) => item.key === key)
    if (!message || !message.id) return
    if (editingText.value.trim() === message.content.trim()) {
      resetRecovery()
      return
    }
    if (panel.value.dirty && panel.value.mode === 'draft' && !(await saveDraftContent())) return

    recoveryPhase.value = 'previewing'
    recoveryError.value = ''
    try {
      const preview = await recoveryApi.previewRecovery(
        conversationId, message.id, editingText.value, revisions.value[conversationId] ?? 0,
      )
      recoveryPreview.value = preview
      if (!preview.can_apply) {
        recoveryPhase.value = 'conflict'
        return
      }
      if (preview.requires_confirmation) {
        recoveryPhase.value = 'confirming'
        return
      }
      await confirmRecovery()
    } catch (error) {
      recoveryError.value = (error as Error).message
      recoveryPhase.value = 'failed'
    }
  }

  async function confirmRecovery(): Promise<void> {
    const preview = recoveryPreview.value
    const conversationId = currentId.value
    // Only a fresh preview may start; a conflict/failed plan must not be force-applied.
    if (!preview || !conversationId) return
    if (recoveryPhase.value !== 'confirming' && recoveryPhase.value !== 'previewing') return
    recoveryPhase.value = 'running'
    try {
      const job = await recoveryApi.startRecovery(
        conversationId, preview.preview_id, editingText.value,
        recoveryApi.requiredConfirmations(preview), newRequestId(),
      )
      await pollRecovery(job)
    } catch (error) {
      recoveryError.value = (error as Error).message
      recoveryPhase.value = 'failed'
    }
  }

  async function retryRecovery(): Promise<void> {
    const job = recoveryJob.value
    if (!job || recoveryPhase.value === 'running') return
    recoveryPhase.value = 'running'
    try {
      await pollRecovery(await recoveryApi.retryRecovery(job.job_id, newRequestId()))
    } catch (error) {
      recoveryError.value = (error as Error).message
      recoveryPhase.value = 'failed'
    }
  }

  /** 轮询真实任务直到终态；成功后重载活动状态并用 prepared turn 续接生成。 */
  async function pollRecovery(job: RecoveryJob): Promise<void> {
    recoveryJob.value = job
    let current = job
    for (let i = 0; i < 120 && current.status !== 'succeeded' && current.status !== 'failed'; i += 1) {
      await new Promise((resolve) => setTimeout(resolve, 400))
      current = await recoveryApi.getRecoveryJob(current.job_id)
      recoveryJob.value = current
    }
    if (current.status !== 'succeeded' || !current.prepared_turn_id) {
      recoveryError.value = current.error ?? '恢复未完成'
      recoveryPhase.value = 'failed'
      return
    }
    await loadMessages(current.conversation_id)
    await refreshRun(current.conversation_id)
    await notes.refreshAfterExternalChange()
    const preparedTurnId = current.prepared_turn_id
    resetRecovery()
    await runStream('', undefined, preparedTurnId)
  }

  async function runPrepared(preparedTurnId: string): Promise<SendOutcome> {
    return runStream('', undefined, preparedTurnId)
  }

  return {
    conversations,
    currentId,
    messages,
    visibleMessages,
    hasMessages,
    panels,
    panel,
    panelHint,
    panelSaveDisabled,
    panelSaveLabel,
    panelTitle,
    panelOverrideAvailable: computed(() => draftOverrideAvailable(panel.value.draft)),
    streaming,
    selectionVersion,
    stateRevision,
    activeRun,
    anyPanelDirty,
    // 会话
    loadConversations,
    openConversation,
    loadMessages,
    newChat,
    renameConversation,
    removeConversation,
    // 面板
    patchActivePanel,
    patchPanel,
    applyServerDraft,
    openCitation,
    reloadPanel,
    saveCitation,
    closePanel,
    openDraft,
    saveDraftContent,
    reviewDraft,
    confirmPanelDiscard,
    confirmLeaveAssistant,
    discardActivePanelEdits,
    adoptPanelKey,
    // 发送
    send,
    resumeRun,
    pushNotice,
    // 编辑历史消息与整体回退
    editingKey,
    editingText,
    recoveryPreview,
    recoveryJob,
    recoveryPhase,
    recoveryError,
    beginEdit,
    updateEditingText,
    submitEdit,
    confirmRecovery,
    cancelRecovery,
    retryRecovery,
    runPrepared,
  }
})
