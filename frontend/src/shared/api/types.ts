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
  source_urls?: string[]
  user_supplied_source_urls?: string[]
  source_file_ids?: string[]
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
  /** 进行中或失败的恢复任务，前端据此显示进度并续办。 */
  recovery?: RecoveryJob | null
}

export interface RecoveryFileChange {
  path: string
  action: string
  target_hash?: string | null
  current_hash?: string | null
}

export interface RecoveryFolderChange {
  path: string
  action: string
}

export interface RecoveryConflict {
  path: string
  reason: string
}

/** POST …/recoveries/preview 的返回：纯预览，尚未改动任何正文。 */
export interface RecoveryPreview {
  preview_id: string
  conversation_id: string
  can_apply: boolean
  requires_confirmation: boolean
  file_changes: RecoveryFileChange[]
  folder_changes: RecoveryFolderChange[]
  conflicts: RecoveryConflict[]
  affected_messages: string[]
  state_revision: number
  workspace_seq: number
  content_digest: string
  expires_at?: string | null
}

/** 恢复任务状态。 */
export interface RecoveryJob {
  job_id: string
  operation_id: string
  conversation_id: string
  status: string
  stage?: string | null
  prepared_turn_id?: string | null
  error?: string | null
  retryable: boolean
  plan?: Record<string, unknown>
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
  attachments?: Array<{ id: string; name: string; status?: string; parse_profile_revision?: number | null }>
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

export type AuthMode = 'api_key' | 'none'
export type CapabilityName = 'text' | 'vision' | 'tool_calling' | 'streaming' | 'json_mode' | 'reasoning'
export type CapabilityStatus = 'enabled' | 'disabled'
export type VerificationStatus = 'unverified' | 'verified' | 'failed'
export type JobStatus = 'running' | 'succeeded' | 'failed' | 'interrupted'
export type EmbeddingAvailability = 'available' | 'incomplete' | 'unsupported'
export type RetrievalState = 'ok' | 'empty' | 'missing' | 'config_mismatch' | 'unavailable'

export interface CapabilityRecord {
  capability: CapabilityName
  status: CapabilityStatus
  verification: VerificationStatus
  source: 'manual' | 'probe'
  checked_at: string | null
  probe_version: number | null
  evidence: Record<string, unknown> | null
}

/** 对外配置永不含 api_key，只用 has_api_key 表达"有没有凭据"。 */
export interface ModelConfig {
  id: string
  label: string
  provider: string
  model: string
  base_url: string
  auth_mode: AuthMode
  has_api_key: boolean
  timeout_s: number
  max_retries: number
  context_window: number
  temperature: number | null
  max_tokens: number | null
  is_active: boolean
  revision: number
  capabilities: CapabilityRecord[]
}

export interface ProviderSpec {
  id: string
  label: string
  default_base_url: string
  base_url_required: boolean
  auth_modes: AuthMode[]
}

/** 提交用的配置体；省略 api_key 表示保留已保存的那一个。 */
export interface ModelConfigInput {
  label: string
  provider: string
  model: string
  base_url?: string
  api_key?: string
  clear_api_key?: boolean
  auth_mode?: AuthMode
  timeout_s?: number
  max_retries?: number
  context_window?: number
  temperature?: number | null
  max_tokens?: number | null
}

export interface ModelConfigWriteIn extends ModelConfigInput {
  expected_revision: number
}

/** POST /models/{id}/activate：可选携带完整 config 实现“保存并启用”。 */
export interface ModelActivateIn {
  expected_revision: number
  config?: ModelConfigInput
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
  models: ModelConfig[]
  active_model: ModelConfig | null
  embedding_revision: number
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

export interface ModelTestResult {
  verified: boolean
  streaming: boolean
  tool_calling: boolean
  message: string | null
}
