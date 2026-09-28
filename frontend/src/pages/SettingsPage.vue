<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useModelsStore } from '@/features/models/store'
import ModelConnectionsSection from '@/features/settings/ModelConnectionsSection.vue'
import RetrievalSection from '@/features/settings/RetrievalSection.vue'
import SettingsLayout from '@/features/settings/SettingsLayout.vue'
import {
  AVAILABLE_SETTINGS_SECTIONS,
  resolveSettingsSection,
} from '@/features/settings/sections'

/**
 * Settings 用 query 表达分类，服务端路径始终是 `/settings`：
 *   - 裸路径按默认分类显示，不主动补 query；
 *   - 提供了无效、未开放或数组值时 replace 成默认分类，并保留其他 query；
 *   - 两个可用分类都保持挂载、用 v-show 切换，切分类不会重建表单。
 * 分类只改地址，不触发保存、连接测试、切换模型或重建。
 */
const route = useRoute()
const router = useRouter()
const models = useModelsStore()

const activeSection = computed(() => resolveSettingsSection(route.query.section))

/** 只修正「提供了但无效」的分类：裸路径与合法值都不改写地址。 */
watch(
  () => route.query.section,
  (raw) => {
    if (raw === undefined) return
    const resolved = resolveSettingsSection(raw)
    if (raw === resolved) return
    void router.replace({ path: '/settings', query: { ...route.query, section: resolved } })
  },
  { immediate: true },
)

onMounted(() => {
  void models.fetchStatus(true)
  void models.loadCandidates()
})
</script>

<template>
  <section class="page">
    <div class="settings-body">
      <h1 class="page-title">设置</h1>
      <p class="page-hint">
        管理模型连接、检索与应用偏好。这里的配置与 Assistant 输入框下方的模型入口是同一份数据，改任一处两边都会更新。
      </p>

      <SettingsLayout :sections="AVAILABLE_SETTINGS_SECTIONS" :active="activeSection">
        <template #content>
          <!-- 同时挂载、只切换显隐：切分类不会丢掉表单里尚未提交的文本。 -->
          <ModelConnectionsSection v-show="activeSection === 'models'" />
          <RetrievalSection v-show="activeSection === 'retrieval'" />
        </template>
      </SettingsLayout>
    </div>
  </section>
</template>

<style scoped>
.settings-body {
  padding: var(--space-5);
  max-width: 900px;
}
</style>
