<script setup lang="ts">
import { computed } from 'vue'

import EmbeddingSettings from '@/features/models/EmbeddingSettings.vue'
import { STAGE_TEXT, useModelsStore } from '@/features/models/store'

/**
 * 「检索与索引」分类。承接原设置页顶部的向量摘要与任务阶段行，
 * 内容是原来就在这里的 EmbeddingSettings，不新增操作。
 */
const models = useModelsStore()

const STATUS_TEXT: Record<string, string> = {
  ok: '索引正常',
  empty: '索引为空',
  missing: '索引缺失',
  config_mismatch: '索引配置已变化',
  unavailable: '索引不可用',
}

const retrievalLabel = computed(() => STATUS_TEXT[models.retrievalState] ?? models.retrievalState)
const jobLabel = computed(() => {
  const job = models.embeddingJob
  if (!job || job.status !== 'running') return ''
  const stage = STAGE_TEXT[job.stage] ?? job.stage
  const counter = job.total ? `（${job.completed}/${job.total}）` : ''
  return `正在切换到 ${job.target_model}：${stage}${counter}`
})
</script>

<template>
  <section
    class="settings-panel"
    data-settings-section="retrieval"
    aria-labelledby="settings-retrieval-title"
  >
    <h2 id="settings-retrieval-title" class="settings-heading">检索与索引</h2>
    <p class="settings-hint">
      选择本地向量模型并维护索引。重建期间不能发送消息或保存笔记，已有内容仍可查看。
    </p>
    <p class="settings-summary">
      <span>当前：{{ models.activeEmbedding?.model_id ?? '未知' }}</span>
      <span>·</span>
      <span>{{ retrievalLabel }}</span>
      <span>·</span>
      <span>已索引 {{ models.indexedFiles }} 个片段 / {{ models.corpusFiles }} 篇笔记</span>
      <span v-if="models.busy" class="settings-busy">维护中</span>
    </p>
    <p v-if="jobLabel" class="settings-summary">{{ jobLabel }}</p>
    <EmbeddingSettings />
  </section>
</template>

<style scoped>
.settings-panel {
  max-width: 640px;
}

.settings-heading {
  font-size: 15px;
  font-weight: 650;
}

.settings-hint {
  margin: var(--space-2) 0 var(--space-3);
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.settings-summary {
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-bottom: var(--space-2);
}

.settings-busy {
  color: var(--warn-text);
  background: var(--warn-bg);
  padding: 0 6px;
  border-radius: var(--radius-pill);
}
</style>
