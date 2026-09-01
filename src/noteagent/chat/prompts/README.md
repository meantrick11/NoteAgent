# prompts

只放提示词文本，不放 Python，不把用户笔记贴进本目录。

## 包含模块

| 文件 | 作用 |
|------|------|
| `system.txt` | **现行**系统提示（Agent 只读这一份）。结构为 Role / Context / Task / Constraint / Example；Constraint 为笔记六条质量 |
| [`iterations/`](iterations/README.md) | 历次全文归档；现为 v1–v7。v7 与现行 `system.txt` 相同 |

`ChatAgent` 用文件路径读取，不经过包 import：

`src/noteagent/chat/prompts/system.txt`

## 基础使用

改 `system.txt` 后**重启进程**（每次 `stream()` 会重新读该文件）。不要改 `ChatAgent` 去加载 `iterations/`。

人工黄金集（不进 pytest）：[evals/](../../../../evals/README.md)。改完提示词用 [`evals/prompt/cases.jsonl`](../../../../evals/prompt/cases.jsonl) 人工回归。
