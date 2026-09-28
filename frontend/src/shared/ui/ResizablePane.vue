<script setup lang="ts">
/**
 * 一条可拖拽、可键盘调整的分隔线。
 *
 * 只负责呈现与转发交互意图，宽度计算在 features/chat/layout.ts 里；
 * ARIA 值必须跟着实际生效的宽度走，否则窄屏收边后读屏会读出假值。
 */
defineProps<{
  label: string
  value: number
  min: number
  max: number
  hidden?: boolean
  dragging?: boolean
}>()

const emit = defineEmits<{
  (event: 'pointerdown', payload: PointerEvent): void
  (event: 'pointermove', payload: PointerEvent): void
  (event: 'pointerup'): void
  (event: 'keydown', payload: KeyboardEvent): void
}>()
</script>

<template>
  <div
    v-show="!hidden"
    class="pane-resize-handle"
    :class="{ dragging }"
    role="separator"
    aria-orientation="vertical"
    :aria-label="label"
    tabindex="0"
    :aria-valuemin="min"
    :aria-valuemax="max"
    :aria-valuenow="value"
    @pointerdown="emit('pointerdown', $event)"
    @pointermove="emit('pointermove', $event)"
    @pointerup="emit('pointerup')"
    @pointercancel="emit('pointerup')"
    @keydown="emit('keydown', $event)"
  ></div>
</template>

<style scoped>
.pane-resize-handle {
  flex: 0 0 8px;
  align-self: stretch;
  cursor: col-resize;
  position: relative;
  margin: 0 -4px;
  z-index: 5;
  touch-action: none;
  background: transparent;
}

.pane-resize-handle::after {
  content: '';
  position: absolute;
  left: 3px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: transparent;
}

.pane-resize-handle:hover::after,
.pane-resize-handle:focus-visible::after,
.pane-resize-handle.dragging::after {
  background: var(--accent);
}

.pane-resize-handle:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.pane-resize-handle.dragging {
  cursor: col-resize;
}
</style>
