/**
 * 整体回退的接口封装与展示辅助。
 *
 * 前端不携带任何 paths/commit 作为恢复权威：路径、目标与冲突一律来自服务端预览计划。
 */

import { jsonRequest, requestJson } from '@/shared/api/http'
import type { RecoveryJob, RecoveryPreview } from '@/shared/api/types'

/** POST /conversations/{id}/recoveries/preview —— 纯预览，不改动正文。 */
export function previewRecovery(
  conversationId: string,
  messageId: string,
  editedContent: string,
  expectedRevision?: number,
): Promise<RecoveryPreview> {
  return jsonRequest<RecoveryPreview>(
    `/conversations/${encodeURIComponent(conversationId)}/recoveries/preview`,
    'POST',
    {
      message_id: messageId,
      edited_content: editedContent,
      expected_revision: expectedRevision,
    },
  )
}

/** POST /conversations/{id}/recoveries —— 用确认过的预览启动恢复。 */
export function startRecovery(
  conversationId: string,
  previewId: string,
  editedContent: string,
  confirmedFileChanges: string[],
  operationId: string,
): Promise<RecoveryJob> {
  return jsonRequest<RecoveryJob>(
    `/conversations/${encodeURIComponent(conversationId)}/recoveries`,
    'POST',
    {
      preview_id: previewId,
      edited_content: editedContent,
      confirmed_file_changes: confirmedFileChanges,
      operation_id: operationId,
    },
  )
}

/** GET /recoveries/{job_id} —— 任务进度，维护窗口内也可读。 */
export function getRecoveryJob(jobId: string): Promise<RecoveryJob> {
  return requestJson<RecoveryJob>(`/recoveries/${encodeURIComponent(jobId)}`)
}

/** POST /recoveries/{job_id}/retry —— 续办同一计划。 */
export function retryRecovery(jobId: string, operationId: string): Promise<RecoveryJob> {
  return jsonRequest<RecoveryJob>(
    `/recoveries/${encodeURIComponent(jobId)}/retry`,
    'POST',
    { operation_id: operationId },
  )
}

/** 预览里所有需要确认的路径（文件 + 目录）。 */
export function requiredConfirmations(preview: RecoveryPreview): string[] {
  return [
    ...preview.file_changes.map((change) => change.path),
    ...preview.folder_changes.map((change) => change.path),
  ]
}

/** 冲突原因，拼接成一行可读文案。 */
export function conflictSummary(preview: RecoveryPreview): string {
  return preview.conflicts
    .map((conflict) => (conflict.path ? `${conflict.path}：${conflict.reason}` : conflict.reason))
    .join('；')
}
