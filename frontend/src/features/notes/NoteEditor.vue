<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import MarkdownPreview from '@/shared/ui/MarkdownPreview.vue'
import { basename, useNotesStore } from './store'
import IndexChip from './IndexChip.vue'

/**
 * Markdown 编辑与预览。两侧滚动按比例同步，用一把锁避免互相触发；
 * 保存失败保留正文与未保存标记，并把后端的原话显示出来。
 */
const notes = useNotesStore()

const textEl = ref<HTMLTextAreaElement | null>(null)
const preview = ref<InstanceType<typeof MarkdownPreview> | null>(null)
let scrollLock = false

const title = computed(() => (notes.current ? basename(notes.current) : '选择一篇笔记'))
const mtimeText = computed(() => {
  const stamp = notes.currentMeta?.mtime
  return stamp ? new Date(stamp * 1000).toLocaleString() : ''
})

function syncScroll(from: HTMLElement | null | undefined, to: HTMLElement | null | undefined): void {
  if (scrollLock || !from || !to) return
  const fromMax = from.scrollHeight - from.clientHeight
  const toMax = to.scrollHeight - to.clientHeight
  if (fromMax <= 0 || toMax <= 0) return
  scrollLock = true
  to.scrollTop = (from.scrollTop / fromMax) * toMax
  requestAnimationFrame(() => {
    scrollLock = false
  })
}

function onEditorScroll(): void {
  syncScroll(textEl.value, preview.value?.root ?? null)
}

function onPreviewScroll(): void {
  syncScroll(preview.value?.root ?? null, textEl.value)
}

function onInput(): void {
  notes.markDirty(textEl.value?.value ?? '')
}

function onKeydown(event: KeyboardEvent): void {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 's') return
  event.preventDefault()
  void notes.saveDocument()
}

onMounted(() => {
  // 预览区的滚动要按比例回写编辑器，所以监听挂在它的根元素上。
  nextTick(() => {
    preview.value?.root?.addEventListener('scroll', onPreviewScroll)
  })
  document.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  preview.value?.root?.removeEventListener('scroll', onPreviewScroll)
  document.removeEventListener('keydown', onKeydown)
})

// 打开另一篇时把编辑区滚回顶部，避免沿用上一篇的滚动位置。
watch(
  () => notes.current,
  async () => {
    await nextTick()
    if (textEl.value) textEl.value.scrollTop = 0
    const root = preview.value?.root
    if (root) root.scrollTop = 0
  },
)
</script>

<template>
  <div class="docs-main">
    <div class="main-header">
      <div class="header-inner">
        <span class="docs-title" :title="notes.current ?? ''">{{ title }}</span>
        <span v-if="notes.dirty" class="dirty-dot" aria-label="有未保存修改"></span>
        <IndexChip
          v-if="notes.current"
          :indexed="notes.currentIndexed"
          :file-name="notes.current"
        />
        <span class="docs-mtime">{{ mtimeText }}</span>
      </div>
    </div>

    <p v-if="notes.conflictHint" class="conflict-hint">{{ notes.conflictHint }}</p>

    <div class="docs-toolbar">
      <button
        type="button"
        class="btn btn-primary"
        :disabled="!notes.canEdit"
        @click="notes.saveDocument()"
      >
        保存
      </button>
      <button
        type="button"
        class="btn"
        :disabled="!notes.canEdit || !notes.current"
        @click="notes.current && notes.deleteNote(notes.current)"
      >
        删除
      </button>
    </div>

    <div class="docs-editor">
      <textarea
        ref="textEl"
        :value="notes.content"
        :disabled="!notes.canEdit"
        placeholder="打开左侧笔记后可在此编辑 Markdown"
        aria-label="Markdown 正文"
        @input="onInput"
        @scroll="onEditorScroll"
      ></textarea>
      <MarkdownPreview ref="preview" class="docs-preview" :text="notes.content" />
    </div>
  </div>
</template>

<style scoped>
.docs-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.main-header {
  min-height: var(--header-height);
  padding: 8px var(--space-5);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  display: flex;
  align-items: center;
}

.header-inner {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  width: 100%;
}

.docs-title {
  font-size: 16px;
  font-weight: 650;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dirty-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}

.docs-mtime {
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: auto;
  flex-shrink: 0;
}

.conflict-hint {
  margin: 0;
  padding: 8px var(--space-5);
  font-size: 12px;
  color: var(--warn-text);
  background: var(--warn-bg);
}

.docs-toolbar {
  display: flex;
  gap: var(--space-2);
  align-items: center;
  padding: 8px var(--space-5);
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  flex-wrap: wrap;
}

.docs-editor {
  flex: 1;
  display: flex;
  min-height: 0;
}

.docs-editor textarea {
  flex: 1;
  min-width: 0;
  border: none;
  resize: none;
  padding: var(--space-4);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  outline: none;
  background: var(--surface);
  color: var(--text);
  overflow-y: auto;
}

.docs-preview {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: var(--space-4) 20px;
  border-left: 1px solid var(--border);
  font-size: 14px;
  line-height: 1.7;
  background: var(--bg);
}
</style>
