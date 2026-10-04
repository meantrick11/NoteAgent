<script setup lang="ts">
import { computed } from 'vue'

import type { RecoveryPreview } from '@/shared/api/types'
import { conflictSummary } from './recovery'

const props = defineProps<{
  preview: RecoveryPreview | null
  phase: 'idle' | 'editing' | 'previewing' | 'confirming' | 'running' | 'conflict' | 'failed'
  error?: string
  retryable?: boolean
}>()

defineEmits<{
  (event: 'confirm'): void
  (event: 'cancel'): void
  (event: 'retry'): void
}>()

const conflicts = computed(() => props.preview?.conflicts ?? [])
const files = computed(() => props.preview?.file_changes ?? [])
const folders = computed(() => props.preview?.folder_changes ?? [])
const busy = computed(() => props.phase === 'running' || props.phase === 'previewing')
</script>

<template>
  <div class="recovery-backdrop">
    <div class="recovery-dialog" role="dialog" aria-modal="true" aria-label="确认整体回退">
      <h3>确认回退已执行的文件改动</h3>

      <template v-if="phase === 'conflict'">
        <p class="warn">无法回退：其他会话或外部修改涉及同一文件。</p>
        <ul class="changes conflicts">
          <li v-for="item in conflicts" :key="item.path + item.reason">
            {{ item.path || '（会话状态）' }}：{{ item.reason }}
          </li>
        </ul>
        <p v-if="preview" class="hint">{{ conflictSummary(preview) }}</p>
      </template>

      <template v-else>
        <p>以下文件／目录将被回退，其余改动保持不变：</p>
        <ul class="changes">
          <li v-for="item in files" :key="item.path">
            {{ item.action === 'delete' ? '删除' : '恢复' }}：{{ item.path }}
          </li>
          <li v-for="item in folders" :key="'f-' + item.path">
            {{ item.action === 'create' ? '新建目录' : '删除目录' }}：{{ item.path }}
          </li>
          <li v-if="!files.length && !folders.length">没有文件改动，仅恢复会话状态。</li>
        </ul>
        <p v-if="phase === 'running'" class="hint" role="status">正在回退并重建索引…</p>
        <p v-else-if="phase === 'failed'" class="warn" role="status">{{ error || '恢复失败' }}</p>
      </template>

      <div class="recovery-actions">
        <template v-if="phase === 'conflict'">
          <button type="button" class="btn" @click="$emit('cancel')">取消</button>
        </template>
        <template v-else-if="phase === 'failed'">
          <button type="button" class="btn primary" :disabled="!retryable" @click="$emit('retry')">
            重试
          </button>
          <button type="button" class="btn" @click="$emit('cancel')">取消</button>
        </template>
        <template v-else>
          <button type="button" class="btn primary" :disabled="busy" @click="$emit('confirm')">
            确认回退并重新生成
          </button>
          <button type="button" class="btn" :disabled="busy" @click="$emit('cancel')">取消</button>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.recovery-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 30;
}

.recovery-dialog {
  width: min(520px, 92vw);
  background: var(--surface);
  border-radius: var(--radius);
  padding: 20px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
}

.recovery-dialog h3 {
  margin: 0 0 12px;
  font-size: 16px;
}

.changes {
  margin: 8px 0;
  padding-left: 18px;
  max-height: 220px;
  overflow: auto;
  font-size: 13px;
}

.changes.conflicts {
  color: var(--danger, #dc2626);
}

.warn {
  color: var(--danger, #dc2626);
}

.hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.recovery-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.btn {
  padding: 6px 14px;
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
</style>
