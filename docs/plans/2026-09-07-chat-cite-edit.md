# 气泡对齐与聊天侧栏编辑

> 本日实现规格。不新增 HTTP。不改检索入库实现。聊天出处侧栏保存走现有 `PUT /notes/{path}`。

**Goal:** 聊天气泡与输入框左右边距对齐。点 ① 后可在右侧改 Markdown：仅保存/关闭，保存后与 Documents 一样整篇重索引。无预览、无删除。

## 1. 气泡

[home.html](../../src/noteagent/web/templates/home.html)：`.chat-inner` 与 `.input-inner` 同宽。去掉用户行 `flex-end`。助手/用户气泡都铺满该栏；用户头像仍在右侧。

## 2. 出处侧栏

只读正文改为 textarea。头栏：保存、关闭。打开时若有 quote，选中并滚到该段。

`saveCitedNote`：`PUT` 与 Documents 相同，后端已是 `write` + `index_note`（先删再写）。成功则清 dirty；若 Documents 正打开同一文件则同步 `docsText`。

未保存关闭/Escape/切走 Chat 先确认。Ctrl+S：Chat 且侧栏打开时保存侧栏；`/documents` 仍只保存 Documents。

## 不做

新路由、侧栏预览、删除、改气泡里旧 ① 文案。
