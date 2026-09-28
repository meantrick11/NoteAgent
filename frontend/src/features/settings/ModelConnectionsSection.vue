<script setup lang="ts">
import ChatProfiles from '@/features/models/ChatProfiles.vue'
</script>

<template>
  <!-- 原来的 ChatProfiles：配置增改删、连接测试、保存与启用全部保留，这里只补分类的标题与说明。 -->
  <section
    class="settings-panel"
    data-settings-section="models"
    aria-labelledby="settings-models-title"
  >
    <h2 id="settings-models-title" class="settings-heading">模型与连接</h2>
    <p class="settings-hint">
      配置聊天服务的连接、凭据与上下文窗口。这里与 Assistant 输入框下方的模型入口是同一份数据，改任一处两边都会更新。
    </p>
    <ChatProfiles />
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
</style>
