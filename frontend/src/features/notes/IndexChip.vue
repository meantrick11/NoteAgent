<script setup lang="ts">
import { computed } from 'vue'

import { useNotesStore } from './store'

/** 索引状态芯片：已索引／未索引／入库中；点未索引的那一个就补建。 */
const props = defineProps<{ indexed: boolean; fileName: string }>()

const notes = useNotesStore()

const busy = computed(() => notes.indexing.includes(props.fileName))

function onClick(): void {
  if (props.indexed || busy.value) return
  void notes.indexDocument(props.fileName)
}
</script>

<template>
  <span
    class="chip index-chip"
    :class="{ on: indexed, clickable: !indexed, busy }"
    :title="indexed ? '已入向量索引' : '点击补建这篇的向量'"
    :role="indexed ? undefined : 'button'"
    :tabindex="indexed ? undefined : 0"
    @click.stop="onClick"
    @keydown.enter.stop="onClick"
    @mousedown.stop
  >
    {{ indexed ? '已索引' : busy ? '入库中…' : '未索引' }}
  </span>
</template>

<style scoped>
.index-chip {
  flex-shrink: 0;
}

.index-chip.on {
  background: var(--ok-bg);
  color: var(--ok-text);
}

.index-chip.clickable {
  cursor: pointer;
}

.index-chip.clickable:hover {
  background: var(--accent-soft);
  color: var(--accent);
}

.index-chip.busy {
  cursor: wait;
  opacity: 0.7;
  pointer-events: none;
}
</style>
