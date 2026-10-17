import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from './api'
import type { SourceFile } from './api'

export const useSourceFilesStore = defineStore('source-files', () => {
  const files = ref<SourceFile[]>([])
  const folders = ref<string[]>([])
  const busy = ref(false)

  async function refresh(): Promise<void> {
    busy.value = true
    try {
      const [items, list] = await Promise.all([api.listSourceFiles(), api.listFolders()])
      files.value = items
      folders.value = list.folders
    } finally { busy.value = false }
  }

  async function update(id: string): Promise<SourceFile> {
    const item = await api.getSourceFile(id)
    files.value = files.value.map(old => old.id === id ? item : old)
    return item
  }

  return { files, folders, busy, refresh, update }
})
