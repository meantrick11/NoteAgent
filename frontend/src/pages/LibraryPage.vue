<script setup lang="ts">
import { onMounted } from 'vue'

import NoteEditor from '@/features/notes/NoteEditor.vue'
import NoteTree from '@/features/notes/NoteTree.vue'
import { useNotesStore } from '@/features/notes/store'

const notes = useNotesStore()

onMounted(() => {
  void notes.loadCatalog()
})
</script>

<template>
  <section class="library-page">
    <NoteTree />
    <NoteEditor />
  </section>
</template>

<style scoped>
.library-page {
  flex: 1;
  min-height: 0;
  display: flex;
}
</style>
