<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ChatComposer from '@/features/chat/ChatComposer.vue'
import ConversationList from '@/features/chat/ConversationList.vue'
import MessageList from '@/features/chat/MessageList.vue'
import NotePane from '@/features/chat/NotePane.vue'
import { useChatLayout } from '@/features/chat/layout'
import { useChatStore } from '@/features/chat/store'
import ModelQuickControls from '@/features/models/ModelQuickControls.vue'
import ResizablePane from '@/shared/ui/ResizablePane.vue'
import type { Citation } from '@/shared/api/types'

const chat = useChatStore()
const layout = useChatLayout()

const scroller = ref<HTMLElement | null>(null)

/** 新消息或流式增量都跟着滚到底。 */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
}

watch(
  () => [chat.visibleMessages.length, chat.visibleMessages.at(-1)?.content],
  () => {
    void scrollToBottom()
  },
)

function onCite(cite: Citation): void {
  void chat.openCitation(cite)
}

function onHandlePointerDown(kind: 'sidebar' | 'pane', event: PointerEvent): void {
  layout.beginDrag(kind, event)
  // 指针捕获让拖到面板外时仍然收得到 move／up。
  const handle = event.currentTarget as HTMLElement | null
  handle?.setPointerCapture?.(event.pointerId)
}

// 拖动期间锁定全局光标与选区；样式只在 body 上挂一次。
watch(
  () => layout.dragging.value,
  (dragging) => {
    document.body.classList.toggle('pane-resizing', dragging)
  },
)

onMounted(async () => {
  // 先读列表再决定打开哪一个：历史里没有会话时就停在欢迎页。
  const before = chat.selectionVersion
  const list = await chat.loadConversations()
  // 列表还没回来时用户就自己点了「新对话」或某条会话，不抢他的选择。
  if (chat.selectionVersion !== before) return
  if (list.length) await chat.openConversation(list[0].id)
  await nextTick()
  if (chat.visibleMessages.length) await scrollToBottom()
})

onBeforeUnmount(() => {
  layout.dispose()
})
</script>

<template>
  <section
    class="assistant-page"
    :style="{
      '--sidebar-width': `${layout.effective.value.sidebarWidth}px`,
      '--note-pane-width': `${layout.effective.value.notePaneWidth}px`,
    }"
  >
    <ConversationList />

    <ResizablePane
      label="调整会话列表宽度"
      :value="layout.effective.value.sidebarWidth"
      :min="layout.bounds.value.sidebarMin"
      :max="layout.bounds.value.sidebarMax"
      :dragging="layout.dragging.value"
      @pointerdown="onHandlePointerDown('sidebar', $event)"
      @pointermove="layout.moveDrag($event)"
      @pointerup="layout.endDrag()"
      @keydown="layout.keyPaneWidth('sidebar', $event)"
    />

    <div class="main">
      <div class="main-header">学习笔记助手</div>

      <div class="main-stage">
        <div ref="scroller" class="chat-container">
          <MessageList
            :messages="chat.visibleMessages"
            :welcome="!chat.hasMessages"
            @cite="onCite"
          />
        </div>

        <ResizablePane
          label="调整笔记面板宽度"
          :value="layout.effective.value.notePaneWidth"
          :min="layout.bounds.value.paneMin"
          :max="layout.bounds.value.paneMax"
          :hidden="chat.panel.hidden"
          :dragging="layout.dragging.value"
          @pointerdown="onHandlePointerDown('pane', $event)"
          @pointermove="layout.moveDrag($event)"
          @pointerup="layout.endDrag()"
          @keydown="layout.keyPaneWidth('pane', $event)"
        />

        <NotePane />
      </div>

      <ChatComposer>
        <ModelQuickControls />
      </ChatComposer>
    </div>
  </section>
</template>

<style scoped>
.assistant-page {
  flex: 1;
  min-height: 0;
  display: flex;
}

.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.main-header {
  min-height: var(--header-height);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  padding: 0 var(--space-5);
  background: var(--surface);
  font-size: 14px;
  color: var(--text-secondary);
  flex-shrink: 0;
}

/* 聊天区与右侧面板并排，输入区固定在这条 stage 下方。 */
.main-stage {
  flex: 1;
  display: flex;
  min-height: 0;
}

.chat-container {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: var(--space-5) 0;
}

.chat-container::-webkit-scrollbar {
  width: 6px;
}

.chat-container::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 3px;
}
</style>
