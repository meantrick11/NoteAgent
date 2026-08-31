# unit

纯函数与仓库测试。无网络、无真实 LLM、无 SentenceTransformer、无持久 Chroma。

## 包含模块

| 文件 | 覆盖 |
|------|------|
| `test_import.py` | 包从 `src/noteagent` 导入 |
| `test_settings.py` | 路径解析、密钥不出现在 repr、env 覆盖 |
| `test_app_container.py` | `build_container` 要求 `DATABASE_URL` |
| `test_note_repository.py` | 创建/读写、路径逃逸 |
| `test_chunker.py` | 短文不拆、长文拆开 |
| `test_chat_tools.py` | 工具列表无写盘；`propose_note` 不落盘 |
| `test_drafts.py` | 同意追加/新建、override、拒绝 |
| `test_chat_history.py` | 标题归一化；create/get/list/append；级联删除；重命名/删除 |
| `test_context_budget.py` | Settings → `ContextBudget` |
| `test_context_tokens.py` | token 估算与 stub 截断 |
| `test_context_compact.py` | Turn 分组、触发、drop/keep、stub 不计双份 |
| `test_context_pack.py` | pack 装配 |
| `test_context_store.py` | turn_id、stub、watermark、UI 过滤 tool |
| `test_chat_agent_context.py` | stub 入库、跨 Turn 无全文工具、hop 上限、压缩 |

## 基础使用

```bash
uv run pytest tests/unit -q
uv run pytest tests/unit/test_drafts.py -q
```
