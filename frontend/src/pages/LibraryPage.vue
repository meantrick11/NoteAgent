<script setup lang="ts">
import { onMounted, ref } from 'vue'

import NoteEditor from '@/features/notes/NoteEditor.vue'
import NoteTree from '@/features/notes/NoteTree.vue'
import { useNotesStore } from '@/features/notes/store'
import SourceFileLibrary from '@/features/source-files/SourceFileLibrary.vue'

const notes = useNotesStore()
const view = ref<'notes' | 'files'>('notes')

onMounted(() => {
  void notes.loadCatalog()
})
</script>

<template>
  <div class="library-shell">
    <nav class="library-tabs"><button type="button" @click="view = 'notes'">笔记</button><button type="button" @click="view = 'files'">文件</button></nav>
    <section class="library-page">
      <template v-if="view === 'notes'"><NoteTree /><NoteEditor /></template>
      <SourceFileLibrary v-else />
    </section>
  </div>
</template>

<style scoped>
.library-page {
  flex: 1;
  min-height: 0;
  display: flex;
}
.library-shell { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.library-tabs { display: flex; gap: 8px; padding: 8px 16px; border-bottom: 1px solid var(--border); }
</style>
