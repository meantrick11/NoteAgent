# agent evals

多 hop 工具轨迹评测。第一期不单开数据，复用 [`../prompt/cases.jsonl`](../prompt/cases.jsonl) 里 `kind=behavior` 的 b01–b04。

## 包含模块

尚无独立 JSONL。以后若 prompt 集不够覆盖「search 之后误提案」等轨迹，再在本目录加文件。

## 基础使用

看日志或草稿卡片是否调用了 `propose_note` / `list_files` / `search_relative_from_chromadb`，与该条 `expect_propose`、`expect_tools_prefix` 对照。
