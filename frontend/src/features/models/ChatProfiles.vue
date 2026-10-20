<script setup lang="ts">
import { computed, ref } from 'vue'

import { alertDialog, confirmDialog } from '@/shared/ui/confirm'
import type { CapabilityRecord, ModelConfig } from '@/shared/api/types'
import ChatProfileForm from './ChatProfileForm.vue'
import { useModelsStore } from './store'

/** 模型配置列表 + 新增／编辑表单。Settings 页与 Assistant 快捷弹层共用。 */
const models = useModelsStore()

const editing = ref<ModelConfig | null>(null)
const forming = ref(false)
const verifying = ref<string | null>(null)

const editIsActive = computed(
  () => Boolean(editing.value && models.activeModel?.id === editing.value.id),
)

function openForm(model: ModelConfig | null): void {
  editing.value = model
  forming.value = true
  models.showChatError('')
  models.showChatOk('')
}

function closeForm(): void {
  forming.value = false
  editing.value = null
}

function providerLabel(provider: string): string {
  return models.providerSpec(provider)?.label ?? provider
}

function capabilityRecord(model: ModelConfig, capability: 'text' | 'vision'): CapabilityRecord | undefined {
  return model.capabilities.find(item => item.capability === capability)
}

function capabilityVerified(model: ModelConfig, capability: 'text' | 'vision'): boolean {
  const record = capabilityRecord(model, capability)
  return record?.verification === 'verified' && record?.status === 'enabled'
}

function capabilityPaused(model: ModelConfig, capability: 'text' | 'vision'): boolean {
  return capabilityRecord(model, capability)?.status === 'disabled'
}

function credentialText(model: ModelConfig): string {
  return model.auth_mode === 'none'
    ? '无需 Key'
    : model.has_api_key
      ? '已保存 Key'
      : '未配置 Key'
}

async function remove(model: ModelConfig): Promise<void> {
  const ok = await confirmDialog({
    title: '删除模型配置',
    body: `删除配置「${model.label}」？该配置保存的 Key 会一并删除，且无法恢复。`,
  })
  if (!ok) return
  await models.removeModel(model)
}

async function changeCapability(model: ModelConfig, capability: 'text' | 'vision'): Promise<void> {
  if (verifying.value || models.modelActionsLocked || forming.value) return
  verifying.value = `${model.id}:${capability}`
  try {
    await models.changeCapability(model, capability)
  } catch (error) {
    verifying.value = null
    await alertDialog('能力验证失败', (error as Error).message)
  } finally {
    verifying.value = null
  }
}
</script>

<template>
  <div class="chat-profiles">
    <p v-if="!models.models.length" class="ms-row-sub">
      还没有保存过模型配置，下面新增一个即可。
    </p>

    <div
      v-for="model in models.models"
      :key="model.id"
      class="ms-row"
      :class="{ active: models.activeModel?.id === model.id }"
    >
      <div class="ms-row-main">
        <div class="ms-row-title">{{ model.label }}</div>
        <div class="ms-row-sub">
          {{ providerLabel(model.provider) }} · {{ model.model }}
        </div>
        <div class="ms-row-sub">
          {{ credentialText(model) }}
          <template v-if="model.base_url"> · {{ model.base_url }}</template>
          · 上下文 {{ model.context_window }}
        </div>
      </div>

      <div class="ms-capabilities" aria-label="模型能力">
        <button v-for="capability in (['text', 'vision'] as const)" :key="capability"
          type="button" class="ms-capability"
          :class="[
            { verified: capabilityVerified(model, capability), paused: capabilityPaused(model, capability) },
            `cap-${capability}`,
          ]"
          :aria-label="capability"
          :title="capabilityVerified(model, capability) ? `点击关闭 ${capability} 能力` : `点击验证 ${capability} 能力`"
          :disabled="models.modelActionsLocked || Boolean(verifying) || forming"
          @click="changeCapability(model, capability)"
        >{{ verifying === `${model.id}:${capability}` ? '验证中' : capability }}</button>
      </div>

      <template v-if="models.activeModel?.id === model.id">
        <span class="chip chip-on">已启用</span>
        <span v-if="capabilityPaused(model, 'text')" class="chip chip-paused">聊天暂停</span>
      </template>
      <button
        v-else
        type="button"
        class="ms-chip-button"
        :disabled="models.modelActionsLocked"
        @click="models.activateExisting(model)"
      >
        启用
      </button>

      <button
        type="button"
        class="btn"
        :disabled="models.modelActionsLocked"
        @click="openForm(model)"
      >
        编辑
      </button>
      <button
        v-if="models.activeModel?.id !== model.id"
        type="button"
        class="btn"
        :disabled="models.modelActionsLocked"
        @click="remove(model)"
      >
        删除
      </button>
    </div>

    <p v-if="!models.retrievalAvailable && models.retrievalProblem" class="ms-row-sub">
      {{ models.retrievalProblem }}
    </p>

    <div class="ms-actions">
      <button type="button" class="btn" @click="openForm(null)">＋ 新增模型</button>
    </div>

    <ChatProfileForm
      v-if="forming"
      :model="editing"
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
.ms-capability.paused { opacity: 0.6; text-decoration: line-through; }

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
