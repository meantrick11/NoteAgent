<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

import ChatProfiles from './ChatProfiles.vue'
import EmbeddingSettings from './EmbeddingSettings.vue'
import { useModelsStore } from './store'

/**
 * 输入框下方的两个模型入口。能力与旧页面一致：
 * 显示当前生效的模型名、点开就能看／改配置、生成中与维护期间禁用。
 *
 * 弹层内容与 Settings 页共用同一批组件，避免两份逻辑。
 */
const models = useModelsStore()

const openKind = ref<'chat' | 'embedding' | null>(null)
const chatTrigger = ref<HTMLButtonElement | null>(null)
const embeddingTrigger = ref<HTMLButtonElement | null>(null)
const popover = ref<HTMLElement | null>(null)

async function toggle(kind: 'chat' | 'embedding'): Promise<void> {
  if (openKind.value === kind) {
    close()
    return
  }
  openKind.value = kind
  if (kind === 'embedding') await models.loadCandidates()
  await nextTick()
  popover.value?.querySelector<HTMLElement>('button, input, select')?.focus()
}

function close(): void {
  const previous = openKind.value
  openKind.value = null
  // 焦点回到触发按钮，键盘用户可以继续操作。
  if (previous === 'chat') chatTrigger.value?.focus()
  else if (previous === 'embedding') embeddingTrigger.value?.focus()
}

function onDocumentKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Escape' || !openKind.value) return
  event.preventDefault()
  close()
}

function onDocumentClick(event: MouseEvent): void {
  if (!openKind.value) return
  const target = event.target as HTMLElement
  if (target.closest('.model-toolbar')) return
  close()
}

watch(openKind, (kind) => {
  if (typeof document === 'undefined') return
  if (kind) {
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
</script>

<template>
  <div class="model-toolbar">
    <div class="model-picker">
      <button
        ref="chatTrigger"
        type="button"
        class="model-btn"
        aria-haspopup="dialog"
        :aria-expanded="openKind === 'chat'"
        title="聊天模型设置"
        :disabled="models.streaming"
        @click="toggle('chat')"
      >
        <span class="model-btn-kind">聊天</span>
        <span class="model-btn-name">{{ models.activeChat?.label ?? '未配置' }}</span>
        <span class="model-btn-caret" aria-hidden="true">▾</span>
      </button>

      <div
        v-if="openKind === 'chat'"
        ref="popover"
        class="model-popover"
        role="dialog"
        aria-label="聊天模型设置"
      >
        <h4>聊天模型</h4>
        <ChatProfiles />
      </div>
    </div>

    <div class="model-picker">
      <button
        ref="embeddingTrigger"
        type="button"
        class="model-btn"
        aria-haspopup="dialog"
        :aria-expanded="openKind === 'embedding'"
        title="本地向量模型设置"
        :disabled="models.streaming"
        @click="toggle('embedding')"
      >
        <span class="model-btn-kind">向量</span>
        <span class="model-btn-name">{{ models.activeEmbedding?.model_id ?? '未知' }}</span>
        <span class="model-btn-caret" aria-hidden="true">▾</span>
      </button>

      <div
        v-if="openKind === 'embedding'"
        ref="popover"
        class="model-popover"
        role="dialog"
        aria-label="向量模型设置"
      >
        <h4>向量模型</h4>
        <EmbeddingSettings />
      </div>
    </div>
  </div>

  <p v-if="models.busy" class="model-toolbar-note">
    向量索引重建中：暂时不能发送消息或保存笔记，已有内容仍可查看。
  </p>
</template>

<style scoped>
.model-toolbar {
  max-width: calc((100% + 768px) / 2);
  margin: var(--space-2) auto 0;
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.model-picker {
  position: relative;
}

.model-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-family: inherit;
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  cursor: pointer;
  max-width: 100%;
}

.model-btn:hover:not(:disabled) {
  background: var(--bg);
}

.model-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.model-btn-kind {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.model-btn-name {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-btn-caret {
  color: var(--text-secondary);
  flex-shrink: 0;
}

.model-popover {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  width: 380px;
  max-width: min(380px, 88vw);
  max-height: 60vh;
  overflow-y: auto;
  padding: var(--space-3);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-modal);
  z-index: 120;
}

.model-popover h4 {
  font-size: 14px;
  margin-bottom: var(--space-2);
}

.model-toolbar-note {
  max-width: calc((100% + 768px) / 2);
  margin: var(--space-2) auto 0;
  font-size: 12px;
  color: var(--warn-text);
  background: var(--warn-bg);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
}
</style>
