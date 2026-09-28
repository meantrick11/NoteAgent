/**
 * Library（原 Documents）的状态：目录树、当前笔记、未保存正文与索引状态。
 *
 * 与旧实现一致的几条约束：
 *  - 一级目录：文件夹只有一层，笔记移动的目标也只能是根或某个一级目录；
 *  - 移动／重命名的 JSON 键是 `from`/`to`；
 *  - 写入前先 `refreshIfStale`，避免另一标签页刚进入维护窗口时提示不准；
 *  - 保存失败保留正文与 dirty，不丢用户已经敲进去的字；
 *  - 引用面板保存或草稿批准之后要刷新目录与索引状态，但**不覆盖本页未保存的正文**。
 */

import { computed, ref, shallowRef } from 'vue'
import { defineStore } from 'pinia'

import { alertDialog, confirmDialog, promptDialog } from '@/shared/ui/confirm'
import { showSaveToast } from '@/shared/ui/toast'
import type { NoteFile } from '@/shared/api/types'
import * as api from './api'
import { useModelsStore } from '@/features/models/store'

/** 拖动超过这个距离才算"在拖"，否则仍是点击。 */
const DRAG_THRESHOLD_PX = 6

export interface FolderGroup {
  folder: string
  files: NoteFile[]
}

export interface TreeAnchor {
  kind: 'note' | 'folder'
  id: string
}

/** 无扩展名时补 .md，与旧页面的输入习惯一致。 */
export function notePath(folder: string, name: string): string {
  return folder ? `${folder}/${name}` : name
}

export function basename(path: string): string {
  return path.includes('/') ? (path.split('/').pop() as string) : path
}

export function parentFolder(path: string): string {
  return path.includes('/') ? (path.split('/')[0] as string) : ''
}

