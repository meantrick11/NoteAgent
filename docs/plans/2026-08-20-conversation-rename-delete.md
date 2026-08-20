# 会话重命名与删除 Implementation Plan

> **For agentic workers:** 按 Task 1 → 5 **严格顺序**执行。不要 git commit，除非用户明确要求。
>
> **做完后不要自称完成。** 列出改过的文件、pytest 命令与结果。浏览器里点一遍「… → 重命名 / 删除」后交给审查 Agent。

**Goal:** 侧栏每条历史右侧有 `…`。点开方形菜单：上「重命名」、下「删除」。重命名把该条标题变成行内输入框。删除先弹确认窗；悬停「确认」变红、「取消」灰色。确认后 PostgreSQL 里该会话及其消息一并删除。

**Architecture:** HTTP 只调 `ConversationStore`。表结构已有 `ON DELETE CASCADE`，**不要新迁移**。不改 `agent.py`、不做 Vue、不加用户系统。

**Tech stack:** 现有 FastAPI + `ConversationStore` + `home.html` vanilla JS。单测仍用 SQLite 内存库。

---

## 怎么执行

1. 先读 [`src/noteagent/chat/history.py`](../../src/noteagent/chat/history.py)、[`router.py`](../../src/noteagent/chat/router.py)、[`home.html`](../../src/noteagent/web/templates/home.html) 里 `loadConversations` / `openConversation` / `newChat`（约 434–477 行）。
2. 每个 Task：有测试先写测试再实现；跑该 Task 的 verify。
3. 只改本计划列出的文件。不要重构列表 API、不要改 RAG。

---

## 非目标

- 批量删除、归档、搜索、拖拽排序
- 改表结构 / 新 Alembic 版本
- `window.confirm`（必须用页面内弹层，才能做确认键红色悬停）
- 改 `ChatAgent` / InMemorySaver（删会话后进程内 checkpoint 可残留，可接受，不要为此接 PostgresSaver）

---

## UX 规格（必须按此，不要发挥成抽屉/底部 sheet）

侧栏宽度 `--sidebar-width: 260px`。列表项已有 `.conversation-item`。

**列表行：**

```text
[ 标题文字（ellipsis）          … ]
```

- 点标题区域：仍 `openConversation(id)`（现有行为）。
- 点 `…`：`stopPropagation`，打开菜单；**不要**因此切换会话。
- `…` 默认浅灰，hover 时更深；不要挡标题。标题 `flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis`。
- 同一时间只开一个菜单。点页面空白、点另一条 `…`、滚动 `.sidebar-body`、开始重命名：关掉菜单。

**方形菜单：**

- 绝对定位在该行 `…` 下方（或上方——若靠近侧栏底部会溢出，则向上打开）。
- 宽度约 120–140px，**不得超过侧栏内边距**：`left`/`right` 钳在 `.sidebar-body` 内，不要伸到主聊天区。
- 白底、`1px` `var(--border)`、`border-radius: 8px`（方形圆角小卡片，不是胶囊）。
- 两项等高：重命名、删除。文字左对齐，不要图标。hover 行背景 `var(--bg)`。
- `z-index` 高于列表，低于删除弹层。

**重命名：**

- 关掉菜单。该行标题换成 `<input>`（小方框：边框 `var(--border)`、圆角 6px、字号 14px、宽度占满标题槽）。
- 预填当前 title，全选。
- Enter：提交；Escape：取消并恢复原文字；blur：非空则提交，空则取消。
- 提交：`PATCH`；成功后该行显示新标题，保持原 `active`。失败 alert 或行内恢复旧标题。
- 输入中点该行不要触发 `openConversation`。

**删除弹层：**

- 关掉菜单。页面中央（或主区中央）小卡片，遮罩半透明。
- 文案：标题「删除对话」；正文「确定删除「{title}」？删除后无法恢复。」
- 按钮右对齐：取消 | 确认。
- **取消**：默认灰底灰字（`#e5e7eb` / `var(--text-secondary)`）；hover 仍灰，略深即可。
- **确认**：默认可浅底；**`:hover` 背景红色**（如 `#dc2626`）、字白。不要默认就是大红块。
- 点遮罩 = 取消。Esc = 取消。
- 确认：`DELETE`；成功后从列表移除。若删的是当前 `currentConversationId`，调用现有 `newChat()`（欢迎页 + id 置 null）。
- 失败：弹层可关，不假装已删。

---

## HTTP 契约

```text
PATCH /conversations/{conversation_id}
Content-Type: application/json
{"title": "新名字"}

200 ConversationOut   {id, title, updated_at}
400 {"detail": "title is required"}   # strip 后空
404 {"detail": "conversation not found"}

DELETE /conversations/{conversation_id}

204 无 body
404 {"detail": "conversation not found"}
```

标题：`strip`，内部空白折叠为单空格（与 `conversation_title_from_question` 同类：`" ".join(title.split())`）。折叠后空 → 400。最长 **80** 字符（超长截断或 400，选 **400** `title too long`，避免静默截断让用户以为没存全）。

**重命名不改 `updated_at`**（避免改名把会话顶到列表最前）。删除走 ORM `session.delete(conversation)`，依赖已有 CASCADE，消息行必须消失。

---

### Task 1: Store.rename / Store.delete

**Files:**
- Modify: `src/noteagent/chat/history.py`
- Modify: `tests/unit/test_chat_history.py`

在 `ConversationStore` **追加**（不要改 `create`/`append_message` 签名）：

```python
def rename(self, conversation_id: str, title: str) -> ConversationRecord:
    """Set title. KeyError if missing/malformed id. ValueError if title empty after normalize."""

def delete(self, conversation_id: str) -> None:
    """Delete conversation and messages. KeyError if missing/malformed id."""
```

