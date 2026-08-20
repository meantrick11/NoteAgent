# evaluations

检索与 Agent 行为的人工评估集。当前不要求提交数据。不要把私人笔记全文放进来。

## 包含模块

暂无评估文件。计划中的用法（尚未落地）：约 10 条 query + 标注，算检索是否命中正确文件；另 10 个对话场景检查是否先 `list_files` 再 `propose_note`。

## 基础使用

以后可放 `queries.jsonl` 或 Markdown 表格：`query`、`expected_file`、`notes`。跑评估脚本时只读本目录，不要扫整个 `notes/`。
