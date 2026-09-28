<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { useModelsStore } from '@/features/models/store'
import { draftApproveLabel, draftAsk, draftOverrideAvailable, useChatStore } from './store'

const chat = useChatStore()
const models = useModelsStore()

/** null 表示未选择覆盖方式；"append" / "create" 时只渲染对应的那一个表单。 */
const overrideMode = ref<'append' | 'create' | null>(null)
const menuOpen = ref(false)
const menuTrigger = ref<HTMLButtonElement | null>(null)
const appendSelect = ref<HTMLSelectElement | null>(null)
const nameInput = ref<HTMLInputElement | null>(null)

const draft = computed(() => chat.panel.draft)
const busy = computed(() => chat.panel.busy)
const showOverride = computed(() => draftOverrideAvailable(draft.value))
/** 维护窗口里不允许审批写入，后端也会拒。 */
const canWrite = computed(() => models.canSend)

function closeMenu(): void {
  menuOpen.value = false
}

/** 选择一种覆盖方式：关掉菜单，只渲染该方式需要的表单。 */
function pickOverride(mode: 'append' | 'create'): void {
  overrideMode.value = mode
  closeMenu()
}

function onDocumentKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !menuOpen.value) return
  event.preventDefault()
  closeMenu()
  menuTrigger.value?.focus()
}

function onDocumentClick(event: MouseEvent): void {
  if (!menuOpen.value) return
  const target = event.target as HTMLElement
  if (target.closest('.draft-pane-menu') || target.closest('[data-act="more"]')) return
  closeMenu()
}

// 菜单打开时才挂全局监听，避免每处都留一个常驻 document 处理器。
watch(menuOpen, (open) => {
  if (typeof document === 'undefined') return
  if (open) {
    document.addEventListener('keydown', onDocumentKeydown)
    document.addEventListener('click', onDocumentClick)
  } else {
    document.removeEventListener('keydown', onDocumentKeydown)
    document.removeEventListener('click', onDocumentClick)
  }
})

onBeforeUnmount(() => {
  if (typeof document === 'undefined') return
  document.removeEventListener('keydown', onDocumentKeydown)
  document.removeEventListener('click', onDocumentClick)
})

// 换成 replace／delete 时清掉可能残留的覆盖选择。
watch(showOverride, (available) => {
  if (!available) overrideMode.value = null
  else closeMenu()
})

watch(overrideMode, async (mode) => {
  if (!mode) return
  await new Promise((resolve) => requestAnimationFrame(resolve))
  if (mode === 'append') appendSelect.value?.focus()
  else nameInput.value?.focus()
})

function approve(): void {
  if (busy.value || !canWrite.value) return
  void chat.reviewDraft({ action: 'approve' })
}

function reject(): void {
  if (busy.value || !canWrite.value) return
  void chat.reviewDraft({ action: 'reject' })
}

function submitOverride(): void {
  if (busy.value || !canWrite.value) return
  if (overrideMode.value === 'append') {
    const target = appendSelect.value?.value
    if (!target) return
    void chat.reviewDraft({ action: 'override', write_action: 'append', file_name: target })
    return
  }
  const current = draft.value
  const name = nameInput.value?.value.trim() || current?.file_name
  if (!name) return
  void chat.reviewDraft({ action: 'override', write_action: 'create', file_name: name })
}
</script>

<template>
  <div v-if="draft" class="draft-pane-actions">
    <p class="draft-pane-ask">{{ draftAsk(draft) }}</p>
    <div class="draft-pane-buttons">
      <button
        type="button"
        class="btn btn-primary"
        data-act="approve"
        :disabled="busy || !canWrite"
        @click="approve"
      >
        {{ draftApproveLabel(draft.action) }}
      </button>
      <button
        v-if="showOverride"
        ref="menuTrigger"
        type="button"
        class="btn"
        data-act="more"
        aria-haspopup="menu"
        :aria-expanded="menuOpen"
        :disabled="busy || !canWrite"
        @click="menuOpen ? closeMenu() : (menuOpen = true)"
      >
        更多操作 ▾
      </button>
      <button
        type="button"
        class="btn"
        data-act="reject"
        :disabled="busy || !canWrite"
        @click="reject"
      >
        拒绝
      </button>
    </div>

    <div v-if="menuOpen" class="draft-pane-menu" role="menu" aria-label="更多草稿操作">
      <button type="button" role="menuitem" data-pick="append" @click="pickOverride('append')">
        追加到笔记
      </button>
      <button type="button" role="menuitem" data-pick="create" @click="pickOverride('create')">
        新建笔记
      </button>
    </div>

    <div v-if="overrideMode" class="draft-pane-form">
      <template v-if="overrideMode === 'append'">
        <label for="cite-pane-append-target">追加到笔记</label>
        <select id="cite-pane-append-target" ref="appendSelect" data-role="append-target">
          <option v-for="name in draft.existing_files ?? []" :key="name" :value="name">
            {{ name }}
          </option>
        </select>
        <button type="button" data-act="submit-append" :disabled="busy || !canWrite" @click="submitOverride">
          追加到所选笔记
        </button>
      </template>
      <template v-else>
        <label for="cite-pane-new-name">新建笔记</label>
        <input
          id="cite-pane-new-name"
          ref="nameInput"
          data-role="new-name"
          placeholder="新文件名.md"
          :value="draft.action === 'create' ? draft.file_name : ''"
        />
        <button type="button" data-act="submit-create" :disabled="busy || !canWrite" @click="submitOverride">
          新建这篇笔记
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped>
.draft-pane-actions {
  flex-shrink: 0;
  border-top: 1px solid var(--border);
  padding: 10px 12px 12px;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.draft-pane-ask {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
}

.draft-pane-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
}

.draft-pane-buttons button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.draft-pane-menu {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg);
}

.draft-pane-menu button {
  text-align: left;
  font-size: 13px;
  font-family: inherit;
  padding: 6px 8px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  color: var(--text);
}

.draft-pane-menu button:hover,
.draft-pane-menu button:focus-visible {
  background: var(--surface);
}

.draft-pane-form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  align-items: center;
  padding-top: 2px;
}

.draft-pane-form label {
  font-size: 12px;
  color: var(--text-secondary);
}

.draft-pane-form button,
.draft-pane-form select,
.draft-pane-form input {
  font-size: 13px;
  font-family: inherit;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
}

.draft-pane-form button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
