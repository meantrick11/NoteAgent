<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ value: string; busy?: boolean }>()
const emit = defineEmits<{
  (event: 'update:value', value: string): void
  (event: 'submit'): void
  (event: 'cancel'): void
}>()

// IME 组合输入期间绝不提交；Enter 只换行。
const composing = ref(false)
const input = ref<HTMLTextAreaElement | null>(null)
let observer: ResizeObserver | undefined
let previousWidth = -1

function resizeToContent(): void {
  const element = input.value
  if (!element) return
  element.style.height = '0px'
  element.style.height = `${element.scrollHeight}px`
}

watch(() => props.value, resizeToContent, { flush: 'post' })
onMounted(() => {
  resizeToContent()
  observer = new ResizeObserver(([entry]) => {
    if (!entry || entry.contentRect.width === previousWidth) return
    previousWidth = entry.contentRect.width
    resizeToContent()
  })
  if (input.value) observer.observe(input.value)
})
onBeforeUnmount(() => observer?.disconnect())

function onInput(event: Event): void {
  emit('update:value', (event.target as HTMLTextAreaElement).value)
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    emit('cancel')
    return
  }
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
    event.preventDefault()
    if (!composing.value) emit('submit')
  }
}
</script>

<template>
  <div class="msg-edit">
    <textarea
      ref="input"
      class="msg-edit-input"
      :value="props.value"
      :disabled="props.busy"
      aria-label="编辑这条消息"
      rows="1"
      @input="onInput"
      @keydown="onKeydown"
      @compositionstart="composing = true"
      @compositionend="composing = false"
    ></textarea>
    <div class="msg-edit-actions">
      <button type="button" class="btn primary" :disabled="props.busy" @click="$emit('submit')">
        重新生成
      </button>
      <button type="button" class="btn" :disabled="props.busy" @click="$emit('cancel')">
        取消
      </button>
      <span class="hint">Enter 换行 · Ctrl/⌘+Enter 提交 · Esc 取消</span>
    </div>
  </div>
</template>

<style scoped>
.msg-edit {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.msg-edit-input {
  width: 100%;
  box-sizing: border-box;
  resize: none;
  overflow: hidden;
  font: inherit;
  line-height: inherit;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--text);
}

.msg-edit-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.btn {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface);
  cursor: pointer;
}

.btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.hint {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
