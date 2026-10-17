<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useSourceFilesStore } from './store'
import * as api from './api'
import type { SourceFile } from './api'

const library = useSourceFilesStore()
const selected = ref<SourceFile | null>(null)
const textPreview = ref('')
const error = ref('')
const uploading = ref(false)

async function uploadFiles(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  uploading.value = true
  error.value = ''
  const failures: string[] = []
  try {
    for (const file of files) {
      try { await api.uploadSourceFile(file, () => {}).promise }
      catch (reason) { failures.push(`${file.name}: ${(reason as Error).message}`) }
    }
    await refresh()
    error.value = failures.join('；')
  } catch (reason) { error.value = (reason as Error).message }
  finally { uploading.value = false }
}

async function refresh(): Promise<void> {
  await library.refresh()
  if (selected.value) selected.value = library.files.find(item => item.id === selected.value?.id) ?? null
}

onMounted(() => { void refresh() })

async function open(file: SourceFile): Promise<void> {
  selected.value = file
  textPreview.value = ''
  if (file.status !== 'ready' || ['application/pdf', 'image/png', 'image/jpeg'].includes(file.media_type)) return
  try {
    const data = await fetch(api.previewUrl(file.id)).then(response => response.json()) as { fragments: Array<{ locator: string; text: string }> }
    textPreview.value = data.fragments.map(part => `[${part.locator}]\n${part.text}`).join('\n\n')
  } catch (reason) { error.value = (reason as Error).message }
}

async function rename(file: SourceFile): Promise<void> {
  const name = window.prompt('显示名称', file.display_name)
  if (!name || name === file.display_name) return
  try { await api.patchSourceFile(file.id, { display_name: name }); await refresh() }
  catch (reason) { error.value = (reason as Error).message }
}

async function move(file: SourceFile): Promise<void> {
  const folder = window.prompt('文件夹名称（留空为根目录）', file.folder)
  if (folder === null) return
  try { await api.patchSourceFile(file.id, { folder }); await refresh() }
  catch (reason) { error.value = (reason as Error).message }
}

async function remove(file: SourceFile): Promise<void> {
  if (!window.confirm(`删除来源文件“${file.display_name}”？历史消息仍保留来源名称，但 AI 将无法再读取。`)) return
  try { await api.deleteSourceFile(file.id); await refresh(); selected.value = null }
  catch (reason) { error.value = (reason as Error).message }
}

async function retry(file: SourceFile): Promise<void> {
  try { await api.retrySourceFile(file.id); await refresh() }
  catch (reason) { error.value = (reason as Error).message }
}

async function createFolder(): Promise<void> {
  const name = window.prompt('新文件夹名称')
  if (!name) return
  try { await api.createFolder(name); await refresh() }
  catch (reason) { error.value = (reason as Error).message }
}

async function renameFolder(name: string): Promise<void> {
  const next = window.prompt('新文件夹名称', name)
  if (!next || next === name) return
  try { await api.renameFolder(name, next); await refresh() }
  catch (reason) { error.value = (reason as Error).message }
}

async function removeFolder(name: string): Promise<void> {
  if (!window.confirm(`删除文件夹“${name}”？其中文件将移到根目录。`)) return
  try { await api.deleteFolder(name); await refresh() }
  catch (reason) { error.value = (reason as Error).message }
}
</script>

<template>
  <div class="source-library">
    <aside>
      <div class="toolbar"><strong>文件</strong><label class="upload-button">上传文件<input type="file" multiple :disabled="uploading" @change="uploadFiles" /></label><button type="button" @click="createFolder">新建文件夹</button><button type="button" @click="refresh">刷新</button></div>
      <p v-if="error" class="error">{{ error }}</p>
      <div v-for="folder in ['根目录', ...library.folders]" :key="folder" class="folder-group">
        <h3>{{ folder }}
          <template v-if="folder !== '根目录'"><button type="button" @click="renameFolder(folder)">重命名</button><button type="button" @click="removeFolder(folder)">删除</button></template>
        </h3>
        <button v-for="file in library.files.filter(item => item.status !== 'deleted' && item.folder === (folder === '根目录' ? '' : folder))"
          :key="file.id" type="button" class="file-row" @click="open(file)">
          <span>{{ file.display_name }}</span><small>{{ file.status }}</small>
        </button>
      </div>
    </aside>
    <main v-if="selected">
      <h2>{{ selected.display_name }}</h2>
      <p>原始文件名：{{ selected.original_filename }}</p>
      <p>类型：{{ selected.media_type }} · 大小：{{ selected.size_bytes }} 字节 · SHA-256：{{ selected.sha256 }}</p>
      <p>状态：{{ selected.status }} {{ selected.error }}</p>
      <p v-if="selected.status === 'stored'">已保存原件；此格式暂不支持聊天解析。</p>
      <div class="toolbar"><button type="button" @click="rename(selected)">重命名</button><button type="button" @click="move(selected)">移动</button><button v-if="selected.status === 'failed'" type="button" @click="retry(selected)">重试解析</button><a :href="api.downloadUrl(selected.id)">下载</a><button type="button" @click="remove(selected)">删除</button></div>
      <iframe v-if="selected.status === 'ready' && selected.media_type === 'application/pdf'" title="PDF 预览" :src="api.previewUrl(selected.id)" />
      <img v-else-if="selected.status === 'ready' && selected.media_type.startsWith('image/')" alt="文件预览" :src="api.previewUrl(selected.id)" />
      <pre v-else>{{ textPreview }}</pre>
    </main>
    <main v-else><p>选择文件查看内容</p></main>
  </div>
</template>

<style scoped>
.source-library { display: flex; flex: 1; min-width: 0; }
aside { width: 280px; border-right: 1px solid var(--border); overflow: auto; padding: 16px; }
main { flex: 1; min-width: 0; overflow: auto; padding: 20px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.upload-button { cursor: pointer; border: 1px solid var(--border); padding: 2px 6px; }
.upload-button input { display: none; }
.folder-group { margin-top: 18px; }
.folder-group h3 { font-size: 14px; }
.folder-group h3 button { margin-left: 6px; }
.file-row { width: 100%; display: flex; justify-content: space-between; margin: 5px 0; padding: 8px; border: 1px solid var(--border); background: var(--bg); text-align: left; }
.error { color: var(--danger, #b33); }
iframe { width: 100%; height: 70vh; border: 0; }
img { max-width: 100%; max-height: 70vh; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
