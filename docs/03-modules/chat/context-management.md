# Checkpoint 上下文与压缩

当前状态定义在 conversations/records.py 的 GraphState，执行节点在 chat/graph.py 与 nodes.py。checkpoint 保存完整显示历史和独立模型工作上下文。

| 状态 | 用途 |
|---|---|
| ui_messages | 完整 user/assistant 展示记录、引用和工具步骤，压缩不删除 |
| working_records | 模型近端对话与工具 stub，按 watermark/预算保留 |
| running_summary / summary_watermark_turn_id | 旧工作上下文摘要及已压缩边界 |
| runtime_messages | 当前轮完整工具调用和结果，按节点持久保存，受控续跑保持配对 |
| pending_draft | 待审批笔记全文，独立于气泡；批准才修改正文 |

context_pack 按现有预算组装消息，context_compact 将较旧工作记录归并摘要；框架 checkpoint 负责持久化，不自动替应用实现压缩策略。完成轮次后的近端工具结果保留受控 stub，完整 UI 历史仍可显示。

历史编辑从所选 user 的输入前 checkpoint 恢复摘要、压缩记录和草稿，再加入一次新 user。不能把全部 UI 历史重造为未压缩工作上下文，也不能清空历史草稿。隐藏候选通过恢复协调器成功发布后才成为活动状态。

中断可显式 run_id 续跑；已恢复的 prepared_turn_id 不重复接受 user。旧 imported 消息没有真实 before checkpoint，不提供整体回退能力。并发规则见 [checkpoint-resume](checkpoint-resume.md)，材料与索引恢复见 [recovery](../recovery/recovery.md)。

## 5. 压缩算法

### 5.1 符号

```text
W = 模型 Context Window
触发 = 当前 Context token ≥ W × 0.80
T = W × 0.60
F = 压缩后必须保留的非「历史 Turn」内容（当次实测）
K = T − F
```

K 不是消息条数、不是剩余窗口、不是 80% 本身。

F 包含：System、Tools、Summary、当前 User、Runtime（内部含全文 Tool Result）、draft 一行（若有）、Output Reserve、Safety Buffer。内部路径 F 更大、K 更小。

例：W=32K，T=19.2K，F=14K → K=5.2K。

### 5.2 保留哪些 Turn

从当前往历史，累加已完成 Turn 的 Persistent token：

```text
Turn10=1.5K, Turn9=1.8K, Turn8=1.2K → 4.5K
再加 Turn7=2.0K → 6.5K > K
→ 保留 Turn 8～10（约 4.5K），Turn 1～7 进入 summary
```

不为凑满 K 而拆 Turn 7。

### 5.3 为何默认 80% 触发、60% 水位

触发与水位同一套，闲聊与带工具的 Turn 都在包真正变满时才压，而不是外部路径先压到 60%「给 read_file 留空」（工具还没发生）。T=50% 时同样 F=14K 会把 K 压到约 2K，往往只剩一两个短 Turn，摘要更容易漂。T 贴近 75% 会与触发贴太近、来回压。默认 80/60，用日志再调。

---
