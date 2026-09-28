<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'

import AppShell from '@/layouts/AppShell.vue'
import { useModelsStore } from '@/features/models/store'

// 模型状态在应用根部初始化一次：可见性与跨标签监听只有一份，
// 组件切换页面不会各注册一套轮询。
const models = useModelsStore()

onMounted(() => models.init())
onBeforeUnmount(() => models.dispose())
</script>

<template>
  <AppShell />
</template>
