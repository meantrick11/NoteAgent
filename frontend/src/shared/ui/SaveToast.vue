<script setup lang="ts">
import { toastVisible } from './toast'
</script>

<template>
  <div class="save-toast" :class="{ 'save-toast-on': toastVisible }" role="status">
    文件已保存
  </div>
</template>

<style scoped>
.save-toast {
  position: fixed;
  top: 12px;
  right: 16px;
  z-index: 300;
  padding: 10px 14px;
  background: var(--text);
  color: #fff;
  border-radius: var(--radius-sm);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  font-size: 13px;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transform: translateY(-6px);
  transition:
    opacity 0.2s ease,
    transform 0.2s ease,
    visibility 0.2s ease;
}

.save-toast-on {
  opacity: 1;
  visibility: visible;
  transform: translateY(0);
}

/* 内嵌浏览器里改贴导航右缘，见 toast.ts。 */
:global(html[style*='--toast-left']) .save-toast {
  left: var(--toast-left);
  right: auto;
}
</style>
