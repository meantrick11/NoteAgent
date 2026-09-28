<script setup lang="ts">
/**
 * Records 本轮只初始化入口与空状态。它最终承载哪些来源（视频、会议、网页…）
 * 还没有决定，所以这里不画记录列表、进度、录制按钮或任何新业务表单，
 * 只用可扩展的容器占位，等范围确定后再实现。
 */
</script>

<template>
  <section class="page">
    <div class="records-body">
      <h1 class="page-title">Records</h1>
      <p class="page-hint">本页目前只有入口，没有可用的记录来源。</p>

      <div class="card records-empty">
        <h2>尚未开放</h2>
        <p>
          这里将来会承载学习记录的来源与整理结果。在范围确定之前不提供任何操作，
          以免把讨论中的候选方案当成已实现的功能。
        </p>
      </div>

      <!-- 预留的扩展位：只有布局，没有假数据。 -->
      <div class="records-slots" aria-hidden="true">
        <div v-for="slot in 2" :key="slot" class="card records-slot"></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.records-body {
  padding: var(--space-5);
  max-width: 820px;
}

.records-empty h2 {
  font-size: 15px;
  font-weight: 650;
  margin-bottom: var(--space-2);
}

.records-empty p {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
}

.records-slots {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-3);
}

.records-slot {
  min-height: 96px;
  background: repeating-linear-gradient(
    135deg,
    var(--surface),
    var(--surface) 10px,
    var(--bg) 10px,
    var(--bg) 20px
  );
  border-style: dashed;
}
</style>
