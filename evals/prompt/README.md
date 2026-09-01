# prompt evals

系统提示与记笔记质量的第一期黄金集。人工对照 [`../README.md`](../README.md) 的六条标准打勾。不要把私人笔记全文写进 `user`。

## 包含模块

| 文件 | 作用 |
|------|------|
| [`cases.jsonl`](cases.jsonl) | 一行一条；13 条 |

| id | kind | 测什么 |
|----|------|--------|
| n01 | quality | 解释器教程标题树 + 记下来 |
| n02 | quality | 带 3. / 3.1. 的短节 + 整理成笔记 |
| n03 | quality | 含 python -c / -m 的命令段落；草稿须含围栏代码块（must_substrings） |
| n04 | quality | 无编号标题的叙述（GIL） |
| n05 | quality | 只要提纲 |
| n06 | quality | 只要 2.1.2 交互模式 |
| b01 | behavior | 只贴长文、无说明 → 先问、不提案 |
| b02 | behavior | 短句 + 记下来 → list_files 再提案 |
| b03 | behavior | 寒暄 → 不提案 |
| b04 | behavior | 问旧笔记 argv → search、不提案 |
| b05 | behavior | 明确更正过时表述 → list_files，提案 replace |
| b06 | behavior | 明确删文件 → list_files，提案 delete |
| b07 | behavior | 往已有主题再补一节 → list_files，提案 append 或 create，不得 replace |

## 基础使用

从 JSONL 取出某条的 `user`，贴进 `http://127.0.0.1:8000` 聊天（改过 [`system.txt`](../../src/noteagent/chat/prompts/system.txt) 后先重启进程）。对照该条字段与六条标准评分。尚无自动跑分脚本。
