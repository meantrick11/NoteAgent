# unit

纯函数与仓库测试。无网络、无真实 LLM、无 SentenceTransformer、无持久 Chroma。

## 包含模块

| 文件 | 覆盖 |
|------|------|
| `TestSourceOrganization.py` | 五个入口、业务与 HTTP 隔离、ORM 注册和 SPA 资源路径 |
| `TestModelProbes.py` | 不支持探测时的不可变结果构造 |
| `TestImport.py` | 包从 `src/NoteAgent` 导入 |
| `TestSettings.py` | 路径解析、密钥不出现在 repr、env 覆盖 |
| `TestAppContainer.py` | `build_container` 要求 `DATABASE_URL` |
| `TestNoteRepository.py` | 创建/读写/删除、一层目录、路径逃逸 |
| `TestChunker.py` | 短文不拆、长文拆开 |
| `TestChatTools.py` | 工具列表无写盘；`propose_note` 四动作不落盘；一层路径；`ProposeNoteInput` schema |
| `TestDrafts.py` | 同意追加/新建/覆盖/删除、override、拒绝；可选 retrieval 同步 |
| `TestChatHistory.py` | 标题归一化；create/get/list/append；级联删除；重命名/删除；`pending_draft` |
| `TestContextBudget.py` | Settings → `ContextBudget` |
| `TestContextTokens.py` | token 估算与 stub 截断 |
| `TestContextCompact.py` | Turn 分组、触发、drop/keep、stub 不计双份 |
| `TestContextPack.py` | pack 装配；从用户句抽取编号/`##` 标题树 |
| `TestContextStore.py` | turn_id、stub、watermark、UI 过滤 tool |
| `TestCitations.py` | `source_id` 登记、sanitize 丢假号、用到的引用按出现顺序重排 1..n |
| `TestPromptEvalScore.py` | v0.1 L1：标题树、发明标题、锚点、create 正文 H1 |
| `TestPromptEvalLearningNotes.py` | v0.2 学习型字段与资格判定 |
| `TestPromptEvalJudge.py` | Judge JSON 契约与重试 |
| `TestPromptEvalCalibration.py` | 四候选校准契约 |
| `TestPromptEvalRun.py` | 脚本化 Agent、seed_files、`n00.md` / `index.json` 布局、rubric 版本 |

## 基础使用

```bash
uv run pytest Tests/Unit -q
uv run pytest Tests/Unit/TestDrafts.py -q
```
