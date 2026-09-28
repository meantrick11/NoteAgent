<script setup lang="ts">
import { nextTick, ref } from 'vue'

import { confirmDialog } from '@/shared/ui/confirm'
import type { Conversation } from '@/shared/api/types'
import { useChatStore } from './store'

const store = useChatStore()

const menuId = ref<string | null>(null)
const menuStyle = ref<Record<string, string>>({})
const renamingId = ref<string | null>(null)
const renameText = ref('')
const bodyEl = ref<HTMLElement | null>(null)
let renameCommitted = false

function closeMenu(): void {
  menuId.value = null
}

function onItemClick(conversation: Conversation): void {
  if (renamingId.value === conversation.id) return
  void store.openConversation(conversation.id)
}

function focusRenameInput(): void {
  // renamingId 一次只有一个，所以直接查当前那一行里的输入框。
  const input = bodyEl.value?.querySelector<HTMLInputElement>('.conversation-rename-input')
  input?.focus()
  input?.select()
}

function openMenu(conversation: Conversation, anchor: HTMLElement): void {
  if (menuId.value === conversation.id) {
    closeMenu()
    return
  }
  menuId.value = conversation.id
  // 菜单贴按钮右缘，被视口压住时上翻；与旧页面的定位规则一致。
  nextTick(() => {
    const rect = anchor.getBoundingClientRect()
    const width = 140
    const height = 76
    let left = rect.right - width
    left = Math.max(8, Math.min(left, window.innerWidth - width - 8))
    let top = rect.bottom + 4
    if (top + height > window.innerHeight - 4) top = rect.top - height - 4
    menuStyle.value = { left: `${left}px`, top: `${top}px` }
  })
}

async function startRename(conversation: Conversation): Promise<void> {
  closeMenu()
  renamingId.value = conversation.id
  renameText.value = conversation.title
  renameCommitted = false
  await nextTick()
  focusRenameInput()
}

async function commitRename(): Promise<void> {
  if (renameCommitted) return
  renameCommitted = true
  const id = renamingId.value
  const value = renameText.value.trim()
  renamingId.value = null
  if (!id || !value) return
  await store.renameConversation(id, value)
}

function cancelRename(): void {
  renameCommitted = true
  renamingId.value = null
}

async function confirmDelete(conversation: Conversation): Promise<void> {
  closeMenu()
  const ok = await confirmDialog({
    title: '删除对话',
    body: `确定删除「${conversation.title}」？删除后无法恢复。`,
  })
  if (!ok) return
  await store.removeConversation(conversation.id)
}

async function newChat(): Promise<void> {
  if (!(await store.confirmPanelDiscard(true))) return
  store.newChat()
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-header">会话</div>
    <div ref="bodyEl" class="sidebar-body" @scroll="closeMenu">
      <div
        v-for="conversation in store.conversations"
        :key="conversation.id"
        class="conversation-item"
        :class="{ active: conversation.id === store.currentId }"
        @click="onItemClick(conversation)"
      >
        <input
          v-if="renamingId === conversation.id"
          v-model="renameText"
          class="conversation-rename-input"
          @click.stop
          @keydown.enter.prevent="commitRename()"
          @keydown.esc.prevent="cancelRename()"
          @blur="commitRename()"
        />
        <template v-else>
          <span class="conversation-title" :title="conversation.title">
            {{ conversation.title }}
          </span>
          <button
            type="button"
            class="conversation-more"
            aria-label="更多"
            aria-haspopup="menu"
            :aria-expanded="menuId === conversation.id"
            @click.stop="openMenu(conversation, $event.currentTarget as HTMLElement)"
          >
            …
          </button>
        </template>
      </div>
      <p v-if="!store.conversations.length" class="placeholder">暂无对话</p>
    </div>
    <div class="sidebar-footer">
      <button type="button" class="btn-new-chat" @click="newChat">
        <span aria-hidden="true">＋</span> 新对话
      </button>
    </div>

    <div
      v-if="menuId"
      class="conversation-menu"
      role="menu"
      :style="menuStyle"
      @click.stop
    >
      <button
        type="button"
        role="menuitem"
        class="conversation-menu-item"
        @click="startRename(store.conversations.find((item) => item.id === menuId)!)"
      >
        重命名
      </button>
      <button
        type="button"
        role="menuitem"
        class="conversation-menu-item"
        @click="confirmDelete(store.conversations.find((item) => item.id === menuId)!)"
      >
        删除
      </button>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: var(--sidebar-width);
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
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--header-height);
}

.sidebar-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.placeholder {
  color: var(--text-secondary);
  font-size: 13px;
  text-align: center;
  margin-top: 40px;
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--border);
}

.btn-new-chat {
  width: 100%;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  cursor: pointer;
  font-family: inherit;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: background 0.15s;
}

.btn-new-chat:hover {
  background: var(--bg);
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 10px 12px;
  cursor: pointer;
  font-size: 14px;
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-1);
}

.conversation-item:hover,
.conversation-item.active {
  background: var(--bg);
}

.conversation-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-more {
  flex-shrink: 0;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  border-radius: 6px;
}

.conversation-more:hover {
  color: var(--text);
  background: var(--border);
}

.conversation-rename-input {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  padding: 4px 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  outline: none;
  font-family: inherit;
}

.conversation-rename-input:focus {
  border-color: var(--accent);
}

.conversation-menu {
  position: fixed;
  width: 140px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: var(--space-1);
  box-shadow: var(--shadow-popover);
  z-index: 100;
}

.conversation-menu-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 8px 10px;
  font-size: 14px;
  font-family: inherit;
  border: none;
  background: transparent;
  cursor: pointer;
  border-radius: 6px;
  color: var(--text);
}

.conversation-menu-item:hover {
  background: var(--bg);
}
</style>
