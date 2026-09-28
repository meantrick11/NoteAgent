<script setup lang="ts">
import { computed, ref } from 'vue'

import { renderMarkdown } from './markdown'

const props = defineProps<{ text: string }>()

const root = ref<HTMLElement | null>(null)
const html = computed(() => renderMarkdown(props.text))

/** 供父组件做编辑区／预览区同步滚动。 */
defineExpose({ root })
</script>

<template>
  <div ref="root" class="markdown-preview" v-html="html"></div>
</template>
