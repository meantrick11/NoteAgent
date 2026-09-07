# 聊天出处引用（编号映射 + 侧栏预览）

> 本日实现规格。不改切块器、embedding、Chroma collection。不做 NLI 校验。不做全局稳定索引。

**Goal:** 助手用过 `search` / `read_file` 支撑回答时，气泡里出现可点的 ①；点击后聊天区收窄，右侧打开对应笔记；检索片段灰底定位。模型只输出 `[[cite:N]]`，真实路径由服务端映射。

**做法:** 每轮内存 `CitationRegistry` 给工具结果分配 `source_id`。给模型的工具结果只有编号和正文。最终回答校验编号后，把实际用到的映射写入现有 `messages.citations` JSON。前端按映射渲染上标并打开预览。历史打包时剥掉 `[[cite:N]]`，不把映射发给模型。

## 不做

- 新建引用表；不从截断的 tool stub 重建映射
- 把映射或真实路径放进工具结果给模型
- 重建 Chroma / 增加 `char_start`
- 出处芯片条、语义校验、PDF 页码

## 文件

| 文件 | 改动 |
|------|------|
| `chat/citations.py` | `CitationRegistry`、`sanitize_answer`、`strip_cite_markers`、`current_citations` |
| `db/models.py` | `Message.citations` JSON 可空 |
| `alembic/versions/` | `messages.citations` 列；head 接在 `3d1c2b8a9e4f` 后 |
| `chat/history.py` | `append_message(..., citations=)`；`MessageRecord.citations` |
| `chat/tools.py` | search/read 注册来源，返回 `source_id` |
| `chat/agent.py` | 本轮 registry；最终 hop 校验后 `sources` + 净化正文 |
| `chat/router.py` | 推 `sources` SSE；assistant 入库带 citations |
| `chat/schemas.py` | `CitationOut`；`MessageOut.citations` |
| `chat/context_pack.py` | 进模型的历史 assistant 去掉 cite 标记 |
| `prompts/system.txt` | 要求 `[[cite:N]]`，禁止输出路径 |
| `web/templates/home.html` | 上标、侧栏预览、历史恢复 |
| 测试与 architecture 现状句 | 与代码对齐 |

## 流程

```text
search/read
  → CitationRegistry.register（去重，1,2,3…）
  → 工具返回 {source_id, content}（无 file_name）
模型句末 [[cite:1]]
  → sanitize：非法编号删除；used 列表
SSE sources（used）→ token（净化后）
append_message(assistant, content, citations=used)
前端：[[cite:n]] → ①；点击 GET /notes/{path}；有 quote 则灰底定位
```

## 存储

`messages.citations` 可空 JSON，仅 assistant 最终消息：

```json
[{"index": 1, "file_name": "Go.md", "chunk_index": 0, "quote": "..."}]
```

read 整篇：`chunk_index`/`quote` 为 null。user/tool 行保持 null。删除会话 CASCADE 消息行。生产库 `alembic upgrade head`。

## 验收

- 同一 chunk 两次 search 共用一个 `source_id`。
- 合法 `[[cite:1]]` 保留；未注册编号从正文删除。
- assistant 行能读回 citations；user 行不能写 citations。
- 进 pack 的历史正文不含 `[[cite:N]]`。
- 实时 SSE 与刷新历史后 ① 均可点；片段可灰底；笔记改写后定位失败仍打开全文。
