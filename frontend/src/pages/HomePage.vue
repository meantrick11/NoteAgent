<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'

import { useModelsStore } from '@/features/models/store'
import { listNotes } from '@/features/notes/api'
import { NAV_ITEMS } from '@/shared/navigation'

/**
 * Home 只呈现现有接口能给出的东西：`GET /notes` 的笔记／索引数量，
 * 以及 `/model-settings` 的索引可用性与维护状态。不画趋势图、复习统计、
 * 活动流或任何"还没有的能力"，缺数据时明确说读不到，而不是显示 0。
 */
const models = useModelsStore()

const total = ref<number | null>(null)
const indexed = ref<number | null>(null)
const loading = ref(false)
const error = ref('')

const unindexed = computed(() =>
  total.value === null || indexed.value === null ? null : total.value - indexed.value,
)

/** 索引不可用时要与"逐篇未索引"分开说，不能都算成待补建。 */
const retrievalNote = computed(() => {
  if (models.busy) return '向量索引重建中：暂时不能发送消息或保存笔记，已有内容仍可查看。'
  if (!models.retrievalAvailable) return models.retrievalProblem ?? '向量索引当前不可用。'
  if (models.retrievalState !== 'ok') return models.retrievalStatus?.text ?? ''
  return ''
})

/** 顶部导航之外的快捷入口；顺序与顶部一致，只是去掉了 Home 自己。 */
const shortcuts = computed(() => NAV_ITEMS.filter((item) => item.name !== 'home'))

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const catalog = await listNotes()
    total.value = catalog.files.length
    indexed.value = catalog.files.filter((file) => file.indexed).length
  } catch (thrown) {
    total.value = null
    indexed.value = null
    error.value = (thrown as Error).message
  } finally {
    loading.value = false
  }
  // 可用性与维护状态来自共享的模型状态，顺手刷新一次。
  void models.refreshIfStale()
}

onMounted(load)
</script>

<template>
  <section class="page">
    <div class="home-body">
      <h1 class="page-title">Home</h1>
      <p class="page-hint">笔记概览与四个入口。数字都来自现有接口，读不到时不会用 0 顶替。</p>

      <div v-if="loading" class="card home-card">
        <p class="page-hint">正在读取笔记目录…</p>
      </div>

      <div v-else-if="error" class="card home-card">
        <p class="home-error">读取笔记目录失败：{{ error }}</p>
        <button type="button" class="btn" @click="load">重试</button>
      </div>

      <div v-else class="stat-grid">
        <div class="card stat">
          <span class="stat-value">{{ total }}</span>
          <span class="stat-label">笔记总数</span>
        </div>
        <div class="card stat">
          <span class="stat-value">{{ indexed }}</span>
          <span class="stat-label">已索引</span>
        </div>
        <div class="card stat">
          <span class="stat-value">{{ unindexed }}</span>
          <span class="stat-label">未索引</span>
        </div>
      </div>

      <p v-if="retrievalNote" class="home-note">{{ retrievalNote }}</p>
      <p v-else-if="!loading && !error" class="page-hint">
        索引已就绪：检索与笔记写入都可以正常进行。
      </p>

      <h2 class="home-heading">入口</h2>
      <div class="shortcut-grid">
        <RouterLink
          v-for="item in shortcuts"
          :key="item.name"
          class="card shortcut"
          :to="item.path"
        >
          <span class="shortcut-label">{{ item.label }}</span>
          <span class="shortcut-hint">{{ item.name === 'records' ? '尚未开放' : '打开' }}</span>
        </RouterLink>
      </div>
      <!-- 复习内容等尚无能力支撑的项目只留扩展位，不放假数据。 -->
      <p class="page-hint home-more">后续能力会在这一行下方继续扩展。</p>
    </div>
  </section>
</template>

<style scoped>
.home-body {
  padding: var(--space-5);
  max-width: 820px;
}

.home-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.home-error {
  color: var(--danger);
  font-size: 13px;
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.stat {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.stat-value {
  font-size: 28px;
  font-weight: 650;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.home-note {
  margin-top: var(--space-3);
  padding: 8px 12px;
  font-size: 13px;
  border-radius: var(--radius-sm);
  background: var(--warn-bg);
  color: var(--warn-text);
}

.home-heading {
  margin-top: var(--space-5);
  font-size: 15px;
  font-weight: 650;
}

.shortcut-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.shortcut {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  text-decoration: none;
  color: var(--text);
  transition: border-color 0.15s, background 0.15s;
}

.shortcut:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.shortcut-label {
  font-size: 14px;
  font-weight: 600;
}

.shortcut-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.home-more {
  margin-top: var(--space-2);
}
</style>
