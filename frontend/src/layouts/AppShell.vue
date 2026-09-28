<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

import ConfirmDialog from '@/shared/ui/ConfirmDialog.vue'
import SaveToast from '@/shared/ui/SaveToast.vue'
import { NAV_ITEMS } from '@/shared/navigation'
</script>

<template>
  <div class="app-shell">
    <nav class="app-nav" aria-label="主导航">
      <span class="app-nav-brand">📒 NoteAgent</span>
      <RouterLink
        v-for="item in NAV_ITEMS"
        :key="item.name"
        class="app-nav-link"
        :to="item.path"
      >
        {{ item.label }}
      </RouterLink>
    </nav>
    <main class="app-main">
      <RouterView />
    </main>
    <!-- 全局单例：一次只可能有一个对话框与一个保存提示。 -->
    <ConfirmDialog />
    <SaveToast />
  </div>
</template>
