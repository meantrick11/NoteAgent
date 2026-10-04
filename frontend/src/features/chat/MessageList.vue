<script setup lang="ts">
import { computed } from 'vue'

import type { Citation } from '@/shared/api/types'
import { citationMap, localizeCitations, renderAssistantHtml } from './citations'
import type { ChatMessage } from './store'
import { useChatStore } from './store'
import MessageEditForm from './MessageEditForm.vue'
import RecoveryConfirmDialog from './RecoveryConfirmDialog.vue'
import ToolTrace from './ToolTrace.vue'
import UserMessageActions from './UserMessageActions.vue'

const props = defineProps<{ messages: ChatMessage[]; welcome: boolean }>()

const emit = defineEmits<{
  (event: 'cite', payload: Citation): void
}>()

const chat = useChatStore()

/**
 * 每条消息都有自己的编号空间，所以引用表要按消息算。
 * 编号必须在渲染前重排，点击时才能用同一个映射找回出处。
 */
const citationTables = computed(() =>
  props.messages.map((message) =>
    message.role === 'assistant'
      ? citationMap(localizeCitations(message.content, message.citations).citations)
      : {},
  ),
)

function bodyHtml(message: ChatMessage): string {
  if (message.role !== 'assistant') return ''
  return renderAssistantHtml(message.content, message.citations)
}

function onBodyClick(message: ChatMessage, index: number, event: MouseEvent): void {
  if (message.role !== 'assistant') return
  const target = (event.target as HTMLElement).closest('.cite-ref')
  if (!target) return
  event.preventDefault()
  const n = Number(target.getAttribute('data-cite'))
  const cite = citationTables.value[index]?.[n]
  if (cite) emit('cite', cite)
}
</script>

<template>
  <div class="chat-inner">
    <div v-if="welcome" class="welcome">
      <h2>今天想学点什么？</h2>
      <p>告诉我你的学习内容，我帮你整理成结构化笔记</p>
    </div>
    <div
      v-for="(message, index) in messages"
      :key="message.key"
      class="msg-row"
      :class="message.role"
    >
      <div class="msg-avatar" aria-hidden="true">{{ message.role === 'user' ? '👤' : '🤖' }}</div>
      <div class="msg-col">
        <ToolTrace
          v-if="message.role === 'assistant'"
          :steps="message.toolSteps"
          :live="message.live"
        />
        <div class="msg-bubble">
          <MessageEditForm
            v-if="message.role === 'user' && chat.editingKey === message.key"
            :value="chat.editingText"
            :busy="chat.recoveryPhase === 'previewing' || chat.recoveryPhase === 'running'"
            @update:value="chat.updateEditingText"
            @submit="chat.submitEdit"
            @cancel="chat.cancelRecovery"
          />
          <!-- 与旧页面一致：助手正文是 Markdown，先把引用标记插进去再解析。 -->
          <div
            v-else-if="message.role === 'assistant'"
            class="msg-body"
            @click="onBodyClick(message, index, $event)"
            v-html="bodyHtml(message)"
          ></div>
          <div v-else class="msg-body">{{ message.content }}</div>
        </div>

        <!-- 编辑态：只允许一条消息同时编辑，提交前必须看到预览。 -->
        <UserMessageActions
          v-if="message.role === 'user' && chat.editingKey !== message.key"
          :message="message"
          @edit="(target) => chat.beginEdit(target)"
        />
      </div>
    </div>

    <RecoveryConfirmDialog
      v-if="(chat.recoveryPreview || chat.recoveryJob) && chat.recoveryPhase !== 'idle' && chat.recoveryPhase !== 'editing'"
      :preview="chat.recoveryPreview"
      :phase="chat.recoveryPhase"
      :error="chat.recoveryError"
      :retryable="chat.recoveryJob?.retryable ?? true"
      @confirm="chat.confirmRecovery"
      @cancel="chat.cancelRecovery"
      @retry="chat.retryRecovery"
    />
  </div>
</template>

<style scoped>
.chat-inner {
  max-width: calc((100% + 768px) / 2);
  margin: 0 auto;
  padding: 0 var(--space-5);
}

.welcome {
  text-align: center;
  margin-top: 80px;
}

.welcome h2 {
  font-size: 22px;
  margin-bottom: var(--space-2);
}

.welcome p {
  color: var(--text-secondary);
  font-size: 14px;
}

.msg-row {
  display: flex;
  margin-bottom: 20px;
  align-items: flex-start;
  width: 100%;
}

.msg-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.msg-bubble {
  flex: 1;
  min-width: 0;
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: 14px;
  line-height: 1.7;
}

.msg-row.user .msg-bubble {
  background: var(--user-bubble);
  border-bottom-right-radius: 4px;
}

.msg-row.user .msg-body {
  white-space: pre-wrap;
  overflow-wrap: break-word;
}

.msg-row.assistant .msg-bubble {
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.msg-avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
  margin: 0 10px;
}

.msg-row.assistant .msg-avatar {
  background: var(--accent-soft);
}

.msg-row.user .msg-avatar {
  background: #dbeafe;
  order: 2;
}

/* Markdown 正文样式：与旧页面保持一致的外观。 */
.msg-body :deep(p) {
  margin: 0 0 var(--space-2);
}

.msg-body :deep(p:last-child) {
  margin-bottom: 0;
}

.msg-body :deep(ul),
.msg-body :deep(ol) {
  padding-left: 20px;
  margin: var(--space-2) 0;
}

.msg-body :deep(li) {
  margin: var(--space-1) 0;
}

.msg-body :deep(h1),
.msg-body :deep(h2),
.msg-body :deep(h3),
.msg-body :deep(h4) {
  margin: 12px 0 6px;
  font-weight: 600;
}

.msg-body :deep(h1) {
  font-size: 18px;
}

.msg-body :deep(h2) {
  font-size: 16px;
}

.msg-body :deep(h3) {
  font-size: 15px;
}

.msg-body :deep(code) {
  background: #f3f4f6;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: var(--font-mono);
}

.msg-body :deep(pre) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 14px 16px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  margin: 10px 0;
  font-size: 13px;
  line-height: 1.55;
}

.msg-body :deep(pre code) {
  background: none;
  padding: 0;
  color: inherit;
  font-size: inherit;
}

.msg-body :deep(blockquote) {
  border-left: 3px solid var(--accent);
  padding-left: 12px;
  color: var(--text-secondary);
  margin: var(--space-2) 0;
}

.msg-body :deep(table) {
  border-collapse: collapse;
  margin: var(--space-2) 0;
  width: 100%;
}

.msg-body :deep(th),
.msg-body :deep(td) {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
  font-size: 13px;
}

.msg-body :deep(th) {
  background: #f3f4f6;
}

.msg-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 12px 0;
}

.msg-body :deep(.cite-ref) {
  color: var(--accent);
  cursor: pointer;
  font-size: 0.72em;
  font-weight: 700;
  margin-left: 1px;
  vertical-align: super;
}
</style>
