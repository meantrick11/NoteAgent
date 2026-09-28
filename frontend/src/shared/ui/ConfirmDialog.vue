<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'

import { dialogState, settle } from './confirm'

const state = dialogState()
const inputEl = ref<HTMLInputElement | null>(null)
const okEl = ref<HTMLButtonElement | null>(null)
// 输入框自己持有一份文本，避免在模板里把 state 的 value 字段和 ref 的 .value 混在一起读。
const draft = ref('')

watch(
  () => state.value.open,
  async (open) => {
    if (!open) return
    draft.value = state.value.value ?? ''
    await nextTick()
    // 有输入框就聚焦并全选，否则焦点落到确认按钮，键盘可以直接继续。
    if (state.value.input && inputEl.value) {
      inputEl.value.focus()
      inputEl.value.select()
    } else {
      okEl.value?.focus()
    }
  },
)

function cancel(): void {
  settle(null)
}

function confirm(): void {
  settle(state.value.input ? draft.value : true)
}

function onInputKeydown(event: KeyboardEvent): void {
  if (event.key !== 'Enter') return
  event.preventDefault()
  confirm()
}
</script>

<template>
  <div
    v-if="state.open"
    class="modal-overlay"
    role="presentation"
    @click.self="cancel"
  >
    <div class="modal" role="dialog" aria-modal="true" :aria-label="state.title">
      <h3 class="modal-title">{{ state.title }}</h3>
      <p v-if="state.body" class="modal-body">{{ state.body }}</p>
      <input
        v-if="state.input"
        ref="inputEl"
        v-model="draft"
        class="modal-input"
        @keydown="onInputKeydown"
      />
      <div class="modal-actions">
        <button v-if="!state.alert" type="button" class="btn" @click="cancel">取消</button>
        <button
          ref="okEl"
          type="button"
          class="btn"
          :class="state.danger ? 'btn-danger' : 'btn-primary'"
          @click="confirm"
        >
          {{ state.confirmText || '确认' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.modal {
  background: var(--surface);
  border-radius: var(--radius);
  padding: 20px;
  width: 320px;
  box-shadow: var(--shadow-modal);
}

.modal-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: var(--space-2);
}

.modal-body {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: var(--space-4);
  line-height: 1.6;
  white-space: pre-wrap;
}

.modal-input {
  display: block;
  width: 100%;
  font-size: 14px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  font-family: inherit;
  margin-bottom: var(--space-4);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.btn-danger:hover:not(:disabled) {
  background: var(--danger);
  border-color: var(--danger);
  color: #fff;
}
</style>
