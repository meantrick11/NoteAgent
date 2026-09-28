<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

import { confirmDialog } from '@/shared/ui/confirm'
import { basename, useNotesStore } from './store'
import IndexChip from './IndexChip.vue'
import type { NoteFile } from '@/shared/api/types'

/**
 * 笔记目录树：一级目录 + 根目录笔记，支持展开折叠、菜单（重命名／删除）
 * 与拖拽移动。拖拽用鼠标事件 + elementFromPoint 判定落点，与旧页面一致，
 * 因此拖到目录组、拖到某一行、拖回根目录三种落点都要认。
 */
const notes = useNotesStore()

const menuKind = ref<'note' | 'folder' | null>(null)
const menuId = ref('')
const menuStyle = ref<Record<string, string>>({})
const dropTarget = ref<string | null>(null)
const dragging = ref(false)

let drag: { fileName: string; x: number; y: number; active: boolean } | null = null
let suppressClick = false

function closeMenu(): void {
  menuKind.value = null
  menuId.value = ''
}

function openMenu(kind: 'note' | 'folder', id: string, anchor: HTMLElement): void {
  if (menuKind.value === kind && menuId.value === id) {
    closeMenu()
    return
  }
  menuKind.value = kind
  menuId.value = id
  void nextTick(() => {
    const rect = anchor.getBoundingClientRect()
    const width = 120
    const height = 76
    let left = rect.right - width
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8))
    let top = rect.bottom + 4
    if (top + height > window.innerHeight - 4) top = rect.top - height - 4
    menuStyle.value = { left: `${left}px`, top: `${top}px` }
  })
}

function onRename(): void {
  const kind = menuKind.value
  const id = menuId.value
  closeMenu()
  if (kind === 'note') void notes.renameNote(id)
  if (kind === 'folder') void notes.renameFolder(id)
}

function onDelete(): void {
  const kind = menuKind.value
  const id = menuId.value
  closeMenu()
  if (kind === 'note') void notes.deleteNote(id)
  if (kind === 'folder') void notes.deleteFolder(id)
}

async function onNoteClick(file: NoteFile): Promise<void> {
  if (suppressClick) return
  await notes.openDocument(file.file_name)
}

// ---------- 拖拽移动 ----------

/** 落点：目录组 → 该目录；根目录下的行 → 根；树空白区 → 根；树外 → 放弃。 */
function dropFolderFromPoint(x: number, y: number): string | null {
  const el = document.elementFromPoint(x, y)
  if (!el) return null
  const group = el.closest<HTMLElement>('[data-folder-group]')
  if (group) return group.dataset.folderGroup ?? ''
  const row = el.closest<HTMLElement>('[data-drop-folder]')
  if (row) return row.dataset.dropFolder ?? ''
  if (el.closest('[data-notes-tree]')) return ''
  return null
}

function onRowMouseDown(file: NoteFile, event: MouseEvent): void {
  if (event.button !== 0) return
  drag = { fileName: file.file_name, x: event.clientX, y: event.clientY, active: false }
}

function onTreeMouseMove(event: MouseEvent): void {
  if (!drag) return
  const dist = Math.hypot(event.clientX - drag.x, event.clientY - drag.y)
  if (!drag.active && dist > notes.DRAG_THRESHOLD_PX) {
    drag.active = true
    dragging.value = true
    suppressClick = true
  }
  if (!drag.active) return
  dropTarget.value = dropFolderFromPoint(event.clientX, event.clientY)
}

async function onTreeMouseUp(event: MouseEvent): Promise<void> {
  const current = drag
  drag = null
  dragging.value = false
  const folder = dropTargetFromRelease(event)
  dropTarget.value = null
  setTimeout(() => {
    suppressClick = false
  }, 0)
  if (!current || !current.active || folder === null) return

  const base = basename(current.fileName)
  const dest = folder ? `${folder}/${base}` : base
  if (dest === current.fileName) return
  const body = folder ? `将「${base}」移动到「${folder}」？` : `将「${base}」移回根目录？`
  // 移动是写操作，先按既有约定问一次再发请求。
  const ok = await confirmDialog({ title: '移动笔记', body, danger: false })
  if (!ok) return
  await notes.moveNote(current.fileName, dest)
}

function dropTargetFromRelease(event: MouseEvent): string | null {
  const el = document.elementFromPoint(event.clientX, event.clientY)
  if (!el) return null
  const group = el.closest<HTMLElement>('[data-folder-group]')
  if (group) return group.dataset.folderGroup ?? ''
  const row = el.closest<HTMLElement>('[data-drop-folder]')
  if (row) return row.dataset.dropFolder ?? ''
  if (el.closest('[data-notes-tree]')) return ''
  return null
}

