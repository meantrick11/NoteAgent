<script setup lang="ts">
import { RouterLink } from 'vue-router'

import type { AvailableSettingsSectionId, SettingsSection } from './sections'

/**
 * 设置的分类骨架：左侧（窄屏在上方）分类导航，右侧内容插槽。
 * 分类是链接而不是模拟 tab，所以刷新、前进后退与深链接都由路由负责。
 */
defineProps<{
  sections: readonly SettingsSection[]
  active: AvailableSettingsSectionId
}>()
</script>

<template>
  <div class="settings-layout">
    <nav class="settings-sections" aria-label="设置分类">
      <RouterLink
        v-for="section in sections"
        :key="section.id"
        class="settings-section-link"
        :class="{ active: section.id === active }"
        :to="{ path: '/settings', query: { section: section.id } }"
        :aria-current="section.id === active ? 'page' : undefined"
      >
        {{ section.title }}
      </RouterLink>
    </nav>
    <div class="settings-content">
      <slot name="content" />
    </div>
  </div>
</template>

<style scoped>
.settings-layout {
  display: flex;
  align-items: flex-start;
  gap: var(--space-5);
  margin-top: var(--space-4);
}

.settings-sections {
  flex-shrink: 0;
  width: 168px;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.settings-section-link {
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 13px;
  padding: 7px var(--space-3);
  border-radius: var(--radius-sm);
  border-left: 2px solid transparent;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s;
}

.settings-section-link:hover {
  background: var(--bg);
  color: var(--text);
}

.settings-section-link.active {
  color: var(--text);
  background: var(--bg);
  border-left-color: var(--accent);
  font-weight: 600;
}

.settings-content {
  flex: 1;
  min-width: 0;
}

/* 窄屏：分类移到内容上方并允许换行，控件不被压窄。 */
@media (max-width: 720px) {
  .settings-layout {
    flex-direction: column;
    gap: var(--space-3);
  }

  .settings-sections {
    width: 100%;
    flex-direction: row;
    flex-wrap: wrap;
  }

  .settings-section-link {
    border-left: none;
    border-bottom: 2px solid transparent;
  }

  .settings-section-link.active {
    border-left-color: transparent;
    border-bottom-color: var(--accent);
  }
}
</style>