规范化（Store 内做，router 不要再折一次，或抽 `normalize_conversation_title(title: str) -> str`，空串表示非法）：

```python
def normalize_conversation_title(title: str, max_len: int = 80) -> str:
    """Collapse whitespace. Empty if nothing left. Raise ValueError if longer than max_len."""
```

`rename`：非法 uuid / 找不到 → `KeyError`。规范化空 → `ValueError("title is required")`。过长 → `ValueError("title too long")`。成功 `_logger.info("rename conversation=%s", conversation_id)`。

`delete`：找不到 → `KeyError`。`session.delete(row)` + `commit`。`_logger.info("delete conversation=%s", conversation_id)`。

**测试（先红后绿）：**

- rename 后 `get` 标题变了，`updated_at` **相等**（或至少 list 顺序：先 A 后 B，rename A，list 仍是 B 然后 A）
- rename 未知 id → `KeyError`
- rename `"   "` → `ValueError`
- rename 81 个 `x` → `ValueError`
- delete 后 `get` 为 None，`list_messages` 为 None；用第二个 session `count(Message)==0`（沿用现有 cascade 测法）
- delete 未知 id → `KeyError`

- [ ] 写测试
- [ ] 写 Store
- [ ] `uv run pytest tests/unit/test_chat_history.py -v`

---

### Task 2: PATCH / DELETE 路由

**Files:**
- Modify: `src/noteagent/chat/schemas.py` — 增加

```python
class RenameConversation(BaseModel):
    """JSON body for PATCH /conversations/{id}."""

    title: str
```

- Modify: `src/noteagent/chat/router.py`
- Modify: `tests/integration/test_app.py`

路由挂现有 `router`：

```python
@router.patch("/conversations/{conversation_id}")
async def rename_conversation(...) -> ConversationOut:

@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(...) -> None:
```

映射：

- `KeyError` → 404 `conversation not found`
- `ValueError` 且 `"required"` in str(e) → 400 `title is required`
- `ValueError` 且 `"too long"` → 400 `title too long`

日志：`rename conversation=%s`、`delete conversation=%s`。

**集成测（`_client` 内存 history）：**

- create `"old"`，PATCH `{"title":"新名字"}` → 200，`title=="新名字"`，GET list 能看到
- PATCH 未知 uuid → 404
- PATCH `{"title":"  "}` → 400
- create + 两条 message，DELETE → 204；GET messages 404；GET list 不含该 id
- DELETE 未知 uuid → 404

- [ ] 实现 + 测试
- [ ] `uv run pytest tests/integration/test_app.py tests/unit/test_chat_history.py -v`

---

### Task 3: 侧栏 `…` 菜单 + 行内重命名 + 删除弹层

**Files:**
- Modify: `src/noteagent/web/templates/home.html` 的 CSS、`loadConversations`、必要时少量 HTML（弹层可 JS 创建或静态放在 `</body>` 前）

**不要**引入 Vue。不要 localStorage。

**`loadConversations` 行结构（必须）：** 不要再用整行 `textContent = conv.title`（会盖住按钮）。改为：

```html
<div class="conversation-item" data-id>
  <span class="conversation-title">...</span>
  <button type="button" class="conversation-more" aria-label="更多">…</button>
</div>
```

点 `.conversation-title`（或 item 空白）→ `openConversation`。点 `.conversation-more` → 开菜单。

菜单建议一个全局 `#conversationMenu`，打开时 `dataset.id` 记下目标，用 `getBoundingClientRect` 相对 sidebar 定位。删除弹层全局一份即可。

重命名：把该行 `.conversation-title` 换成 input（或隐藏 span 显示 input）。PATCH：

```text
PATCH /conversations/${id}
{"title": value}
```

删除：

```text
DELETE /conversations/${id}
```

204 无 JSON，不要 `res.json()`。

`test_home_serves_template` 可加：`assert "conversation-more" in response.text` **仅当**按钮写在静态 HTML；若纯 JS 生成则不要加这条（会红）。改测 `assert "conversationList" in response.text` 保持即可。

- [ ] CSS + JS
- [ ] `uv run pytest tests/integration/test_app.py -q` 仍绿

---

### Task 4: 文档

**Files:**
- Modify: `src/noteagent/chat/README.md` — 路由表加上 PATCH、DELETE 及行为一句（CASCADE、rename 不改 updated_at）

不要改 `knowledge-workflow-v1.md` 大段。不要新增 docker-compose。

- [ ] README 与实现一致

---

### Task 5: 手工验收（实现 Agent 尽量做）

`uv run python main.py`，浏览器：

1. 至少两条会话。每条右侧能看到 `…`，标题长时被 ellipsis，`…` 仍在侧栏内。
2. 点 `…` 出现方形菜单：重命名在上、删除在下；菜单不超出左侧栏。
3. 重命名：行变输入框，改名 Enter，刷新后新标题还在；列表顺序不因改名跳到最顶（除非它本来就是最新）。
4. 删除：弹窗；悬停确认变红、取消保持灰；取消后会话还在；确认后列表和库都没了（再刷新也没有）。
5. 删掉当前打开的会话后，主区回到欢迎页，可新建对话。

---

## 给审查 Agent 的清单

1. 无新 migration；delete 后 messages 行为 0（测试覆盖）
2. PATCH/DELETE 404/400 行为符合契约
3. rename 不把会话顶到 `updated_at` 排序第一（有单测）
4. 菜单在 260px 侧栏内；`…` 不触发误切换会话
5. 删除用自定义弹层，确认 hover 红色，取消灰色
6. 未改 `agent.py`
7. 前端 DELETE 按 204 处理
8. 手工验收若未做，标「未验证」