export const useNotesStore = defineStore('notes', () => {
  const models = useModelsStore()

  const files = shallowRef<NoteFile[]>([])
  const folders = shallowRef<string[]>([])
  const current = ref<string | null>(null)
  const content = ref('')
  const dirty = ref(false)
  const collapsed = ref<string[]>([])
  const anchor = shallowRef<TreeAnchor | null>(null)
  const indexing = ref<string[]>([])
  /** 跨页面写入后给用户的提示：本页有未保存编辑时不能静默覆盖。 */
  const conflictHint = ref('')

  const currentMeta = computed(() =>
    files.value.find((file) => file.file_name === current.value),
  )
  const currentIndexed = computed(() => Boolean(currentMeta.value?.indexed))
  const currentIndexing = computed(() =>
    current.value ? indexing.value.includes(current.value) : false,
  )

  /** 目录树：先一级目录（含其笔记），再根目录下的笔记。 */
  const tree = computed<{ groups: FolderGroup[]; rootFiles: NoteFile[] }>(() => {
    const groups = folders.value.map((folder) => ({
      folder,
      files: files.value.filter((file) => file.folder === folder),
    }))
    const rootFiles = files.value.filter((file) => !file.folder)
    return { groups, rootFiles }
  })

  /** 新建笔记落在哪：选中的目录 > 当前笔记所在目录 > 根目录。 */
  const targetFolder = computed(() => {
    if (anchor.value?.kind === 'folder') return anchor.value.id
    if (current.value) return parentFolder(current.value)
    return ''
  })

  /** 编辑区同时受"是否已打开笔记"和"维护窗口"约束，两者不互相覆盖。 */
  const canEdit = computed(() => current.value !== null && models.canSend)

  function isCollapsed(folder: string): boolean {
    return collapsed.value.includes(folder)
  }

  function toggleCollapsed(folder: string): void {
    collapsed.value = isCollapsed(folder)
      ? collapsed.value.filter((name) => name !== folder)
      : [...collapsed.value, folder]
  }

  function selectFolder(folder: string): void {
    anchor.value = { kind: 'folder', id: folder }
  }

  async function loadCatalog(): Promise<void> {
    try {
      const list = await api.listNotes()
      files.value = list.files ?? []
      folders.value = list.folders ?? []
    } catch {
      // 读不到就保持上一次的目录；错误由具体动作反馈。
    }
  }

  function applyContent(text: string): void {
    content.value = text
    dirty.value = false
    conflictHint.value = ''
  }

  async function openDocument(fileName: string): Promise<boolean> {
    if (dirty.value && current.value && current.value !== fileName) {
      const ok = await confirmDialog({
        title: '未保存修改',
        body: '有未保存修改，确定切换？',
        danger: false,
      })
      if (!ok) return false
    }
    try {
      const note = await api.readNote(fileName)
      current.value = note.file_name
      anchor.value = { kind: 'note', id: note.file_name }
      applyContent(note.content ?? '')
      return true
    } catch {
      return false
    }
  }

  /** 保存正文。失败时保留正文与 dirty，用户不必重打。 */
  async function saveDocument(): Promise<boolean> {
    if (!current.value) return false
    // 另一标签页可能刚进入向量维护窗口：保存前刷新状态，提示会更准确。
    await models.refreshIfStale()
    try {
      await api.writeNote(current.value, content.value)
    } catch (error) {
      await alertDialog('保存失败', (error as Error).message)
      return false
    }
    dirty.value = false
    showSaveToast()
    await loadCatalog()
    return true
  }

  async function indexDocument(fileName: string): Promise<void> {
    if (indexing.value.includes(fileName)) return
    indexing.value = [...indexing.value, fileName]
    try {
      await api.indexNote(fileName)
    } catch (error) {
      await alertDialog('入库失败', (error as Error).message)
    } finally {
      indexing.value = indexing.value.filter((name) => name !== fileName)
      await loadCatalog()
    }
  }

  async function createFolder(): Promise<void> {
    const name = await promptDialog({
      title: '新建文件夹',
      body: '文件夹名称（仅一层）',
      value: '',
    })
    if (name === null || !name.trim()) return
    try {
      const created = await api.createFolder(name.trim())
      anchor.value = { kind: 'folder', id: created.name }
    } catch (error) {
      await alertDialog('创建失败', (error as Error).message)
    }
    await loadCatalog()
  }

  async function createNote(): Promise<void> {
    const folder = targetFolder.value
    const value = await promptDialog({
      title: '新建笔记',
      body: folder ? `将创建在「${folder}」下` : '将创建在根目录',
      value: '',
    })
    if (value === null || !value.trim()) return
    try {
      const created = await api.createNote(notePath(folder, value.trim()))
      await loadCatalog()
      await openDocument(created.file_name)
    } catch (error) {
      await alertDialog('创建失败', (error as Error).message)
    }
  }

  async function moveNote(fromPath: string, toPath: string): Promise<boolean> {
    try {
      const moved = await api.moveNote(fromPath, toPath)
      if (current.value === fromPath) current.value = moved.file_name
      anchor.value = { kind: 'note', id: moved.file_name }
      await loadCatalog()
      if (current.value === moved.file_name && !dirty.value) {
        await openDocument(moved.file_name)
      }
      return true
    } catch (error) {
      await alertDialog('移动失败', (error as Error).message)
      return false
    }
  }

  async function renameNote(fileName: string): Promise<void> {
    const suggestion = basename(fileName).replace(/\.md$/i, '')
    const value = await promptDialog({
      title: '重命名笔记',
      body: '输入新的文件名（可省略 .md）',
      value: suggestion,
    })
    if (value === null || !value.trim()) return
    await moveNote(fileName, notePath(parentFolder(fileName), value.trim()))
  }

  async function renameFolder(name: string): Promise<void> {
    const value = await promptDialog({
      title: '重命名文件夹',
      body: '输入新的文件夹名（仅一层）',
      value: name,
    })
    if (value === null || !value.trim() || value.trim() === name) return
    try {
      const result = await api.renameFolder(name, value.trim())
      if (current.value && parentFolder(current.value) === name) {
        current.value = notePath(result.to_name, basename(current.value))
      }
      if (anchor.value?.kind === 'folder' && anchor.value.id === name) {
        anchor.value = { kind: 'folder', id: result.to_name }
      }
      if (isCollapsed(name)) {
        collapsed.value = [...collapsed.value.filter((item) => item !== name), result.to_name]
      }
    } catch (error) {
      await alertDialog('重命名失败', (error as Error).message)
    }
    await loadCatalog()
  }

  async function deleteNote(fileName: string): Promise<void> {
    const ok = await confirmDialog({
      title: '删除笔记',
      body: `确定删除「${basename(fileName)}」？删除后无法恢复。`,
    })
    if (!ok) return
    try {
      await api.deleteNote(fileName)
    } catch (error) {
      await alertDialog('删除失败', (error as Error).message)
      return
    }
    if (current.value === fileName) clearCurrent()
    await loadCatalog()
  }

  async function deleteFolder(name: string): Promise<void> {
    const count = files.value.filter((file) => file.folder === name).length
    const ok = await confirmDialog({
      title: '删除文件夹',
      body: `确定删除文件夹「${name}」及其内 ${count} 篇笔记？笔记和对应向量都会删除，无法恢复。`,
    })
    if (!ok) return
    try {
      await api.deleteFolder(name)
    } catch (error) {
      await alertDialog('删除失败', (error as Error).message)
      return
    }
    if (current.value && parentFolder(current.value) === name) clearCurrent()
    if (anchor.value?.kind === 'folder' && anchor.value.id === name) anchor.value = null
    await loadCatalog()
  }

  function clearCurrent(): void {
    current.value = null
    applyContent('')
  }

  /**
   * 别处（引用面板／草稿审批）写了同一篇笔记之后的同步：
   * 本页打开着它且没有未保存编辑就换上新正文；有未保存编辑则保留并提示重新核对。
   */
  async function syncAfterExternalWrite(fileName: string, newContent: string): Promise<void> {
    await loadCatalog()
    if (current.value !== fileName) return
    if (dirty.value) {
      conflictHint.value = `「${basename(fileName)}」已在别处更新，请核对后再保存。`
      return
    }
    applyContent(newContent)
  }

  async function refreshAfterExternalChange(): Promise<void> {
    await loadCatalog()
  }

  /** 离开 Library 前的确认；只丢掉本页这份缓冲。 */
  async function confirmDiscard(body: string): Promise<boolean> {
    if (!dirty.value) return true
    return confirmDialog({ title: '未保存修改', body, danger: false })
  }

  function discardEdits(): void {
    dirty.value = false
    content.value = ''
    conflictHint.value = ''
  }

  function markDirty(text: string): void {
    content.value = text
    dirty.value = true
  }

  return {
    files,
    folders,
    current,
    content,
    dirty,
    collapsed,
    anchor,
    indexing,
    conflictHint,
    currentMeta,
    currentIndexed,
    currentIndexing,
    tree,
    targetFolder,
    canEdit,
    DRAG_THRESHOLD_PX,
    isCollapsed,
    toggleCollapsed,
    selectFolder,
    loadCatalog,
    openDocument,
    saveDocument,
    indexDocument,
    createFolder,
    createNote,
    moveNote,
    renameNote,
    renameFolder,
    deleteNote,
    deleteFolder,
    syncAfterExternalWrite,
    refreshAfterExternalChange,
    confirmDiscard,
    discardEdits,
    markDirty,
  }
})
