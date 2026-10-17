import { ApiError, extractErrorMessage, requestJson, jsonRequest } from '@/shared/api/http'

export interface SourceFile {
  id: string
  original_filename: string
  storage_path: string
  display_name: string
  folder: string
  media_type: string
  size_bytes: number
  sha256: string
  status: 'stored' | 'queued' | 'parsing' | 'ready' | 'failed' | 'deleted'
  error: string | null
  created_at: string
  updated_at: string
}

const path = (id: string) => `/source-files/${encodeURIComponent(id)}`
export const listSourceFiles = () => requestJson<SourceFile[]>('/source-files')
export const getSourceFile = (id: string) => requestJson<SourceFile>(path(id))
export const retrySourceFile = (id: string) => jsonRequest<SourceFile>(`${path(id)}/retry`, 'POST', {})
export const patchSourceFile = (id: string, body: { display_name?: string; folder?: string }) =>
  jsonRequest<SourceFile>(path(id), 'PATCH', body)
export const deleteSourceFile = (id: string) => requestJson<null>(path(id), { method: 'DELETE' })
export const listFolders = () => requestJson<{ folders: string[] }>('/source-files/folders')
export const createFolder = (name: string) => jsonRequest<{ name: string }>('/source-files/folders', 'POST', { name })
export const renameFolder = (name: string, next: string) =>
  jsonRequest<{ name: string }>(`/source-files/folders/${encodeURIComponent(name)}`, 'PATCH', { name: next })
export const deleteFolder = (name: string) => requestJson<null>(`/source-files/folders/${encodeURIComponent(name)}`, { method: 'DELETE' })
export const previewUrl = (id: string) => `${path(id)}/preview`
export const downloadUrl = (id: string) => `${path(id)}/download`

export function uploadSourceFile(file: File, onProgress: (percent: number) => void): {
  promise: Promise<SourceFile>
  cancel: () => void
} {
  const xhr = new XMLHttpRequest()
  const promise = new Promise<SourceFile>((resolve, reject) => {
    xhr.open('POST', '/source-files')
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100))
    }
    xhr.onload = () => {
      let body: Record<string, unknown> = {}
      try { body = JSON.parse(xhr.responseText) as Record<string, unknown> } catch { /* empty response */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as unknown as SourceFile)
      else reject(new ApiError(xhr.status, extractErrorMessage(body, xhr.status)))
    }
    xhr.onerror = () => reject(new ApiError(0, '上传连接失败'))
    xhr.onabort = () => reject(new ApiError(0, '上传已取消'))
    const data = new FormData()
    data.append('file', file)
    xhr.send(data)
  })
  return { promise, cancel: () => xhr.abort() }
}
