<script setup lang="ts">
import { nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'

import { useModelsStore } from '@/features/models/store'
import { useChatStore } from './store'
import { useSourceFilesStore } from '@/features/source-files/store'
import { getSourceFile, retrySourceFile, uploadSourceFile } from '@/features/source-files/api'
import type { SourceFile } from '@/features/source-files/api'

const chat = useChatStore()
const models = useModelsStore()
const library = useSourceFilesStore()

interface AttachmentItem {
  key: string
  file?: File
  id?: string
  name: string
  status: 'uploading' | 'stored' | 'queued' | 'parsing' | 'ready' | 'failed'
  progress: number
  error: string
  cancel?: () => void
}
const attachments = ref<AttachmentItem[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const libraryOpen = ref(false)
let disposed = false

function remove(item: AttachmentItem): void {
  item.cancel?.()
  attachments.value = attachments.value.filter(value => value.key !== item.key)
}

function clearAttachments(): void {
  for (const item of attachments.value) item.cancel?.()
  attachments.value = []
}

watch(() => chat.currentId, clearAttachments)
onBeforeUnmount(() => { disposed = true; clearAttachments() })

async function followStatus(item: AttachmentItem): Promise<void> {
  while (!disposed && attachments.value.includes(item) && item.id) {
    try {
      const latest = await getSourceFile(item.id)
      item.status = latest.status === 'deleted' ? 'failed' : latest.status
      item.error = latest.status === 'stored'
        ? '已保存到文件库；该格式暂不支持聊天解析，请移除此附件后发送。'
        : latest.error ?? ''
    } catch (error) {
      item.error = `状态查询失败：${(error as Error).message}`
      return
    }
    if (item.status === 'ready' || item.status === 'failed' || item.status === 'stored') return
    await new Promise(resolve => setTimeout(resolve, 1000))
  }
}

async function upload(item: AttachmentItem): Promise<void> {
  if (!item.file) return
  item.status = 'uploading'
  item.error = ''
  const request = uploadSourceFile(item.file, progress => { item.progress = progress })
  item.cancel = request.cancel
  try {
    const source = await request.promise
    item.cancel = undefined
    if (!attachments.value.includes(item)) return
    if (attachments.value.some(other => other !== item && other.id === source.id)) {
      remove(item)
      return
    }
    item.id = source.id
    item.status = source.status === 'deleted' ? 'failed' : source.status
    if (item.status === 'stored') item.error = '已保存到文件库；该格式暂不支持聊天解析，请移除此附件后发送。'
    await followStatus(item)
  } catch (error) {
    if (attachments.value.includes(item)) { item.status = 'failed'; item.error = (error as Error).message }
  }
}

function addFiles(files: FileList | File[]): void {
  for (const file of Array.from(files)) {
    if (attachments.value.length >= 5) break
    const item = reactive<AttachmentItem>({
      key: crypto.randomUUID(), file, name: file.name,
      status: 'uploading', progress: 0, error: '',
    })
    attachments.value.push(item)
    if (file.size > 20 * 1024 * 1024) {
      item.status = 'failed'; item.error = '文件超过 20 MB'
    } else void upload(item)
  }
  if (fileInput.value) fileInput.value.value = ''
}

async function retry(item: AttachmentItem): Promise<void> {
  if (item.id) {
    if (item.status !== 'failed') { item.error = ''; void followStatus(item); return }
    try { const source = await retrySourceFile(item.id); item.status = source.status === 'deleted' ? 'failed' : source.status; void followStatus(item) }
    catch (error) { item.error = (error as Error).message }
  } else void upload(item)
}

async function openLibrary(): Promise<void> {
  libraryOpen.value = !libraryOpen.value
  if (libraryOpen.value) await library.refresh()
}

function selectExisting(file: SourceFile): void {
  if (file.status !== 'ready' || attachments.value.length >= 5 || attachments.value.some(item => item.id === file.id)) return
  attachments.value.push({ key: crypto.randomUUID(), id: file.id, name: file.display_name, status: 'ready', progress: 100, error: '' })
  libraryOpen.value = false
}

function onDrop(event: DragEvent): void {
  event.preventDefault()
  if (event.dataTransfer?.files) addFiles(event.dataTransfer.files)
}

const text = ref('')
const box = ref<HTMLTextAreaElement | null>(null)

/** 发送按钮的禁用状态 = 空输入 或 维护窗口，两者都不能被对方覆盖。 */
const sendDisabled = () => !models.canChat || !!chat.activeRun ||
  (text.value.trim().length === 0 && attachments.value.length === 0) ||
  attachments.value.some(item => item.status !== 'ready')

function resize(): void {
  const el = box.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`
}

async function restoreIfEmpty(question: string): Promise<void> {
  // 只在输入框仍为空时恢复，避免覆盖用户随后打的新字。
  if (text.value.trim()) return
  text.value = question
  await nextTick()
  resize()
}

async function send(): Promise<void> {
  const question = text.value.trim()
  if (!question && attachments.value.length === 0) return
  if (chat.streaming) return
  if (!models.canChat) {
    // 维护窗口或 text 暂停：保留输入，并在聊天区说明原因。
    chat.notifyUnavailable()
    return
  }
  if (sendDisabled()) return
  text.value = ''
  await nextTick()
  resize()
  const selected = attachments.value.map(item => ({ id: item.id!, name: item.name }))
  const outcome = await chat.send(question || '请分析附件内容', selected)
  if (outcome === 'failed' || outcome === 'refused') await restoreIfEmpty(question)
  else { clearAttachments(); await nextTick() }
  box.value?.focus()
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void send()
  }
}
</script>

<template>
  <div class="input-area" @dragover.prevent @drop="onDrop">
    <div v-if="chat.activeRun && !chat.streaming" class="resume-bar" role="status">
      <span>{{ ['interrupted', 'prepared'].includes(chat.activeRun.status) ? '上一条回复已中断，可继续生成。' : '上一条回复仍在处理中。' }}</span>
      <button v-if="['interrupted', 'prepared'].includes(chat.activeRun.status)" type="button"
        :disabled="!models.canChat" @click="chat.resumeRun()">继续生成</button>
      <button v-else type="button" @click="chat.currentId && chat.loadMessages(chat.currentId)">刷新状态</button>
    </div>
    <div class="input-inner">
      <input ref="fileInput" class="file-input" type="file" multiple @change="event => addFiles((event.target as HTMLInputElement).files!)" />
      <button type="button" class="btn" title="上传文件" @click="fileInput?.click()">＋</button>
      <button type="button" class="btn" @click="openLibrary">文件库</button>
      <textarea
        ref="box"
        v-model="text"
        rows="1"
        placeholder="输入你的问题…"
        aria-label="输入你的问题"
        @input="resize"
        @keydown="onKeydown"
      ></textarea>
      <button
        type="button"
        class="btn-send"
        aria-label="发送"
        :disabled="sendDisabled()"
        @click="send"
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <line x1="12" y1="19" x2="12" y2="5" />
          <polyline points="5 12 12 5 19 12" />
        </svg>
      </button>
    </div>
    <div v-if="libraryOpen" class="file-picker">
      <button v-for="file in library.files.filter(item => item.status === 'ready')" :key="file.id" type="button" @click="selectExisting(file)">{{ file.display_name }}</button>
    </div>
    <div v-if="attachments.length" class="attachment-list">
      <div v-for="item in attachments" :key="item.key" class="attachment-chip">
        <span>{{ item.name }} · {{ item.status === 'uploading' ? `${item.progress}%` : item.status }}</span>
        <span v-if="item.error" class="attachment-error">{{ item.error }}</span>
        <button v-if="item.status === 'failed' || (!!item.id && !!item.error && item.status !== 'stored')" type="button" @click="retry(item)">重试</button>
        <button type="button" aria-label="移除附件" @click="remove(item)">×</button>
      </div>
    </div>
    <slot />
  </div>
</template>

<style scoped>
.input-area {
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: var(--space-4) var(--space-5);
}
.file-input { display: none; }
.file-picker, .attachment-list { max-width: 900px; margin: 8px auto 0; display: flex; flex-wrap: wrap; gap: 8px; }
.file-picker button, .attachment-chip { border: 1px solid var(--border); border-radius: 6px; padding: 5px 8px; background: var(--bg); }
.attachment-chip { display: flex; gap: 6px; align-items: center; }
.attachment-chip button { border: 0; background: none; cursor: pointer; }
.attachment-error { color: var(--danger, #b33); }

.resume-bar {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  color: var(--text-secondary);
}

.input-inner {
  max-width: calc((100% + 768px) / 2);
  margin: 0 auto;
  display: flex;
  gap: 10px;
  align-items: flex-end;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 12px;
  transition: border-color 0.15s;
}

.input-inner:focus-within {
  border-color: var(--accent);
  box-shadow: var(--focus-ring);
}

textarea {
  flex: 1;
  border: none;
  outline: none;
  background: transparent;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  min-height: 24px;
  max-height: 200px;
  padding: 4px 0;
  color: var(--text);
}

.btn-send {
  width: 34px;
  height: 34px;
  border-radius: var(--radius-sm);
  border: none;
  background: var(--accent);
  color: #fff;
  cursor: pointer;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.btn-send:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
