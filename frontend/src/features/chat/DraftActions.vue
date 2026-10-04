<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useModelsStore } from '@/features/models/store'
import { draftApproveLabel, draftAsk, draftOverrideAvailable, useChatStore } from './store'

const chat = useChatStore()
const models = useModelsStore()
const draft = computed(() => chat.panel.draft)
const busy = computed(() => chat.panel.busy || !models.canSend)
const appendOpen = ref(false)
const target = ref('')
const appendSelect = ref<HTMLSelectElement | null>(null)

watch(() => [chat.currentId, draft.value?.action, draft.value?.file_name], () => { appendOpen.value = false; target.value = '' })
async function openAppend(): Promise<void> {
  appendOpen.value = !appendOpen.value
  if (appendOpen.value) {
    target.value = draft.value?.existing_files?.[0] ?? ''
    await nextTick()
    appendSelect.value?.focus()
  }
}
function submitAppend(): void {
  if (busy.value || !target.value) return
  void chat.reviewDraft({ action: 'override', write_action: 'append', file_name: target.value })
}
</script>

<template>
  <div v-if="draft" class="draft-pane-actions">
    <p class="draft-pane-ask">{{ draftAsk(draft) }}</p>
    <div class="draft-pane-buttons">
      <button type="button" class="btn btn-primary" data-act="approve" :disabled="busy"
        @click="chat.reviewDraft({ action: 'approve' })">{{ draftApproveLabel(draft.action) }}</button>
      <button type="button" class="btn" data-act="reject" :disabled="busy"
        @click="chat.reviewDraft({ action: 'reject' })">拒绝</button>
      <button v-if="draftOverrideAvailable(draft)" type="button" class="btn" :disabled="busy"
        :aria-expanded="appendOpen" @click="openAppend">追加到笔记</button>
    </div>
    <div v-if="appendOpen" class="draft-pane-form" @keydown.esc.stop.prevent="appendOpen = false">
      <label for="cite-pane-append-target">追加到笔记</label>
      <select id="cite-pane-append-target" ref="appendSelect" v-model="target" :disabled="busy">
        <option value="" disabled>请选择目标笔记</option>
        <option v-for="name in draft.existing_files ?? []" :key="name" :value="name">{{ name }}</option>
      </select>
      <span v-if="!draft.existing_files?.length" class="hint">暂无可追加的笔记</span>
      <button type="button" :disabled="busy || !target" @click="submitAppend">追加到所选笔记</button>
      <button type="button" :disabled="busy" @click="appendOpen = false">取消追加</button>
    </div>
  </div>
</template>

<style scoped>
.draft-pane-actions { flex-shrink: 0; border-top: 1px solid var(--border); padding: 10px 12px 12px; display: flex; flex-direction: column; gap: var(--space-2); }
.draft-pane-ask { margin: 0; font-size: 13px; line-height: 1.6; }
.draft-pane-buttons, .draft-pane-form { display: flex; flex-wrap: wrap; gap: var(--space-2); align-items: center; }
button:disabled { opacity: 0.4; cursor: not-allowed; }
.draft-pane-form label, .hint { font-size: 12px; color: var(--text-secondary); }
.draft-pane-form button, .draft-pane-form select { max-width: 100%; font-size: 13px; font-family: inherit; padding: 6px 10px; border-radius: var(--radius-sm); border: 1px solid var(--border); background: var(--bg); color: var(--text); }
</style>
