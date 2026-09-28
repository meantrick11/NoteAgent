<script setup lang="ts">
import { computed, onMounted } from 'vue'

import { STAGE_TEXT, availabilityLabel, useModelsStore } from './store'

/**
 * 本地向量模型：候选、可用性原因、索引状态与重建任务进度。
 * Settings 页与 Assistant 快捷弹层共用同一个 store，所以轮询只有一份。
 */
const models = useModelsStore()

const job = computed(() => models.embeddingJob)
const progressPercent = computed(() => {
  const current = job.value
  if (!current?.total) return 0
  return Math.round((current.completed / current.total) * 100)
})

const stageText = computed(() => {
  const current = job.value
  if (!current) return ''
  return STAGE_TEXT[current.stage] ?? current.stage
})

const counter = computed(() => {
  const current = job.value
  return current?.total ? `（${current.completed}/${current.total}）` : ''
})

/** 任务结束后服务端仍保留最后一条记录，成功／失败／中断都要说清楚。 */
const jobOutcome = computed(() => {
  const current = job.value
  if (!current || current.status === 'running') return null
  if (current.status === 'succeeded') {
    return { kind: 'ok', text: `已切换到 ${current.target_model}，检索与笔记索引都使用新模型。` }
  }
  if (current.status === 'interrupted') {
    return {
      kind: 'error',
      text: `上次重建被中断（${current.target_model}），仍在使用 ${models.activeEmbeddingId}；可以再点一次重试。`,
    }
  }
  return {
    kind: 'error',
    text: `重建失败：${current.error || '未知原因'}。仍在使用 ${models.activeEmbeddingId}；可以再点一次重试。`,
  }
})

onMounted(() => {
  void models.loadCandidates()
})
</script>

<template>
  <div class="embedding-settings">
    <p class="ms-row-sub">只能选择本地缓存中已存在的受支持模型；本应用不自动下载。</p>

    <div
      v-for="candidate in models.embeddingCandidates"
      :key="candidate.model_id"
      class="ms-row"
      :class="{ active: candidate.active }"
    >
      <div class="ms-row-main">
        <div class="ms-row-title">{{ candidate.label }}</div>
        <div class="ms-row-sub">{{ candidate.model_id }}</div>
        <div v-if="candidate.reason" class="ms-row-sub">{{ candidate.reason }}</div>
      </div>

      <span
        v-if="candidate.active && models.retrievalAvailable"
        class="chip chip-on"
      >
        已启用
      </span>
      <template v-else-if="candidate.availability === 'available'">
        <!-- 当前模型但索引不可用时，同一个按钮就是修复入口。 -->
        <button
          type="button"
          class="btn"
          :class="{ 'btn-primary': candidate.active }"
          :disabled="models.modelActionsLocked"
          title="重建期间暂不可发送消息或保存笔记，已有内容仍可查看"
          @click="models.switchEmbedding(candidate.model_id)"
        >
          {{ candidate.active ? '重建并修复' : '重建并切换' }}
        </button>
        <span v-if="candidate.active" class="chip chip-warn">索引不可用</span>
      </template>
      <span v-else class="chip chip-warn" :title="candidate.reason ?? ''">
        {{ availabilityLabel(candidate.availability) }}
      </span>
    </div>

    <p v-if="!models.embeddingCandidates.length" class="ms-row-sub">读取中…</p>

    <div v-if="job?.status === 'running'" class="ms-progress">
      正在切换到 {{ job.target_model }}：{{ stageText }}{{ counter }}
      <div class="ms-bar"><div class="ms-bar-fill" :style="{ width: `${progressPercent}%` }"></div></div>
    </div>

    <!-- 重建进行中时由进度条说明情况，状态区让位，避免两处说法互相矛盾。 -->
    <p v-else-if="models.retrievalStatus" class="ms-row-sub">
      {{ models.retrievalStatus.text }}
    </p>

    <p v-if="jobOutcome" class="ms-notice" :class="`ms-${jobOutcome.kind}`">
      {{ jobOutcome.text }}
    </p>
    <p
      v-if="models.embeddingNotice"
      class="ms-notice"
      :class="`ms-${models.embeddingNotice.kind}`"
    >
      {{ models.embeddingNotice.text }}
    </p>
  </div>
</template>

<style scoped>
.ms-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
  background: var(--surface);
}

.ms-row.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.ms-row-main {
  flex: 1;
  min-width: 0;
}

.ms-row-title {
  font-size: 13px;
  font-weight: 600;
}

.ms-row-sub {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.chip-on {
  background: var(--ok-bg);
  color: var(--ok-text);
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  flex-shrink: 0;
}

.chip-warn {
  background: var(--warn-bg);
  color: var(--warn-text);
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  flex-shrink: 0;
}

.ms-progress {
  margin-top: var(--space-2);
  font-size: 12px;
  color: var(--text-secondary);
}

.ms-bar {
  margin-top: var(--space-1);
  height: 4px;
  border-radius: var(--radius-pill);
  background: var(--border);
  overflow: hidden;
}

.ms-bar-fill {
  height: 100%;
  background: var(--accent);
  transition: width 0.3s;
}

.ms-notice {
  margin-top: var(--space-2);
  font-size: 12px;
  line-height: 1.5;
}

.ms-ok {
  color: var(--ok-text);
}

.ms-error {
  color: var(--danger);
}
</style>
