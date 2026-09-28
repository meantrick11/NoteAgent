<script setup lang="ts">
import { computed, ref } from 'vue'

import { confirmDialog } from '@/shared/ui/confirm'
import type { ChatProfile } from '@/shared/api/types'
import ChatProfileForm from './ChatProfileForm.vue'
import { useModelsStore } from './store'

/** 聊天配置列表 + 新增／编辑表单。Settings 页与 Assistant 快捷弹层共用。 */
const models = useModelsStore()

const editing = ref<ChatProfile | null>(null)
const forming = ref(false)

const PROVIDER_TEXT: Record<string, string> = {
  deepseek: 'DeepSeek',
  'openai-compatible': 'OpenAI 兼容',
}

const editIsActive = computed(
  () => Boolean(editing.value && models.activeChat?.id === editing.value.id),
)

function openForm(profile: ChatProfile | null): void {
  editing.value = profile
  forming.value = true
  models.showChatError('')
  models.showChatOk('')
}

function closeForm(): void {
  forming.value = false
  editing.value = null
}

async function remove(profile: ChatProfile): Promise<void> {
  const ok = await confirmDialog({
    title: '删除配置',
    body: `删除配置「${profile.label}」？该配置保存的 Key 会一并删除，且无法恢复。`,
  })
  if (!ok) return
  await models.deleteProfile(profile)
}

function credentialText(profile: ChatProfile): string {
  return profile.credential_source === 'env'
    ? '凭据来自环境'
    : profile.has_api_key
      ? '已保存 Key'
      : '无需 Key'
}
</script>

<template>
  <div class="chat-profiles">
    <p v-if="!models.chatProfiles.length" class="ms-row-sub">
      还没有保存过聊天配置，下面新增一个即可。
    </p>

    <div
      v-for="profile in models.chatProfiles"
      :key="profile.id"
      class="ms-row"
      :class="{ active: models.activeChat?.id === profile.id }"
    >
      <div class="ms-row-main">
        <div class="ms-row-title">{{ profile.label }}</div>
        <div class="ms-row-sub">
          {{ PROVIDER_TEXT[profile.provider] || profile.provider }} · {{ profile.model }}
        </div>
        <div class="ms-row-sub">
          {{ credentialText(profile) }}
          <template v-if="profile.base_url"> · {{ profile.base_url }}</template>
          · 上下文 {{ profile.context_window }}
        </div>
      </div>

      <span v-if="models.activeChat?.id === profile.id" class="chip chip-on">已启用</span>
      <button
        v-else
        type="button"
        class="ms-chip-button"
        :disabled="models.modelActionsLocked"
        @click="models.activateProfile(profile.id)"
      >
        启用
      </button>

      <button
        type="button"
        class="btn"
        :disabled="models.modelActionsLocked"
        @click="openForm(profile)"
      >
        编辑
      </button>
      <!-- 只有显式删除才会移除配置和它的 Key；当前启用的那条必须先切换走。 -->
      <button
        v-if="models.activeChat?.id !== profile.id"
        type="button"
        class="btn"
        :disabled="models.modelActionsLocked"
        @click="remove(profile)"
      >
        删除
      </button>
    </div>

    <p v-if="!models.retrievalAvailable && models.retrievalProblem" class="ms-row-sub">
      {{ models.retrievalProblem }}
    </p>

    <div class="ms-actions">
      <button type="button" class="btn" @click="openForm(null)">＋ 新增配置</button>
    </div>

    <ChatProfileForm
      v-if="forming"
      :profile="editing"
      :active="editIsActive"
      @done="closeForm"
      @cancel="closeForm"
    />

    <p v-if="models.chatNotice" class="ms-notice" :class="`ms-${models.chatNotice.kind}`">
      {{ models.chatNotice.text }}
    </p>
  </div>
</template>

<style scoped>
.ms-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  margin-bottom: var(--space-2);
  background: var(--surface);
}

.ms-row.active {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.ms-row-main {
  flex: 1;
  min-width: 0;
}

.ms-row-title {
  font-size: 13px;
  font-weight: 600;
}

.ms-row-sub {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.chip-on {
  background: var(--ok-bg);
  color: var(--ok-text);
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  flex-shrink: 0;
}

.ms-chip-button {
  flex-shrink: 0;
  font-size: 11px;
  font-family: inherit;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border);
  background: var(--surface);
  cursor: pointer;
}

.ms-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.ms-notice {
  margin-top: var(--space-2);
  font-size: 12px;
  line-height: 1.5;
}

.ms-ok {
  color: var(--ok-text);
}

.ms-error {
  color: var(--danger);
}
</style>