// 监听挂在 document 上：指针移出侧栏时仍要继续跟踪，松手才算落地。
onMounted(() => {
  document.addEventListener('mousemove', onTreeMouseMove)
  document.addEventListener('mouseup', onTreeMouseUp)
})

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onTreeMouseMove)
  document.removeEventListener('mouseup', onTreeMouseUp)
})
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-header">笔记</div>
    <div
      class="sidebar-body"
      data-notes-tree
      :class="{ dragging }"
    >
      <div
        v-for="group in notes.tree.groups"
        :key="group.folder"
        class="folder-group"
        :class="{ 'drop-target': dropTarget === group.folder }"
        :data-folder-group="group.folder"
      >
        <div
          class="docs-row folder-row"
          :class="{ selected: notes.anchor?.kind === 'folder' && notes.anchor.id === group.folder }"
          :data-drop-folder="group.folder"
          @click="notes.selectFolder(group.folder)"
        >
          <span
            class="chevron"
            :class="{ collapsed: notes.isCollapsed(group.folder) }"
            :role="'button'"
            tabindex="0"
            aria-label="展开或折叠"
            @click.stop="notes.toggleCollapsed(group.folder)"
            @keydown.enter.stop="notes.toggleCollapsed(group.folder)"
            >▼</span
          >
          <span class="docs-icon" aria-hidden="true">📁</span>
          <span class="docs-name" :title="group.folder">{{ group.folder }}</span>
          <span class="docs-count">{{ group.files.length }}</span>
          <button
            type="button"
            class="docs-more"
            aria-label="更多"
            @mousedown.stop
            @click.stop="openMenu('folder', group.folder, $event.currentTarget as HTMLElement)"
          >
            …
          </button>
        </div>

        <template v-if="!notes.isCollapsed(group.folder)">
          <div
            v-for="file in group.files"
            :key="file.file_name"
            class="docs-row child"
            :class="{
              active: notes.current === file.file_name,
              'drop-target': dropTarget === group.folder,
            }"
            :data-drop-folder="group.folder"
            @mousedown="onRowMouseDown(file, $event)"
            @click="onNoteClick(file)"
          >
            <span class="docs-icon" aria-hidden="true">📄</span>
            <span class="docs-name" :title="file.file_name">{{ basename(file.file_name) }}</span>
            <IndexChip :indexed="file.indexed" :file-name="file.file_name" />
            <button
              type="button"
              class="docs-more"
              aria-label="更多"
              @mousedown.stop
              @click.stop="openMenu('note', file.file_name, $event.currentTarget as HTMLElement)"
            >
              …
            </button>
          </div>
        </template>
      </div>

      <div
        v-for="file in notes.tree.rootFiles"
        :key="file.file_name"
        class="docs-row"
        :class="{
          active: notes.current === file.file_name,
          'drop-target': dropTarget === '' && dragging,
        }"
        data-drop-folder=""
        @mousedown="onRowMouseDown(file, $event)"
        @click="onNoteClick(file)"
      >
        <span class="docs-icon" aria-hidden="true">📄</span>
        <span class="docs-name" :title="file.file_name">{{ basename(file.file_name) }}</span>
        <IndexChip :indexed="file.indexed" :file-name="file.file_name" />
        <button
          type="button"
          class="docs-more"
          aria-label="更多"
          @mousedown.stop
          @click.stop="openMenu('note', file.file_name, $event.currentTarget as HTMLElement)"
        >
          …
        </button>
      </div>
    </div>

    <div class="sidebar-footer">
      <button type="button" class="btn-new" @click="notes.createNote()">＋ 新建笔记</button>
      <button type="button" class="btn-new" @click="notes.createFolder()">＋ 新建文件夹</button>
    </div>

    <div
      v-if="menuKind"
      class="docs-tree-menu"
      role="menu"
      :style="menuStyle"
      @click.stop
    >
      <button type="button" role="menuitem" class="docs-menu-item" @click="onRename">
        重命名
      </button>
      <button type="button" role="menuitem" class="docs-menu-item" @click="onDelete">删除</button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 300px;
  background: var(--surface);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: 12px 16px;
  font-weight: 700;
  font-size: 15px;
  border-bottom: 1px solid var(--border);
  min-height: var(--header-height);
  display: flex;
  align-items: center;
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-3);
}

.sidebar-footer {
  padding: var(--space-3);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.btn-new {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  cursor: pointer;
  font-family: inherit;
  font-size: 14px;
  color: var(--text);
}

.btn-new:hover {
  background: var(--bg);
}

.docs-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  position: relative;
  border-left: 3px solid transparent;
  user-select: none;
}

.docs-row:hover,
.docs-row.selected {
  background: var(--bg);
}

.docs-row.active {
  background: var(--bg);
  border-left-color: var(--accent);
}

.docs-row.child {
  padding-left: 28px;
}

.docs-row.drop-target,
.folder-group.drop-target {
  background: #e5e7eb;
}

.docs-row .docs-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.docs-icon,
.chevron {
  width: 14px;
  flex-shrink: 0;
  color: var(--text-secondary);
  font-size: 11px;
}

.chevron {
  transition: transform 0.15s;
  cursor: pointer;
}

.chevron.collapsed {
  transform: rotate(-90deg);
}

.docs-count {
  font-size: 11px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

.docs-more {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 6px;
  flex-shrink: 0;
  font-size: 14px;
  line-height: 1;
}

.docs-more:hover {
  background: var(--border);
  color: var(--text);
}

.docs-tree-menu {
  position: fixed;
  min-width: 120px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: var(--space-1);
  box-shadow: var(--shadow-popover);
  z-index: 100;
}

.docs-menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  font-size: 13px;
  font-family: inherit;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 6px;
  color: var(--text);
}

.docs-menu-item:hover {
  background: var(--bg);
}
</style>
