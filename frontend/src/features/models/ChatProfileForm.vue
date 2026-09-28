<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import type { AuthMode, ChatProfile, ChatProfileInput, ChatProviderName } from '@/shared/api/types'
import { useModelsStore } from './store'

/**
 * 新增／编辑一个聊天配置。Key 永不回显：留空表示保留已保存的那一个，
 * 要清除必须显式勾选。当前启用的配置不能走普通保存，只能「保存并启用」。
 */
const props = defineProps<{
  profile: ChatProfile | null
  active: boolean
}>()

const emit = defineEmits<{ (event: 'done'): void; (event: 'cancel'): void }>()

const models = useModelsStore()

const label = ref('')
const provider = ref<ChatProviderName>('deepseek')
const model = ref('')
const baseUrl = ref('')
const apiKey = ref('')
const authNone = ref(false)
const clearKey = ref(false)
const contextWindow = ref('32768')
const labelEl = ref<HTMLInputElement | null>(null)

const hasSavedKey = computed(() => Boolean(props.profile?.has_api_key))

/** 只有 OpenAI 兼容服务才谈得上"无需认证"。 */
const supportsNoAuth = computed(() => provider.value !== 'deepseek')
const keyDisabled = computed(() => authNone.value || clearKey.value)

function reset(): void {
  const profile = props.profile
  label.value = profile ? profile.label : ''
  provider.value = profile ? profile.provider : 'deepseek'
  model.value = profile ? profile.model : ''
  baseUrl.value = profile ? profile.base_url : ''
  apiKey.value = ''
  authNone.value = profile ? profile.auth_mode === 'none' : false
  clearKey.value = false
  contextWindow.value = profile ? String(profile.context_window) : '32768'
}

function onProviderChange(): void {
  if (provider.value === 'deepseek') authNone.value = false
}

function onKeyInput(): void {
  // 输入新 Key 与"清除"是互斥意图，服务端也会拒绝同时提交。
  if (apiKey.value.trim() && clearKey.value) clearKey.value = false
}

watch(() => props.profile, reset, { immediate: true, deep: true })
watch(clearKey, (value) => {
  if (value) apiKey.value = ''
})

watch(
  () => props.profile,
  async () => {
    await nextTick()
    labelEl.value?.focus()
  },
  { immediate: true },
)

function payload(): ChatProfileInput {
  const body: ChatProfileInput = {
    label: label.value.trim(),
    provider: provider.value,
    model: model.value.trim(),
    base_url: baseUrl.value.trim(),
    context_window: Number(contextWindow.value) || 0,
    auth_mode: (authNone.value ? 'none' : 'api_key') as AuthMode,
  }
  if (props.profile) body.id = props.profile.id
  const key = apiKey.value.trim()
  if (key) body.api_key = key
  if (clearKey.value) body.clear_api_key = true
  return body
}

async function test(): Promise<void> {
  await models.testConnection(payload())
}

async function submit(activate: boolean): Promise<void> {
  const ok = await models.submitProfile(payload(), props.profile?.id ?? null, activate)
  if (ok) emit('done')
}
</script>

<template>
  <div class="ms-form">
    <div class="ms-section-title">
      {{ profile ? `编辑「${profile.label}」` : '新增聊天配置' }}
    </div>

    <div class="ms-field">
      <label for="ms-label">配置名称</label>
      <input id="ms-label" ref="labelEl" v-model="label" class="input" type="text" />
    </div>

    <div class="ms-field">
      <label for="ms-provider">provider</label>
      <select id="ms-provider" v-model="provider" class="input" @change="onProviderChange">
        <option value="deepseek">DeepSeek</option>
        <option value="openai-compatible">OpenAI 兼容</option>
      </select>
    </div>

    <div class="ms-field">
      <label for="ms-model">模型名</label>
      <input id="ms-model" v-model="model" class="input" type="text" />
    </div>

    <div class="ms-field">
      <label for="ms-base-url">Base URL</label>
      <input id="ms-base-url" v-model="baseUrl" class="input" type="text" />
      <div class="ms-hint">
        填服务根地址，例如 http://localhost:1234/v1；不要填 /chat/completions
      </div>
    </div>

    <div class="ms-field">
      <label for="ms-key">API Key</label>
      <input
        id="ms-key"
        v-model="apiKey"
        class="input"
        type="password"
        autocomplete="new-password"
        :disabled="keyDisabled"
        :placeholder="hasSavedKey ? '留空保留已保存的 Key' : ''"
        @input="onKeyInput"
      />
    </div>

    <label v-if="supportsNoAuth" class="ms-check">
      <input v-model="authNone" type="checkbox" />
      <span>该服务无需 API Key（仅限本地兼容服务）</span>
    </label>

    <label v-if="hasSavedKey" class="ms-check">
      <input v-model="clearKey" type="checkbox" />
      <span>清除已保存的 Key（该配置将不再带凭据）</span>
    </label>

    <div class="ms-hint">
      留空即保留已保存的 Key；只有勾选「清除」或删除该配置才会移除它。
    </div>

    <div class="ms-field">
      <label for="ms-context">上下文窗口（token）</label>
      <input id="ms-context" v-model="contextWindow" class="input" type="text" />
      <div class="ms-hint">
        用于上下文压缩预算；按服务实际能力填写，不会根据模型名猜测
      </div>
    </div>

    <div v-if="active" class="ms-hint">
      这是当前启用的配置：请用「保存并启用」提交，普通保存会改变文件却不更换正在运行的客户端。
    </div>

    <div class="ms-actions">
      <button type="button" class="btn" :disabled="models.formBusy" @click="test">测试连接</button>
      <button
        v-if="!active"
        type="button"
        class="btn"
        :disabled="models.formBusy"
        @click="submit(false)"
      >
        保存
      </button>
      <button
        type="button"
        class="btn btn-primary"
        :disabled="models.formBusy"
        @click="submit(true)"
      >
        保存并启用
      </button>
      <button type="button" class="btn" @click="emit('cancel')">取消</button>
    </div>
  </div>
</template>

<style scoped>
.ms-form {
  border-top: 1px solid var(--border);
  margin-top: var(--space-3);
  padding-top: var(--space-3);
}

.ms-section-title {
  font-weight: 600;
  margin-bottom: var(--space-2);
}

.ms-field {
  margin-bottom: var(--space-3);
}

.ms-field label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: var(--space-1);
}

.ms-field .input {
  width: 100%;
}

.ms-hint {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.ms-check {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: var(--space-2);
}

.ms-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
</style>
