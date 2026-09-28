<script setup lang="ts">
import { computed, onMounted } from 'vue'

import ChatProfiles from '@/features/models/ChatProfiles.vue'
import EmbeddingSettings from '@/features/models/EmbeddingSettings.vue'
import { STAGE_TEXT, useModelsStore } from '@/features/models/store'

/**
 * Settings 承接原来的聊天配置与向量配置。这里挂的组件与 Assistant 输入框下方的
 * 快捷弹层是同一份（`ChatProfiles` / `EmbeddingSettings`），状态也共用同一个 store，
 * 所以两个入口不会各自轮询、也不会各写一套逻辑。
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

onMounted(() => {
  void models.fetchStatus(true)
  void models.loadCandidates()
})
</script>

<template>
  <section class="page">
    <div class="settings-body">
      <h1 class="page-title">Settings</h1>
      <p class="page-hint">
        这里的配置与 Assistant 输入框下方的模型入口是同一份数据，改任一处两边都会更新。
      </p>

      <section class="settings-card">
        <h2 class="settings-heading">聊天模型</h2>
        <ChatProfiles />
      </section>

      <section class="settings-card">
        <h2 class="settings-heading">向量模型与索引</h2>
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
    </div>
  </section>
</template>

<style scoped>
.settings-body {
  padding: var(--space-5);
  max-width: 760px;
}

.settings-card {
  margin-top: var(--space-5);
  padding: var(--space-4);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.settings-heading {
  font-size: 15px;
  font-weight: 650;
  margin-bottom: var(--space-2);
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
