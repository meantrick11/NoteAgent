<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'

import type { AuthMode, ModelConfig, ModelConfigInput } from '@/shared/api/types'
import { useModelsStore } from './store'

/**
 * 新增／编辑一个模型配置。Key 永不回显：留空表示保留已保存的那一个，
 * 要清除必须显式勾选。当前启用的配置只能“保存并启用”。
 */
const props = defineProps<{
  model: ModelConfig | null
  active: boolean
}>()

const emit = defineEmits<{ (event: 'done'): void; (event: 'cancel'): void }>()

const models = useModelsStore()

const label = ref('')
const provider = ref('deepseek')
const modelName = ref('')
const baseUrl = ref('')
const apiKey = ref('')
const authNone = ref(false)
const clearKey = ref(false)
const contextWindow = ref('32768')
const temperature = ref('')
const maxTokens = ref('')
const timeoutSeconds = ref('60')
const maxRetries = ref('1')
const labelEl = ref<HTMLInputElement | null>(null)

const spec = computed(() => models.providerSpec(provider.value))
const hasSavedKey = computed(() => Boolean(props.model?.has_api_key))
const supportsNoAuth = computed(() => spec.value?.auth_modes.includes('none') ?? false)
const keyDisabled = computed(() => authNone.value || clearKey.value)
const baseUrlRequired = computed(() => spec.value?.base_url_required ?? false)

function reset(): void {
  const model = props.model
  label.value = model?.label ?? ''
  provider.value = model?.provider ?? 'deepseek'
  modelName.value = model?.model ?? ''
  baseUrl.value = model?.base_url ?? ''
  apiKey.value = ''
  authNone.value = model?.auth_mode === 'none'
  clearKey.value = false
  contextWindow.value = String(model?.context_window ?? 32768)
  temperature.value = model?.temperature == null ? '' : String(model.temperature)
  maxTokens.value = model?.max_tokens == null ? '' : String(model.max_tokens)
  timeoutSeconds.value = String(model?.timeout_s ?? 60)
  maxRetries.value = String(model?.max_retries ?? 1)
}

function onProviderChange(): void {
  if (!spec.value?.auth_modes.includes('none')) authNone.value = false
  if (!baseUrl.value) baseUrl.value = spec.value?.default_base_url ?? ''
}

function onKeyInput(): void {
  if (apiKey.value.trim() && clearKey.value) clearKey.value = false
}

watch(() => props.model, reset, { immediate: true, deep: true })
watch(clearKey, (value) => {
  if (value) apiKey.value = ''
})

watch(
  () => props.model,
  async () => {
    await nextTick()
    labelEl.value?.focus()
  },
  { immediate: true },
)

function payload(): ModelConfigInput {
  const body: ModelConfigInput = {
    label: label.value.trim(),
    provider: provider.value,
    model: modelName.value.trim(),
    base_url: baseUrl.value.trim(),
    context_window: Number(contextWindow.value) || 0,
    timeout_s: Number(timeoutSeconds.value) || 0,
    max_retries: Number(maxRetries.value) || 0,
    auth_mode: (authNone.value ? 'none' : 'api_key') as AuthMode,
  }
  const temp = temperature.value.trim()
  const tokens = maxTokens.value.trim()
  if (temp !== '') body.temperature = Number(temp)
  if (tokens !== '') body.max_tokens = Number(tokens)
  const key = apiKey.value.trim()
  if (key) body.api_key = key
  if (clearKey.value) body.clear_api_key = true
  return body
}

async function test(): Promise<void> {
  if (!props.model) {
    models.showChatError('先保存配置，再测试连接。')
    return
  }
  await models.testConnection(props.model.id, payload())
}

async function submit(activate: boolean): Promise<void> {
  const ok = await models.submitModel(payload(), props.model, activate)
  if (ok) emit('done')
}
</script>

<template>
  <div class="ms-form">
    <div class="ms-section-title">
      {{ model ? `编辑「${model.label}」` : '新增模型配置' }}
    </div>

    <div class="ms-field">
      <label for="ms-label">配置名称</label>
      <input id="ms-label" ref="labelEl" v-model="label" class="input" type="text" />
    </div>

    <div class="ms-field">
      <label for="ms-provider">Provider</label>
      <select id="ms-provider" v-model="provider" class="input" @change="onProviderChange">
        <option v-for="item in models.providerSpecs" :key="item.id" :value="item.id">
          {{ item.label }}
        </option>
      </select>
    </div>

    <div class="ms-field">
      <label for="ms-model">模型名</label>
      <input id="ms-model" v-model="modelName" class="input" type="text" />
    </div>

    <div class="ms-field">
      <label for="ms-base-url">
        Base URL<template v-if="baseUrlRequired">（必填）</template>
      </label>
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
      <span>该服务无需 API Key</span>
    </label>

    <label v-if="hasSavedKey" class="ms-check">
      <input v-model="clearKey" type="checkbox" />
      <span>清除已保存的 Key</span>
    </label>

    <div class="ms-field">
      <label for="ms-context">上下文窗口（token）</label>
      <input id="ms-context" v-model="contextWindow" class="input" type="text" />
    </div>

    <div class="ms-grid">
      <div class="ms-field">
        <label for="ms-temp">temperature（留空用 Provider 默认）</label>
        <input id="ms-temp" v-model="temperature" class="input" type="text" />
      </div>
      <div class="ms-field">
        <label for="ms-tokens">max_tokens（留空用 Provider 默认）</label>
        <input id="ms-tokens" v-model="maxTokens" class="input" type="text" />
      </div>
      <div class="ms-field">
        <label for="ms-timeout">超时（秒）</label>
        <input id="ms-timeout" v-model="timeoutSeconds" class="input" type="text" />
      </div>
      <div class="ms-field">
        <label for="ms-retries">最大重试</label>
        <input id="ms-retries" v-model="maxRetries" class="input" type="text" />
      </div>
    </div>

    <div v-if="active" class="ms-hint">
      这是当前启用的模型：普通保存不会切换运行中的客户端，请使用「保存并启用」。
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

.ms-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
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
