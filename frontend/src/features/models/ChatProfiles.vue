<script setup lang="ts">
import { computed, ref } from 'vue'

import { alertDialog, confirmDialog } from '@/shared/ui/confirm'
import type { ChatProfile } from '@/shared/api/types'
import ChatProfileForm from './ChatProfileForm.vue'
import { useModelsStore } from './store'
import { disableCapability, verifyCapability } from './api'

/** 聊天配置列表 + 新增／编辑表单。Settings 页与 Assistant 快捷弹层共用。 */
const models = useModelsStore()

const editing = ref<ChatProfile | null>(null)
const forming = ref(false)
const verifying = ref<string | null>(null)
const capabilityAction = ref<'verify' | 'disable'>('verify')

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

async function changeCapability(profile: ChatProfile, capability: 'text' | 'vision'): Promise<void> {
  if (verifying.value || models.modelActionsLocked || forming.value) return
  verifying.value = `${profile.id}:${capability}`
  try {
    await models.refreshIfStale()
    const current = models.chatProfiles.find(item => item.id === profile.id)
    if (!current) throw new Error('配置已被删除，请刷新页面')
    const verified = current.verified_capabilities?.includes(capability) ?? false
    capabilityAction.value = verified ? 'disable' : 'verify'
    if (verified) await disableCapability(profile.id, capability, models.revision)
    else await verifyCapability(profile.id, capability, models.revision)
    await models.fetchStatus(true)
  } catch (error) {
    try {
      await models.fetchStatus(true)
    } catch (refreshError) {
      models.showChatError((refreshError as Error).message)
    }
    verifying.value = null
    await alertDialog('能力验证失败', (error as Error).message)
  } finally {
    verifying.value = null
  }
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

      <div class="ms-capabilities" aria-label="模型能力">
        <button v-for="capability in (['text', 'vision'] as const)" :key="capability"
          type="button" class="ms-capability"
          :class="[{ verified: profile.verified_capabilities?.includes(capability) }, `cap-${capability}`]"
          :aria-label="capability"
          :title="profile.verified_capabilities?.includes(capability) ? `点击关闭 ${capability} 能力` : `点击验证 ${capability} 能力`"
          :disabled="models.modelActionsLocked || Boolean(verifying) || forming"
          @click="changeCapability(profile, capability)"
        >{{ verifying === `${profile.id}:${capability}` ? (capabilityAction === 'verify' ? '验证中' : '关闭中') : capability }}</button>
      </div>

      <template v-if="models.activeChat?.id === profile.id">
        <span class="chip chip-on">已启用</span>
        <span v-if="profile.text_enabled === false" class="chip chip-paused">聊天暂停</span>
      </template>
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

.chip-paused {
  background: var(--warn-bg);
  color: var(--warn-text);
  padding: 1px 6px;
  border-radius: var(--radius-pill);
  font-size: 11px;
  flex-shrink: 0;
}

.ms-capabilities { display: flex; gap: 4px; flex-wrap: wrap; }
.ms-capability { border: 1px solid var(--border); border-radius: var(--radius-pill); background: var(--surface); color: var(--text-secondary); padding: 3px 8px; cursor: pointer; font-size: 11px; }
.ms-capability.verified.cap-text { background: var(--accent-soft); color: var(--accent-hover); border-color: var(--accent); }
.ms-capability.verified.cap-vision { background: #f3e8ff; color: #6b21a8; border-color: #a855f7; }

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
