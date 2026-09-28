<script setup lang="ts">
import { nextTick, ref } from 'vue'

import { useModelsStore } from '@/features/models/store'
import { useChatStore } from './store'

const chat = useChatStore()
const models = useModelsStore()

const text = ref('')
const box = ref<HTMLTextAreaElement | null>(null)

/** 发送按钮的禁用状态 = 空输入 或 维护窗口，两者都不能被对方覆盖。 */
const sendDisabled = () => !models.canSend || text.value.trim().length === 0

function resize(): void {
  const el = box.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

async function restoreIfEmpty(question: string): Promise<void> {
  // 只在输入框仍为空时恢复，避免覆盖用户随后打的新字。
  if (text.value.trim()) return
  text.value = question
  await nextTick()
  resize()
}

async function send(): Promise<void> {
  const question = text.value.trim()
  if (!question) return
  if (chat.streaming) return
  text.value = ''
  await nextTick()
  resize()
  const outcome = await chat.send(question)
  if (outcome === 'failed' || outcome === 'refused') await restoreIfEmpty(question)
  else await nextTick()
  box.value?.focus()
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}
</script>

<template>
  <div class="input-area">
    <div class="input-inner">
      <textarea
        ref="box"
        v-model="text"
        rows="1"
        placeholder="输入你的问题…"
        aria-label="输入你的问题"
        @input="resize"
        @keydown="onKeydown"
      ></textarea>
      <button
        type="button"
        class="btn-send"
        aria-label="发送"
        :disabled="sendDisabled()"
        @click="send"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="12" y1="19" x2="12" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </svg>
      </button>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.input-area {
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: var(--space-4) var(--space-5);
}

.input-inner {
  max-width: calc((100% + 768px) / 2);
  margin: 0 auto;
  display: flex;
  gap: 10px;
  align-items: flex-end;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  transition: border-color 0.15s;
}

.input-inner:focus-within {
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

textarea {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  min-height: 24px;
  max-height: 200px;
  padding: 4px 0;
  color: var(--text);
}

.btn-send {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.btn-send:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
