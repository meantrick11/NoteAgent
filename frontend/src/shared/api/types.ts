/**
 * 后端合同对应的 TS 类型。字段名与 pydantic schema 一一对应，不做重命名：
 * 迁移期间任何一次改名都会让前后端悄悄错位。
 *
 * 来源：chat/schemas.py、notes/schemas.py、model_management/schemas.py。
 */

// ---------- 会话 ----------

export interface Conversation {
  id: string
  title: string
  updated_at: string
}

/** 草稿由服务端生成，字段随 draft 工具的结果走。 */
export interface PendingDraft {
  action: string
  file_name: string
  content: string
  reason?: string
  similar?: string[]
  existing_files?: string[]
}

export interface ConversationDetail extends Conversation {
  pending_draft: PendingDraft | null
  /** 活动 head 的单调版本号；草稿保存／审批必须原样回传。 */
  state_revision?: number
  /** 正在进行的运行（prepared/running/interrupted），重连时可据此续接。 */
  active_run?: {
    run_id: string
    status: string
    turn_id?: string | null
    user_message_id?: string | null
    request_id?: string
  } | null
}

export interface Citation {
  index: number
  file_name: string
  chunk_index?: number | null
  quote?: string | null
}

export interface ToolStep {
  name: string
  status: string
  preview: string
  arguments: string
}

export interface Message {
  id: string
  role: string
  content: string
  created_at: string
  turn_id?: string | null
  citations: Citation[]
  tool_steps: ToolStep[]
  /** 可回退编辑需要持久化的安全边界；阶段 B 未完成前一律为 false。 */
  editable?: boolean
  edit_unavailable_reason?: string | null
}

export interface ReviewRequest {
  thread_id: string
  action: string
  write_action?: string
  file_name?: string
  expected_revision?: number
}

/**
 * POST /chat/review 的响应。业务失败也走 200，只把 error 放在 JSON 里，
 * 所以调用方必须看 status／error，不能只看 HTTP 状态码。
 */
export interface ReviewResult {
  status?: 'written' | 'rejected'
  action?: string
  file_name?: string
  error?: string
  state_revision?: number
}

// ---------- 笔记 ----------

export interface NoteFile {
  file_name: string
  folder: string
  mtime: number
  indexed: boolean
}

export interface NotesList {
  files: NoteFile[]
  folders: string[]
}

export interface NoteContent {
  file_name: string
  content: string
}

export interface NoteWriteResult {
  file_name: string
  indexed: boolean
}

export interface FolderRenameResult {
  from_name: string
  to_name: string
  files: string[]
}

export interface FolderDeleteResult {
  name: string
  deleted: string[]
}

// ---------- 模型设置 ----------

export type ChatProviderName = 'deepseek' | 'openai-compatible'
export type AuthMode = 'api_key' | 'none'
export type CredentialSource = 'env' | 'ui'
export type JobStatus = 'running' | 'succeeded' | 'failed' | 'interrupted'
export type EmbeddingAvailability = 'available' | 'incomplete' | 'unsupported'
export type RetrievalState = 'ok' | 'empty' | 'missing' | 'config_mismatch' | 'unavailable'

/** 对外配置永不含 api_key，只用 has_api_key 表达"有没有凭据"。 */
export interface ChatProfile {
  id: string
  label: string
  provider: ChatProviderName
  model: string
  base_url: string
  auth_mode: AuthMode
  context_window: number
  has_api_key: boolean
  credential_source: CredentialSource
}

/** 提交用的配置体；省略 api_key 表示保留已保存的那一个。 */
export interface ChatProfileInput {
  id?: string
  label: string
  provider: ChatProviderName
  model: string
  base_url?: string
  api_key?: string
  clear_api_key?: boolean
  auth_mode?: AuthMode
  context_window?: number
}

export interface ChatProfileWriteIn extends ChatProfileInput {
  expected_revision: number
}

/** POST /model-settings/chat/activate：profile_id 与 profile 必须二选一。 */
export interface ChatActivateIn {
  expected_revision: number
  profile_id?: string
  profile?: ChatProfileInput
}

export interface ActiveEmbedding {
  model_id: string
  resolved_revision: string | null
  collection: string
  fingerprint: string | null
}

export interface EmbeddingJob {
  id: string
  status: JobStatus
  stage: string
  completed: number
  total: number
  active_model: string
  target_model: string
  error: string | null
  started_at: string
  finished_at: string | null
}

export interface ModelSettingsStatus {
  revision: number
  chat_profiles: ChatProfile[]
  active_chat: ChatProfile | null
  active_embedding: ActiveEmbedding | null
  retrieval_available: boolean
  retrieval_problem: string | null
  retrieval_state: RetrievalState
  indexed_files: number
  corpus_files: number
  busy: boolean
  embedding_job: EmbeddingJob | null
}

export interface EmbeddingCandidate {
  model_id: string
  label: string
  availability: EmbeddingAvailability
  reason: string | null
  active: boolean
}

export interface EmbeddingSwitchResult {
  unchanged: boolean
  job: EmbeddingJob | null
}

export interface ChatTestResult {
  verified: boolean
  streaming: boolean
  tool_calling: boolean
  message: string | null
}
