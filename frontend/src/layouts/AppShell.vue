<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import SaveToast from '@/shared/ui/SaveToast.vue'
import { PRIMARY_NAV_ITEMS, SETTINGS_ENTRY } from '@/shared/navigation'
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <nav class="app-nav" aria-label="主导航">
        <span class="app-nav-brand">📒 NoteAgent</span>
        <RouterLink
          v-for="item in PRIMARY_NAV_ITEMS"
          :key="item.name"
          class="app-nav-link"
          :to="item.path"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
      <!-- 设置是工具区入口，不属于主导航，避免在 /settings 下误选某一项工作入口。 -->
      <div class="app-nav-tools">
        <RouterLink
          class="app-icon-link"
          :to="SETTINGS_ENTRY.path"
          aria-label="设置"
          title="设置"
        >
          <svg
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            aria-hidden="true"
          >
            <circle cx="12" cy="12" r="3" />
            <path
              d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
            />
          </svg>
        </RouterLink>
      </div>
    </header>
    <main class="app-main">
      <RouterView />
    </main>
    <!-- 全局单例：一次只可能有一个对话框与一个保存提示。 -->
    <ConfirmDialog />
    <SaveToast />
  </div>
</template>
