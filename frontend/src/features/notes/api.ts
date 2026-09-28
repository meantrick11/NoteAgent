import { jsonRequest, requestJson } from '@/shared/api/http'
import type {
  FolderDeleteResult,
  FolderRenameResult,
  NoteContent,
  NoteWriteResult,
  NotesList,
} from '@/shared/api/types'

/**
 * 逐段编码嵌套路径：`a/b c.md` → `a/b%20c.md`，整段编码会把 `/` 变成 %2F 而打不开。
 */
export function noteUrl(fileName: string): string {
  return `/notes/${fileName.split('/').map(encodeURIComponent).join('/')}`
}

/** GET /notes —— 目录与笔记列表，含 mtime 与索引状态。 */
export function listNotes(): Promise<NotesList> {
  return requestJson<NotesList>('/notes')
}

/** GET /notes/{path} —— 读取 Markdown 正文。 */
export function readNote(fileName: string): Promise<NoteContent> {
  return requestJson<NoteContent>(noteUrl(fileName))
}

/** PUT /notes/{path} —— 覆盖正文并重建该笔记的向量。 */
export function writeNote(fileName: string, content: string): Promise<NoteWriteResult> {
  return jsonRequest<NoteWriteResult>(noteUrl(fileName), 'PUT', { content })
}

/** POST /notes —— 新建笔记，服务端会补 .md 后缀并建索引。 */
export function createNote(fileName: string): Promise<NoteWriteResult> {
  return jsonRequest<NoteWriteResult>('/notes', 'POST', { file_name: fileName })
}

/** DELETE /notes/{path} —— 删除文件并清掉它的向量。 */
export function deleteNote(fileName: string): Promise<NoteWriteResult> {
  return requestJson<NoteWriteResult>(noteUrl(fileName), { method: 'DELETE' })
}

/** POST /notes/{path}/index —— 只补建向量，不动 Markdown。 */
export function indexNote(fileName: string): Promise<NoteWriteResult> {
  return jsonRequest<NoteWriteResult>(`${noteUrl(fileName)}/index`, 'POST', {})
}

/** POST /notes/folders —— 新建一级目录。 */
export function createFolder(name: string): Promise<{ name: string }> {
  return jsonRequest<{ name: string }>('/notes/folders', 'POST', { name })
}

/** POST /notes/folders/rename —— 服务的 JSON 键是 from/to，不是 from_path/to_path。 */
export function renameFolder(from: string, to: string): Promise<FolderRenameResult> {
  return jsonRequest<FolderRenameResult>('/notes/folders/rename', 'POST', { from, to })
}

/** DELETE /notes/folders/{name} —— 连目录内笔记与向量一起删。 */
export function deleteFolder(name: string): Promise<FolderDeleteResult> {
  return requestJson<FolderDeleteResult>(`/notes/folders/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
}

/** POST /notes/move —— 同样是 from/to 键。 */
export function moveNote(from: string, to: string): Promise<NoteWriteResult> {
  return jsonRequest<NoteWriteResult>('/notes/move', 'POST', { from, to })
}
