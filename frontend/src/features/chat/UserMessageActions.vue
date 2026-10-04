<script setup lang="ts">
import { ref } from 'vue'

import { copyMessageText } from './clipboard'
import { editUnavailableMessage, type ChatMessage } from './store'

const props = defineProps<{ message: ChatMessage }>()

defineEmits<{ (event: 'edit', message: ChatMessage): void }>()

const copyState = ref<'idle' | 'ok' | 'failed'>('idle')

/** 复制原文（原始 Markdown 与换行），失败要给出可见反馈。 */
async function copy(): Promise<void> {
  const ok = await copyMessageText(props.message.content ?? '')
  copyState.value = ok ? 'ok' : 'failed'
}

function editReason(): string {
  return editUnavailableMessage(props.message) ?? ''
}
</script>

<template>
  <div class="msg-actions">
    <button
      type="button"
      class="icon-btn"
      aria-label="复制这条消息"
      title="复制"
      @click="copy"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <rect x="5.5" y="2.5" width="8" height="10" rx="1.5" fill="none" stroke="currentColor" />
        <rect x="2.5" y="4.5" width="8" height="10" rx="1.5" fill="none" stroke="currentColor" />
      </svg>
    </button>
    <button
      type="button"
      class="icon-btn"
      aria-label="编辑这条消息"
      :title="message.editable ? '编辑' : editReason()"
      :disabled="!message.editable"
      @click="$emit('edit', message)"
    >
      <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
        <path
          d="M3 13h2.5l7-7L10 3.5l-7 7V13z"
          fill="none"
          stroke="currentColor"
          stroke-linejoin="round"
        />
      </svg>
    </button>
    <span v-if="copyState === 'ok'" class="action-hint" role="status">已复制</span>
    <span v-else-if="copyState === 'failed'" class="action-hint failed" role="status">
      复制失败
    </span>
  </div>
</template>

<style scoped>
.msg-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.icon-btn:hover:not(:disabled) {
  background: var(--accent-soft);
  color: var(--accent);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.action-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.action-hint.failed {
  color: var(--danger, #dc2626);
}
</style>
