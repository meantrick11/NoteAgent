<script setup lang="ts">
import { computed, ref } from 'vue'

import type { ToolStepState } from './sse'
import { englishSummary, hasRealTools, liveTraceLabel, toolFlowLabel, toolLiveLabel } from './trace'

const props = defineProps<{
  steps: ToolStepState[]
  live: boolean
}>()

/** 展开态归组件自己管，按步骤下标记（思考段落各自可折叠）。 */
const openThinks = ref<Set<number>>(new Set())
const listOpen = ref(false)

/** 没有真正用过工具、也不是进行中的一轮，就不显示轨迹。 */
const visible = computed(() => props.live || hasRealTools(props.steps))

const label = computed(() =>
  props.live ? liveTraceLabel(props.steps) : englishSummary(props.steps, false),
)

interface Item {
  index: number
  kind: 'think' | 'tool'
  label: string
  body: string
  running: boolean
  collapsible: boolean
}

const items = computed<Item[]>(() =>
  props.steps.flatMap((step, index): Item[] => {
    // _gen 是"正在生成答案"的内部占位，不进列表。
    if (step.name === '_gen') return []
    if (step.name === '_think') {
      const body = step.content ?? ''
      const hasBody = Boolean(body.trim())
      // 想完了又没有留下内容：没必要占一行。
      if (step.status && !hasBody) return []
      return [
        {
          index,
          kind: 'think',
          label: step.status ? 'Thought' : 'Thinking...',
          body,
          running: !step.status,
          collapsible: hasBody,
        },
      ]
    }
    const running = !step.status
    return [
      {
        index,
        kind: 'tool',
        label: running ? toolLiveLabel(step) : toolFlowLabel(step),
        body: '',
        running,
        collapsible: false,
      },
    ]
  }),
)

function toggleThink(index: number): void {
  const next = new Set(openThinks.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  openThinks.value = next
}
</script>

<template>
  <div v-if="visible" class="msg-trace" :class="{ open: listOpen }">
    <button
      type="button"
      class="msg-trace-head"
      :class="{ live }"
      aria-haspopup="true"
      :aria-expanded="listOpen"
      @click="listOpen = !listOpen"
    >
      <span class="msg-trace-label">{{ label }}</span>
      <span class="msg-trace-chevron" aria-hidden="true">▼</span>
    </button>
    <ul class="msg-trace-list">
      <li
        v-for="item in items"
        :key="item.index"
        :class="{ live: item.running, 'step-think': item.kind === 'think', open: openThinks.has(item.index) }"
      >
        <template v-if="item.collapsible">
          <button type="button" class="step-think-head" @click.stop="toggleThink(item.index)">
            <span>{{ item.label }}</span>
            <span class="msg-trace-chevron" aria-hidden="true">▼</span>
          </button>
          <div class="step-think-body">{{ item.body }}</div>
        </template>
        <template v-else>{{ item.label }}</template>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.msg-trace {
  margin: 0 0 6px;
  padding: 0 2px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.msg-trace-head {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  max-width: 100%;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.msg-trace-head:hover {
  color: var(--text);
}

.msg-trace-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-trace-head.live .msg-trace-label,
.msg-trace-list li.live {
  animation: msg-trace-pulse 1.1s ease-in-out infinite;
}

@keyframes msg-trace-pulse {
  50% {
    opacity: 0.4;
  }
}

.msg-trace-chevron {
  flex-shrink: 0;
  line-height: 1;
}

.msg-trace.open > .msg-trace-head .msg-trace-chevron,
.step-think.open .msg-trace-chevron {
  transform: rotate(180deg);
}

.msg-trace-list {
  display: none;
  margin: 6px 0 0;
  padding: 0;
  list-style: none;
}

.msg-trace.open .msg-trace-list {
  display: block;
}

.msg-trace-list li {
  margin: 2px 0;
}

.step-think-head {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.step-think-body {
  display: none;
  margin: 4px 0 8px 8px;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  color: var(--text-secondary);
}

.step-think.open .step-think-body {
  display: block;
}
</style>
