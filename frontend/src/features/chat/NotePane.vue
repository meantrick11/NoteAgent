<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import DraftActions from './DraftActions.vue'
import { useChatStore } from './store'

const chat = useChatStore()

const textEl = ref<HTMLTextAreaElement | null>(null)
const panel = computed(() => chat.panel)
const inDraftMode = computed(() => panel.value.mode === 'draft')

/** 未保存标记只在用户真的改了正文时出现。 */
function onInput(): void {
  chat.patchActivePanel({ text: textEl.value?.value ?? '', dirty: true })
}

/** 选区与滚动位置进快照，切会话再回来能落回原处。 */
function rememberSelection(): void {
  const el = textEl.value
  if (!el) return
  chat.patchActivePanel({
    selStart: el.selectionStart,
    selEnd: el.selectionEnd,
    scrollTop: el.scrollTop,
  })
}

/** 引用命中的位置按行高换算滚动量，让匹配片段进入视野。 */
function scrollToOffset(offset: number): void {
  const el = textEl.value
  if (!el) return
  const lines = el.value.slice(0, offset).split('\n').length
  const lineHeight = Number.parseFloat(getComputedStyle(el).lineHeight) || 22
  el.scrollTop = Math.max(0, (lines - 4) * lineHeight)
}

watch(
  () => [panel.value.fileName, panel.value.text, panel.value.selStart, panel.value.selEnd] as const,
  async () => {
    const el = textEl.value
    if (!el) return
    await nextTick()
    if (el.value !== panel.value.text) el.value = panel.value.text
    const { selStart, selEnd } = panel.value
    if (selEnd <= selStart) {
      el.scrollTop = panel.value.scrollTop
      return
    }
    try {
      el.setSelectionRange(selStart, selEnd)
    } catch {
      // 未聚焦时某些浏览器不允许设置选区，忽略。
    }
    scrollToOffset(selStart)
    el.focus()
  },
)

function save(): void {
  if (inDraftMode.value) void chat.saveDraftContent()
  else void chat.saveCitation()
}

function onDocumentKeydown(event: KeyboardEvent): void {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 's') return
  if (panel.value.hidden || !panel.value.fileName) return
  event.preventDefault()
  save()
}

onMounted(() => document.addEventListener('keydown', onDocumentKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onDocumentKeydown))
</script>

<template>
  <aside
    v-show="!panel.hidden"
    class="cite-pane"
    :data-mode="panel.mode"
    aria-label="引用与草稿面板"
  >
    <div class="cite-pane-head">
      <span class="cite-pane-badge">{{ inDraftMode ? '待审批草稿' : '引用' }}</span>
      <span class="cite-pane-title" :title="chat.panelTitle">{{ chat.panelTitle }}</span>
      <button
        type="button"
        class="cite-pane-save"
        :disabled="chat.panelSaveDisabled"
        @click="save"
      >
        {{ chat.panelSaveLabel }}
      </button>
      <button type="button" class="cite-pane-close" @click="chat.closePanel()">关闭</button>
    </div>
    <p v-if="chat.panelHint" class="cite-pane-hint">{{ chat.panelHint }}</p>
    <textarea
      ref="textEl"
      class="cite-pane-text"
      aria-label="面板正文"
      :value="panel.text"
      :disabled="panel.textDisabled"
      @input="onInput"
      @select="rememberSelection"
      @scroll="rememberSelection"
    ></textarea>
    <DraftActions v-if="inDraftMode" />
  </aside>
</template>

<style scoped>
.cite-pane {
  width: var(--note-pane-width);
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  background: var(--surface);
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cite-pane-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.cite-pane-badge {
  flex-shrink: 0;
  font-size: 11px;
  line-height: 1.6;
  padding: 1px 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-secondary);
  background: var(--bg);
}

.cite-pane[data-mode='draft'] .cite-pane-badge {
  border-color: var(--accent);
  color: var(--accent);
}

.cite-pane-title {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cite-pane-close {
  border: 1px solid var(--border);
  background: var(--surface);
  border-radius: var(--radius-sm);
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
  color: var(--text);
}

.cite-pane-save {
  border: 1px solid var(--accent);
  background: var(--accent);
  color: #fff;
  border-radius: var(--radius-sm);
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
  font-family: inherit;
}

.cite-pane-save:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.cite-pane-hint {
  margin: 0;
  padding: 8px 12px 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.cite-pane-text {
  flex: 1;
  min-height: 0;
  width: 100%;
  border: none;
  resize: none;
  padding: 12px 16px 24px;
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.7;
  outline: none;
  background: var(--surface);
  color: var(--text);
}
</style>
