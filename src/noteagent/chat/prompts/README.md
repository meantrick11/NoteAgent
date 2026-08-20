# prompts

只放提示词文本，不放 Python，不把用户笔记贴进本目录。

## 包含模块

| 文件 | 作用 |
|------|------|
| `system.txt` | 默认系统提示：何时提案、必须先 `list_files`、禁止声称已写盘 |
| `__init__.py` | 无逻辑 |

`ChatAgent` 用文件路径读取，不经过包 import：

`src/noteagent/chat/prompts/system.txt`

## 基础使用

改行为时编辑 `system.txt` 后重启进程。Agent 每个新 thread 的首轮会重新读文件。

无独立单测；改完用一次真实对话或看 `var/logs/noteagent.log` 里的 prompt 长度是否变化。
