# 短期记忆与上下文管理 Implementation Plan

> **For agentic workers:** REQUIRED：按 Task 0 → 10 **严格顺序**执行。每完成一个 Task 再进入下一个。步骤用 `- [ ]` 勾选。不要并行改多个 Task。
>
> **权威文档（冲突时按此顺序）：**
> 1. [../architecture/context-management.md](../architecture/context-management.md) — 行为契约  
> 2. [../architecture/database.md](../architecture/database.md) — 表、列、实例行  
> 3. **本文** — 函数名、Task、测试命令  
>
> **不要 git commit**，除非用户明确要求。
>
> **做完后不要自称完成。** 列出：改过的文件、每条跑过的 pytest 命令与通过/失败。交给审查 Agent 对照本文「验收」与契约 §8。

**Goal:** 会话上下文改为：Persistent（user + 最终 assistant + tool stub）+ 会话上一栏 `running_summary` + 仅当前 Turn 内存 Runtime 全文；按环境里的 W×触发比例 / 目标比例与完整 Turn 边界压缩；停用 `context.md` 当聊天记忆。

**Architecture:** 只扩现有 `conversations` / `messages`（见 database.md §4）。`ConversationStore` 是库的唯一写入口。`ChatAgent.stream` 用 `bind_tools` 循环 + 局部 `runtime` 列表；**禁止** `create_agent` + 进程级 `InMemorySaver`。压缩纯函数在 `context_compact.py`；W、比例、stub token 上限全部来自 Settings/环境，compact/agent **禁止**写死 32768、0.8、0.6、1000。

**Tech stack:** FastAPI、SQLAlchemy 2、Alembic、LangChain `bind_tools`、pytest + 内存 SQLite。不要新增依赖。token 用 `estimate_tokens`（字符/4），不用 tiktoken 文件。

---

## 怎么执行（Claude 必读）

1. Task 0 先读契约 + database.md，不写代码。
2. 每个 Task：先测后实现；`uv run pytest ...`（PowerShell）。
3. 不要发明第三张聊天表、不要 `PostgresSaver`、不要改 `home.html`、不要用户模式开关。
4. `CLAUDE.md`：少改无关文件；新函数写注释；日志打 conversation/turn id 与 token 数字，**禁止**完整 prompt / 工具全文 / `DATABASE_URL`。
5. 列名、函数名必须与本文「锁定接口」一致。表形态以 database.md 为准。

---

## 非目标（禁止）

- 用户切换纯聊天 / Agent 模式
- 工具全文或 Agent 自我输出入库
- 聊天记录进 Chroma
- LangGraph `PostgresSaver` / 进程级跨 Turn `InMemorySaver`
- 语义任务识别、importance scoring、多级 memory
- Job 状态机、审批后自动索引（那是 draft-generation）
- Vue/React 重写前端；草稿卡片逻辑不变
- 把 Draft 并进 `messages` 气泡
- 运行时用 SQLite 代替 PostgreSQL（仅单测 SQLite）

---

## 全局约束

- 包路径 `src/noteagent/`。`chat` 可 import `db`；`db` **不得** import `chat`。
- 前端 `GET /conversations/{id}/messages` 只返回 `role IN ('user','assistant')`。
- 压缩只切 **已完成** Turn；watermark 不得等于当前未完成 `turn_id`。
- 摘要：**只摘要被切掉的 Turn，拼到旧 `running_summary` 后面**，禁止把旧摘要+旧历史重写成一篇。
- 若存在至少一个已完成 Turn，压缩后至少保留 1 个完整 Turn（即使略超 T）。
- 当前 Turn 一个已完成 Turn 都没有时：即使 ≥80%W 也 **不 compact**（只打 warning 日志）。
- 停止读写 `notes/context.md` 作为聊天记忆。
- Runtime 只活在**这一次** `stream()` 调用的局部 list；函数返回即丢。不按会话在 `ChatAgent` 实例上缓存全文工具链。

---

## 目标文件树

新建：

```text
src/noteagent/chat/context_budget.py
src/noteagent/chat/context_tokens.py
src/noteagent/chat/context_compact.py
src/noteagent/chat/context_pack.py
alembic/versions/<rev>_context_watermark_and_tool_stubs.py
tests/unit/test_context_tokens.py
tests/unit/test_context_compact.py
tests/unit/test_context_pack.py
tests/unit/test_context_store.py
tests/unit/test_chat_agent_context.py
tests/unit/test_context_budget.py
```

修改：

```text
src/noteagent/db/models.py
src/noteagent/db/README.md
src/noteagent/bootstrap/settings.py
src/noteagent/bootstrap/app.py
src/noteagent/chat/history.py
src/noteagent/chat/agent.py
src/noteagent/chat/router.py
src/noteagent/chat/drafts.py          # 仅增加 current_turn_id ContextVar
src/noteagent/chat/prompts/system.txt
src/noteagent/chat/README.md
.env.example
docs/architecture/architecture.md     # 4.2.2.5「代码现状」改成已实现
docs/architecture/context-management.md  # 文首状态改「已按本文实现」
docs/architecture/database.md         # 文首状态：上下文列已建
tests/unit/test_chat_history.py
tests/integration/test_app.py
```

不要新建第二套 ORM 表。

---

## 锁定：数据库字段

**列、索引、实例行以 [database.md](../architecture/database.md) §3–4 为准。** 摘要如下，禁止另起表名。

### `conversations` 新增列

| 列 | SQLAlchemy | 可空 | 默认 | 含义 |
|----|------------|------|------|------|
| `running_summary` | `Text` | YES | `NULL` | 该会话**唯一**摘要栏；压缩时追加 |
| `summary_watermark_turn_id` | `Uuid(as_uuid=True)` | YES | `NULL` | 摘要已覆盖的最后**已完成** `turn_id` |

不改 `id` / `title` / `created_at` / `updated_at`。绑定 `conversations.id`。压缩**不删** `messages` 行。

### `messages` 新增列

| 列 | SQLAlchemy | 可空 | 默认 | 含义 |
|----|------------|------|------|------|
| `turn_id` | `Uuid(as_uuid=True)` | YES（旧行） | `NULL` | 所属 Turn |
| `tool_name` | `Text` | YES | `NULL` | 仅 `role='tool'` |
| `tool_arguments` | `Text` | YES | `NULL` | 参数 JSON 字符串，最长 `args_preview_chars` |
| `output_preview` | `Text` | YES | `NULL` | 工具输出前 `stub_preview_tokens`（按 estimate_tokens 截断） |
| `truncated` | `Boolean` | NO | `False` | 输出是否被截成 preview |
| `status` | `Text` | YES | `NULL` | `ok` 或 `error` |

已有列：

- `role`：允许 `'user' | 'assistant' | 'tool'`。`content` 对 user/assistant 为展示正文；对 tool 存与 `output_preview` 相同的短文本（满足 NOT NULL，且列表接口不会返回 tool 行）。
- 新增索引：`ix_messages_conversation_turn`（`conversation_id`, `turn_id`）。

`truncated`：`from sqlalchemy import Boolean`；`mapped_column(Boolean, nullable=False, default=False)`。

Alembic：`down_revision = 'f16dee6e3c97'`。`upgrade` 加列 + 索引；旧 `turn_id` 可空；按会话 `created_at, id` 扫描，遇 `role='user'` 新 `uuid4`，后续连续 assistant 同属该 turn。`downgrade` 删新列和新索引。单测用 `create_all`，不必在 CI 跑 alembic。

---

## 锁定：配置（Settings）

全部从环境变量读（`validation_alias`）。**`context_compact.py` / `agent.py` / `history.py` 禁止出现** 32768、0.8、0.6、1000 字面量，一律用传入的 `ContextBudget` 或 `append_tool_stub` 的 int 参数。

Settings 字段允许与 `.env.example` **相同的 default**（便于 `Settings()` 单测）；生产以 `.env` 覆盖。`.env.example` 必须写出全部键。

| 字段 | env | Settings default 与 example | 含义 |
|------|-----|------------------------------|------|
| `chat_context_window` | `CHAT_CONTEXT_WINDOW` | `32768` | W（**token**） |
| `context_trigger_ratio` | `CONTEXT_TRIGGER_RATIO` | `0.8` | 触发压缩 |
| `context_target_ratio` | `CONTEXT_TARGET_RATIO` | `0.6` | T/W |
| `context_stub_preview_tokens` | `CONTEXT_STUB_PREVIEW_TOKENS` | `1000` | stub 输出预览（**token**） |
| `context_args_preview_chars` | `CONTEXT_ARGS_PREVIEW_CHARS` | `500` | 参数字符串截断（**字符**） |
| `context_output_reserve` | `CONTEXT_OUTPUT_RESERVE` | `1024` | F 的一部分（token） |
| `context_safety_buffer` | `CONTEXT_SAFETY_BUFFER` | `512` | F 的一部分（token） |

---

## 锁定：Python 接口（后续 Task 必须用这些名字）

### `noteagent.chat.context_budget`

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ContextBudget:
    window: int
    trigger_ratio: float
    target_ratio: float
    stub_preview_tokens: int
    args_preview_chars: int
    output_reserve: int
    safety_buffer: int

    def trigger_tokens(self) -> int:
        """Return int(window * trigger_ratio)."""

    def target_tokens(self) -> int:
        """Return int(window * target_ratio)."""

def budget_from_settings(settings: Settings) -> ContextBudget:
    """Map Settings fields onto ContextBudget."""
```

### `noteagent.chat.context_tokens`

```python
def estimate_tokens(text: str) -> int:
    """Deterministic token estimate: max(1, (len(text) + 3) // 4) if text else 0."""

def prefix_until_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """If estimate_tokens(text) <= max_tokens: return (text, False).
    If max_tokens <= 0: return ('', bool(text)).
    Else binary-search the smallest char prefix with estimate_tokens(prefix) >= max_tokens.
    Return (prefix, True).
    """
```

空字符串返回 `0`。

### `noteagent.chat.history` 增量

`ConversationRecord` 增加：

- `running_summary: str | None`
- `summary_watermark_turn_id: str | None`

`MessageRecord` 增加：

- `turn_id: str | None`
- `tool_name: str | None`
- `tool_arguments: str | None`
- `output_preview: str | None`
- `truncated: bool`
- `status: str | None`

```python
def start_turn() -> str:
    """Return str(uuid.uuid4()). No DB write."""

class ConversationStore:
    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        turn_id: str,
    ) -> MessageRecord:
        """Insert user or assistant. role in {user, assistant}. Bump updated_at.
        KeyError if conversation missing; ValueError if bad role or empty turn_id.
        Persist turn_id as UUID.
        """

    def append_tool_stub(
        self,
        conversation_id: str,
        *,
        turn_id: str,
        tool_name: str,
        arguments: str,
        output: str,
        status: str,
        stub_preview_tokens: int,
        args_preview_chars: int,
    ) -> MessageRecord:
        """Insert role='tool'. Do NOT bump conversation.updated_at.
        Truncate arguments by character count args_preview_chars.
        Truncate output with prefix_until_tokens(output, stub_preview_tokens).
        truncated = True if output was cut.
        content = output_preview (NOT NULL).
        status must be 'ok' or 'error'.
        """

    def list_messages(self, conversation_id: str) -> list[MessageRecord] | None:
        """UI: only role in {user, assistant}, order created_at, id.
        Same None/[] semantics as today.
        """

    def list_persistent_after_watermark(
        self, conversation_id: str
    ) -> list[MessageRecord]:
        """All roles. If conversation missing -> KeyError.
        If watermark is NULL: all messages oldest-first.
        Else: messages whose turn is strictly after the watermark turn
        (turns ordered by min(created_at), then turn_id).
        Include the current incomplete turn.
        """

    def apply_compact(
        self,
        conversation_id: str,
        *,
        summary_append: str,
        watermark_turn_id: str,
    ) -> None:
        """Set running_summary = concat old + '\\n\\n' + summary_append (if old empty, just append).
        Set summary_watermark_turn_id. Do not rewrite summary_append itself.
        Log conversation id, watermark, summary chars. KeyError if missing.
        """
```

`get()` / `create()` / `_to_conversation` 必须带出 summary 字段（新会话均为 `None`）。

模块级 `_ROLES` 保持 `{user, assistant}` 给 `append_message`。tool 只走 `append_tool_stub`。

### `noteagent.chat.context_compact`

```python
@dataclass(slots=True)
class TurnBundle:
    turn_id: str
    records: list[MessageRecord]
    tokens: int
    complete: bool  # True iff there is at least one role=='assistant' in records

def group_turns(records: list[MessageRecord]) -> list[TurnBundle]:
    """Group consecutive records by turn_id. Order = first appearance.
    rows with turn_id is None: each message is its own bundle, complete if role=='assistant'.
    tokens = sum(estimate_tokens of content + tool_name + tool_arguments + output_preview).
    """

def compute_f(*, system: str, tool_defs: str, summary: str, current_user: str,
              draft_line: str | None, runtime: str, budget: ContextBudget) -> int:
    """Sum estimate_tokens of those strings plus budget.output_reserve + budget.safety_buffer."""

def select_turns_to_drop(
    bundles: list[TurnBundle],
    *,
    current_turn_id: str,
    k_tokens: int,
) -> tuple[list[TurnBundle], list[TurnBundle]]:
    """Return (drop, keep).
    Ignore bundles with turn_id == current_turn_id (never drop current).
    Among remaining, only drop/keep **complete** turns; incomplete non-current should not happen
    (if it does, treat as keep, never drop).
    Walk complete turns from newest to oldest, accumulating tokens until adding the next
    would exceed k_tokens; those accumulated are keep; older complete turns are drop.
    If there is at least one complete turn besides current, keep at least the newest complete
    even if its tokens > k_tokens.
    Current turn bundle always goes to keep (append at end of keep, after older keep).
    keep order: chronological (old -> new) among kept completed, then current.
    """

def format_turns_for_summary(bundles: list[TurnBundle]) -> str:
    """Plain text dump of dropped turns for the summarizer (role/content/stub fields)."""

def concat_summary(old: str | None, chunk: str) -> str:
    """If old is None or blank: return chunk.strip(). Else old.rstrip() + '\\n\\n' + chunk.strip()."""
```

压缩决策：

```python
def should_compact(pack_tokens: int, budget: ContextBudget) -> bool:
    return pack_tokens >= budget.trigger_tokens()
```

`k_tokens = budget.target_tokens() - f_tokens`；若 `k_tokens < 0`，当作 `0`，然后仍受「至少 1 个已完成 Turn」约束。

### `noteagent.chat.context_pack`

```python
def stub_text(record: MessageRecord) -> str:
    """One line: [tool_stub] name=... args=... preview=... status=... truncated=..."""

def records_to_langchain(records: list[MessageRecord]) -> list:
    """user->HumanMessage(content), assistant->AIMessage(content),
    tool->AIMessage(content=stub_text(record)).
    """

def draft_workspace_line(draft: NoteDraft | None) -> str | None:
    """None if no draft. Else '待审草稿: {action} {file_name}（全文在前端卡片，不要当聊天正文）'."""
```

装配 **必须**按下列规则（不要同时带上「当前 Turn 的 stub」和「同一跳 ToolMessage 全文」）：

`build_pack` 伪代码（实现保持行为一致）：

```python
def build_pack(*, system_prompt, tool_defs, summary, persistent, current_turn_id,
               current_user, draft_line, runtime_messages, budget) -> PackResult:
    hist = [
        r for r in persistent
        if not (r.role == "tool" and r.turn_id == current_turn_id)
    ]
    messages = [SystemMessage(content=system_prompt)]
    if summary:
        messages.append(SystemMessage(content="历史摘要：\n" + summary))
    if draft_line:
        messages.append(SystemMessage(content=draft_line))
    messages.extend(records_to_langchain(hist))
    if not any(r.role == "user" and r.turn_id == current_turn_id for r in hist):
        messages.append(HumanMessage(content=current_user))
    messages.extend(runtime_messages)

    runtime_text = "\n".join(
        (m.content if isinstance(m.content, str) else "") for m in runtime_messages
    )
    f_tokens = compute_f(
        system=system_prompt, tool_defs=tool_defs,
        summary=summary or "", current_user=current_user,
        draft_line=draft_line, runtime=runtime_text, budget=budget,
    )
    k_tokens = max(0, budget.target_tokens() - f_tokens)
    pack_text = tool_defs + "\n".join(
        (m.content if isinstance(getattr(m, "content", None), str) else "") for m in messages
    )
    pack_tokens = estimate_tokens(pack_text)
    return PackResult(messages=messages, pack_tokens=pack_tokens, f_tokens=f_tokens, k_tokens=k_tokens)
```

含义：

- 历史 Turn 的 tool 以 **stub 一行** 进入模型。
- **当前 Turn** 的 tool 行从 Persistent 转换中剔除；全文只走 `runtime_messages`（`AIMessage(tool_calls=...)` + `ToolMessage(content=全文)`）。
- 当前 user 已由路由写入 Persistent，不要再 append 一遍 `question`。
- `pack_tokens` 含 `tool_defs`（bind_tools 仍占窗口）。

实现要求：只接受显式参数，不读 ContextVar。

```python
@dataclass(slots=True)
class PackResult:
    messages: list
    pack_tokens: int
    f_tokens: int
    k_tokens: int

def build_pack(...) -> PackResult: ...
```

`tool_defs`：对每个 tool 拼接 `name + description`（不要 dump 整个 schema JSON 以免测试脆）。

### `ChatAgent` 新签名

```python
class ChatAgent:
    def __init__(
        self,
        model: BaseChatModel,
        tools: list[BaseTool],
        notes: FileNoteRepository,
        drafts: DraftStore,
        history: ConversationStore,
        budget: ContextBudget,
        summarize_dropped: Callable[[str | None, str], str] | None = None,
    ) -> None: ...

    async def stream(
        self,
        question: str,
        thread_id: str,
        turn_id: str,
    ) -> AsyncIterator[dict]: ...

    def review(...) -> dict:  # 不变

    async def summarize_on_exit(self, thread_id: str) -> None:
        """No-op. Log that context.md memory is disabled. Do not write notes/."""
```

`summarize_dropped(old_summary, dropped_text) -> str`：只生成 **新段落**。默认实现用 `model.invoke` 一次，提示词必须写明「不要改写已有摘要，只摘要被移出的对话，保住用户任务」。测试传入 `lambda old, text: "SUM:" + text[:80]`。

**禁止** `create_agent(..., checkpointer=InMemorySaver())` 作为跨 Turn 记忆。本 Turn 内用局部 `messages: list` 变量；函数返回后丢弃。

### 路由

`POST /chat`：

```python
turn_id = start_turn()
history.append_message(record.id, "user", require.question, turn_id=turn_id)
...
async for item in agent.stream(require.question, thread_id=record.id, turn_id=turn_id):
    ...
if assistant_text:
    history.append_message(record.id, "assistant", assistant_text, turn_id=turn_id)
```

`POST /chat/user_exit`：仍 200 `{status: finished}`，调用 `summarize_on_exit`（空实现）。前端 `sendBeacon` **不用改**。

`FakeAgent.stream` 增加参数 `turn_id: str | None = None` 以免集成测炸。

---

## 流程图（实现时对照）

```text
POST /chat
  start_turn -> append user
  ChatAgent.stream:
    load summary + persistent after watermark
    pack external (runtime=[])
    if pack_tokens >= 80%W: compact (drop old complete turns, append summary, set watermark)
    reload persistent; pack again
    loop:
      bind_tools.astream(messages) -> yield token
      if tool_calls:
        execute tool (full result)
        append_tool_stub immediately
        append AIMessage(tool_calls)+ToolMessage(full) to runtime/messages
        pack internal; if >=80%W: compact old complete turns only; rebuild messages
        continue
      else:
        break
    discard runtime
  router append assistant (same turn_id)
```

---

### Task 0: 对照契约，不写代码

**Files:** 无

- [ ] **Step 1:** 通读 [context-management.md](../architecture/context-management.md) §1–9 与 [database.md](../architecture/database.md) §4 实例。
- [ ] **Step 2:** 确认函数名用本文锁定名，表用 `conversations`/`messages`，不自创 `MemoryManager` / `PostgresSaver`。
- [ ] **Step 3:** 单测用 SQLite；`alembic upgrade head` 仅本机有 Postgres 时在 Task 10 尝试。不要猜密码。

Verify：无命令。进入 Task 1。

---

### Task 1: Settings + ContextBudget

**Files:**

- Modify: `src/noteagent/bootstrap/settings.py`
- Create: `src/noteagent/chat/context_budget.py`
- Modify: `.env.example`
- Test: `tests/unit/test_context_tokens.py` 里不要测 Settings；本 Task 可把 budget 测试放进 `tests/unit/test_context_budget.py`（新建）

**Interfaces:** Produces `ContextBudget` 与 `budget_from_settings`。

- [ ] **Step 1: 写失败测试**

```python
from noteagent.bootstrap.settings import Settings
from noteagent.chat.context_budget import budget_from_settings

def test_budget_from_explicit_settings():
    b = budget_from_settings(Settings(
        chat_context_window=32768,
        context_trigger_ratio=0.8,
        context_target_ratio=0.6,
        context_stub_preview_tokens=1000,
        context_args_preview_chars=500,
        context_output_reserve=1024,
        context_safety_buffer=512,
    ))
    assert b.window == 32768
    assert b.stub_preview_tokens == 1000
    assert b.trigger_tokens() == int(32768 * 0.8)
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_context_budget.py -v` → FAIL（模块不存在）。
- [ ] **Step 3:** 实现 `ContextBudget`、`budget_from_settings`、Settings 七个字段。
- [ ] **Step 4:** 再跑同一命令 → PASS。
- [ ] **Step 5:** `.env.example` 追加键（无密钥）。

---

### Task 2: ORM + Alembic

**Files:**

- Modify: `src/noteagent/db/models.py`
- Modify: `src/noteagent/db/README.md`（补新列一句）
- Create: `alembic/versions/<rev>_context_watermark_and_tool_stubs.py`（`uv run alembic revision --autogenerate -m "context_watermark_and_tool_stubs"` 后手工补回填）

**Interfaces:** `Conversation.running_summary`、`Conversation.summary_watermark_turn_id`、`Message` 新列。

- [ ] **Step 1:** 改 models：Conversation 两列；Message 六列 + Boolean `truncated` default `False`；索引 `ix_messages_conversation_turn`。
- [ ] **Step 2:** 生成迁移。`upgrade` 必须：`op.add_column`；旧 `messages.turn_id` 可空；回填逻辑用 SQL 或 connection.execute 按会话扫行。SQLite 与 Postgres 都要能跑 `add_column`（Alembic 标准）。
- [ ] **Step 3:** 单测不跑 alembic；用 `Base.metadata.create_all` 验证新列存在：

```python
def test_models_have_context_columns():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    assert "running_summary" in Conversation.__table__.c
    assert "turn_id" in Message.__table__.c
```

把该测试放进 `tests/unit/test_context_store.py` 文件顶部或 `tests/unit/test_chat_history.py`。本 Task 先放 `test_context_store.py`。

- [ ] **Step 4:** `uv run pytest tests/unit/test_context_store.py::test_models_have_context_columns -v` → PASS。

不要在本 Task 改 `append_message` 签名（否则全仓单测红）。若 `create_all` 后旧测试仍 PASS：`uv run pytest tests/unit/test_chat_history.py -q`。

---

### Task 3: ConversationStore 扩展

**Files:**

- Modify: `src/noteagent/chat/history.py`
- Modify: `tests/unit/test_chat_history.py`（所有 `append_message` 补 `turn_id=`）
- Modify: `tests/unit/test_context_store.py`（本 Task 主测）
- Modify: `tests/integration/test_app.py`（`append_message` 补 `turn_id=start_turn()`）

**Interfaces:** 上文锁定的 Store 方法。Consumes Task 2 列。

辅助：

```python
def _uuid(turn_id: str) -> uuid.UUID:
    return uuid.UUID(turn_id)
```

`list_persistent_after_watermark` 实现要点：

1. 取出该会话全部 messages（所有 role），`order_by created_at, id`。
2. `group_turns` 可在本 Task **先写一个 Store 内私有分组**，Task 4–5 再换成共享 `group_turns`。为避免重复，**本 Task 直接 import 将在 Task 5 创建的 `group_turns`** —— 顺序冲突。因此：本 Task 在 `history.py` 写私有 `_turns_after_watermark(rows, watermark) -> list[Message]`：按 `turn_id` 分组，组顺序 = 该组第一条的 created_at；找到 watermark 组下标 `i`，返回 `groups[i+1:]` 展平。watermark 为 None 返回全部。

- [ ] **Step 1: 写测试**（`tests/unit/test_context_store.py`）

```python
def test_append_requires_turn_id(store):
    c = store.create("t")
    tid = start_turn()
    m = store.append_message(c.id, "user", "hi", turn_id=tid)
    assert m.turn_id == tid
    assert m.role == "user"

def test_list_messages_hides_tool_stubs(store):
    c = store.create("t")
    tid = start_turn()
    store.append_message(c.id, "user", "hi", turn_id=tid)
    store.append_tool_stub(
        c.id, turn_id=tid, tool_name="read_file",
        arguments='{"file_name":"A.md"}', output="x" * 200,
        status="ok", stub_preview_tokens=2, args_preview_chars=500,
    )
    store.append_message(c.id, "assistant", "done", turn_id=tid)
    ui = store.list_messages(c.id)
    assert [x.role for x in ui] == ["user", "assistant"]
    pers = store.list_persistent_after_watermark(c.id)
    assert [x.role for x in pers] == ["user", "tool", "assistant"]
    stub = pers[1]
    assert stub.truncated is True
    assert estimate_tokens(stub.output_preview) <= 2
    # updated_at: tool must not bump
    conv = store.get(c.id)
    # after assistant, updated_at changes; check tool didn't change by capturing between user and tool
```

补一条：user 之后记下 `updated_at`，写 stub，`get().updated_at` 相等（比较到秒即可，或比较同一 datetime）。

```python
def test_watermark_hides_summarized_turns(store):
    c = store.create("t")
    t1, t2 = start_turn(), start_turn()
    store.append_message(c.id, "user", "u1", turn_id=t1)
    store.append_message(c.id, "assistant", "a1", turn_id=t1)
    store.append_message(c.id, "user", "u2", turn_id=t2)
    store.append_message(c.id, "assistant", "a2", turn_id=t2)
    store.apply_compact(c.id, summary_append="old talk", watermark_turn_id=t1)
    tail = store.list_persistent_after_watermark(c.id)
    assert [x.content for x in tail] == ["u2", "a2"]
    rec = store.get(c.id)
    assert rec.running_summary == "old talk"
    assert rec.summary_watermark_turn_id == t1
    store.apply_compact(c.id, summary_append="newer", watermark_turn_id=t2)
    assert store.get(c.id).running_summary == "old talk\n\nnewer"
```

```python
def test_append_message_rejects_tool_role(store):
    c = store.create("t")
    with pytest.raises(ValueError):
        store.append_message(c.id, "tool", "x", turn_id=start_turn())
```

- [ ] **Step 2:** 跑 `uv run pytest tests/unit/test_context_store.py -v` → FAIL。
- [ ] **Step 3:** 实现 Store；改所有旧 `append_message` 调用。`test_chat_history.py` 每个成功路径：

```python
tid = start_turn()
store.append_message(record.id, "user", "hi", turn_id=tid)
```

级联删除测试同样补 `turn_id`。

- [ ] **Step 4:** `uv run pytest tests/unit/test_chat_history.py tests/unit/test_context_store.py tests/integration/test_app.py -q` → PASS。

---

### Task 4: estimate_tokens

**Files:**

- Create: `src/noteagent/chat/context_tokens.py`
- Create: `tests/unit/test_context_tokens.py`

```python
def test_empty_is_zero():
    assert estimate_tokens("") == 0

def test_four_chars_is_one():
    assert estimate_tokens("abcd") == 1

def test_five_chars_is_two():
    assert estimate_tokens("abcde") == 2  # (5+3)//4 == 2
```

- [ ] 先测再实现。`uv run pytest tests/unit/test_context_tokens.py -v`

---

### Task 5: compact 纯函数

**Files:**

- Create: `src/noteagent/chat/context_compact.py`
- Create: `tests/unit/test_context_compact.py`

**Consumes:** `MessageRecord`（可在测试里手工构造 dataclass）、`estimate_tokens`、`ContextBudget`。

构造助手：

```python
from datetime import datetime, timezone
from noteagent.chat.history import MessageRecord

def _rec(turn, role, content, i="00000000-0000-0000-0000-000000000001"):
    return MessageRecord(
        id=i, conversation_id="c", role=role, content=content,
        created_at=datetime.now(timezone.utc), turn_id=turn,
        tool_name=None, tool_arguments=None, output_preview=None,
        truncated=False, status=None,
    )
```

必须覆盖的测试：

1. `group_turns` 两 Turn 顺序、complete 标志。
2. `select_turns_to_drop`：K 小到只能留下最新 complete + current；更早 complete 进 drop。
3. 不拆 Turn：一个大 Turn tokens > K 时，若它是唯一可留的 complete，仍 keep。
4. `current_turn_id` 对应 bundle 永不进 drop。
5. `concat_summary(None,"x") == "x"`；`concat_summary("a","b") == "a\\n\\nb"`。
6. `should_compact(80, ContextBudget(window=100, trigger_ratio=0.8))` 为 True；`79` False（`trigger_tokens=80`）。
7. `compute_f` 含 reserve+buffer。

- [ ] **Step 1:** 写上述测试（完整 assert，不要 `assert True`）。
- [ ] **Step 2:** FAIL。
- [ ] **Step 3:** 实现。
- [ ] **Step 4:** `uv run pytest tests/unit/test_context_compact.py -v` PASS。

`select_turns_to_drop` 参考实现逻辑（必须遵守，可改写但行为一致）：

```python
def select_turns_to_drop(bundles, *, current_turn_id, k_tokens):
    current = [b for b in bundles if b.turn_id == current_turn_id]
    others = [b for b in bundles if b.turn_id != current_turn_id]
    complete = [b for b in others if b.complete]
    incomplete = [b for b in others if not b.complete]
    keep_rev: list[TurnBundle] = []
    used = 0
    for b in reversed(complete):
        if keep_rev and used + b.tokens > k_tokens:
            break
        if not keep_rev and b.tokens > k_tokens:
            keep_rev.append(b)
            break
        keep_rev.append(b)
        used += b.tokens
    keep_completed = list(reversed(keep_rev))
    keep_ids = {x.turn_id for x in keep_completed}
    drop = [b for b in complete if b.turn_id not in keep_ids]  # complete 已是旧→新
    keep = incomplete + keep_completed + current
    return drop, keep
```

```

---

### Task 6: pack

**Files:**

- Create: `src/noteagent/chat/context_pack.py`
- Create: `tests/unit/test_context_pack.py`

- [ ] 测试 `draft_workspace_line(None) is None`。
- [ ] 测试 `stub_text` 含 `name=` 与 `preview=`。
- [ ] 测试 `build_pack`：persistent 含当前 turn 的 tool 行且 `runtime_messages` 有一条长 `ToolMessage` 时，返回的 messages **文本不含 stub_text 那一行**，但含 ToolMessage 全文。
- [ ] 测试 `build_pack`：无 runtime 时 messages 含 system + 一条 HumanMessage；`pack_tokens >= f_tokens`；给巨大 `runtime_messages`（`ToolMessage(content="r"*4000)`）时 `f_tokens` 明显变大。

LangChain 导入与现有 agent 一致：`from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage`。

若 `ToolMessage` 不在 `langchain.messages`，用 `langchain_core.messages.ToolMessage`。

- [ ] `uv run pytest tests/unit/test_context_pack.py -v`

---

### Task 7: ChatAgent 循环、stub、压缩、去掉 context.md

**Files:**

- Modify: `src/noteagent/chat/agent.py`
- Modify: `src/noteagent/chat/drafts.py`（增加 `current_turn_id: ContextVar[str] = ContextVar("noteagent_turn_id", default="")`）
- Modify: `src/noteagent/bootstrap/app.py`（构造 ChatAgent 传入 `history` 与 `budget_from_settings(settings)`）
- Modify: `src/noteagent/chat/prompts/system.txt`（删「首轮可能已附带 context.md」整段；改为：上下文由系统注入历史摘要与近期对话，需要笔记正文时用工具读取。）

**Consumes:** Task 3–6。

**禁止：** `_opening_messages` 读取 `context.md`；`InMemorySaver`；`create_agent`。

`stream` 必须遵守：`messages = pack_now().messages`（runtime 已在 pack 内）。`run_compact_if_needed` **同步**。`drop` 按时间旧→新，`watermark_turn_id = drop[-1].turn_id`，且 `!= turn_id`。

```python
async def stream(self, question, thread_id, turn_id):
    token = current_thread_id.set(thread_id)
    token2 = current_turn_id.set(turn_id)
    try:
        runtime: list = []
        tool_map = {t.name: t for t in self._tools}
        tool_defs = "\n".join(f"{t.name}: {t.description}" for t in self._tools)
        system = self._prompt_path.read_text(encoding="utf-8")

        def pack_now() -> PackResult:
            conv = self._history.get(thread_id)
            return build_pack(
                system_prompt=system,
                tool_defs=tool_defs,
                summary=conv.running_summary if conv else None,
                persistent=self._history.list_persistent_after_watermark(thread_id),
                current_turn_id=turn_id,
                current_user=question,
                draft_line=draft_workspace_line(self._drafts.get(thread_id)),
                runtime_messages=runtime,
                budget=self._budget,
            )

        def run_compact_if_needed(pack: PackResult) -> None:
            if not should_compact(pack.pack_tokens, self._budget):
                return
            drop, _keep = select_turns_to_drop(
                group_turns(self._history.list_persistent_after_watermark(thread_id)),
                current_turn_id=turn_id,
                k_tokens=pack.k_tokens,
            )
            if not drop:
                _logger.warning("compact skipped conversation=%s no droppable complete turns", thread_id)
                return
            conv = self._history.get(thread_id)
            chunk = self._summarize_dropped(conv.running_summary if conv else None, format_turns_for_summary(drop))
            last = drop[-1].turn_id
            if last == turn_id:
                _logger.error("compact refused watermark=current turn conversation=%s", thread_id)
                return
            self._history.apply_compact(thread_id, summary_append=chunk, watermark_turn_id=last)
            _logger.info(
                "compact conversation=%s dropped=%s F=%s K=%s pack=%s",
                thread_id, [b.turn_id for b in drop], pack.f_tokens, pack.k_tokens, pack.pack_tokens,
            )

        bound = self._model.bind_tools(self._tools)
        while True:
            pack = pack_now()
            run_compact_if_needed(pack)
            pack = pack_now()
            assembled_ai = None
            async for chunk in bound.astream(pack.messages, config={"callbacks": [AgentTraceHandler()]}):
                text = _chunk_text(chunk.content)
                if text:
                    yield {"event": "token", "data": text}
                assembled_ai = chunk if assembled_ai is None else assembled_ai + chunk
            ai = assembled_ai
            if ai is None or not getattr(ai, "tool_calls", None):
                break
            runtime.append(ai)
            for call in ai.tool_calls:
                name = call["name"] if isinstance(call, dict) else getattr(call, "name")
                args = (call.get("args") if isinstance(call, dict) else getattr(call, "args", None)) or {}
                call_id = call["id"] if isinstance(call, dict) else getattr(call, "id")
                try:
                    raw = await tool_map[name].ainvoke(args)
                    status = "ok"
                except Exception as exc:
                    raw = {"error": str(exc)}
                    status = "error"
                out = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                self._history.append_tool_stub(
                    thread_id, turn_id=turn_id, tool_name=name,
                    arguments=json.dumps(args, ensure_ascii=False),
                    output=out, status=status,
                    stub_preview_tokens=self._budget.stub_preview_tokens,
                    args_preview_chars=self._budget.args_preview_chars,
                )
                runtime.append(ToolMessage(content=out, tool_call_id=call_id))
        pending = self._drafts.get(thread_id)
        if pending is not None:
            yield {"event": "draft", "data": pending.as_dict()}
    finally:
        current_thread_id.reset(token)
        current_turn_id.reset(token2)
```

`tool_calls` 元素可能是 dict 或对象，用 `.get` / 属性两种都要能跑。

流式：优先 `astream` 合并 chunk。若工具调用流式不稳定：该 hop 改 `ainvoke`，token 对最终 `AIMessage.content` **一次 yield**。

默认摘要器：

```python
def _default_summarize(self, old: str | None, dropped: str) -> str:
    prompt = (
        "下面「已有摘要」不要改写。"
        "只摘要「移出窗口的对话」，保住用户任务目标。"
        "只输出新摘要段落。\n\n"
        f"已有摘要：\n{old or '（空）'}\n\n移出的对话：\n{dropped}"
    )
    return _chunk_text(self._model.invoke([HumanMessage(content=prompt)]).content)
```

`summarize_on_exit`：只打日志，**不写** `notes/`。

单测（`tests/unit/test_chat_agent_context.py`）：

- 用假 model：第一次 `ainvoke/astream` 返回带 `tool_calls` 的 AIMessage（name=`list_files`），第二次返回纯文本 `"ok"`。
- 用真 `ConversationStore` sqlite + 真 `build_chat_tools`（notes 指向 tmp_path）或假 tool。
- Assert：`list_persistent_after_watermark` 含 `role=='tool'` 且 `estimate_tokens(output_preview) <= budget.stub_preview_tokens`。
- Assert：`list_messages` 在 router 写入 assistant 前可能只有 user；本测试在 stream 结束后手动 `append_message assistant`，UI 仍无 tool。
- 第二轮 `stream` 新 `turn_id`：假 model 记录收到的 messages，**不得**含上一 Turn `ToolMessage` 全文（长输出只允许 stub 预览）。

假模型最小写法：自定义 class 继承 `BaseChatModel` 太重。允许：

```python
class ScriptedModel:
    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []
    def bind_tools(self, tools):
        return self
    async def astream(self, messages, config=None):
        self.seen.append(messages)
        yield self.replies.pop(0)
    def invoke(self, messages):
        from langchain.messages import AIMessage
        return AIMessage(content="SUMCHUNK")
```

脚本回复必须是带 `.content` 与 `.tool_calls` 的对象。可用 `AIMessage(content="", tool_calls=[{"name":"list_files","id":"c1","args":{}}])` 与 `AIMessage(content="done")`。

若 `bind_tools` 在真 `BaseChatModel` 才有：ScriptedModel 自己实现 `bind_tools` 返回 self。

- [ ] `uv run pytest tests/unit/test_chat_agent_context.py -v`
- [ ] `ChatAgent(...)` 所有生产构造点已传 `history`、`budget`。

---

### Task 8: 路由接 turn_id；集成测；user_exit 不再写盘

**Files:**

- Modify: `src/noteagent/chat/router.py`
- Modify: `tests/integration/test_app.py`

- [ ] `POST /chat` 使用 `start_turn` + `append_message(..., turn_id=)`，`stream(..., turn_id=turn_id)`。
- [ ] 集成测：`FakeAgent.stream(self, question, thread_id, turn_id=None)`。
- [ ] 新集成测：`test_messages_api_hides_tool_stubs`：create 会话，append user、`append_tool_stub`、append assistant，`GET /conversations/{id}/messages` 只有 2 条。
- [ ] `test_user_exit_does_not_create_context_md`：notes 目录无 `context.md`；POST `/chat/user_exit` 仍 200。

```python
def test_user_exit_does_not_create_context_md(tmp_path):
    client, history = _client(tmp_path)
    rec = history.create("t")
    res = client.post("/chat/user_exit", json={"question": "", "thread_id": rec.id})
    assert res.status_code == 200
    assert res.json()["status"] == "finished"
    assert not (tmp_path / "context.md").exists()
```

- [ ] `uv run pytest tests/integration/test_app.py tests/unit -q`

---

### Task 9: 文档与现状 README

**Files:**

- Modify: `src/noteagent/chat/README.md`（stream 需要 `turn_id`；记忆 = PG + summary；无 InMemorySaver）
- Modify: `src/noteagent/db/README.md`
- Modify: `docs/architecture/context-management.md` 文首 `状态` → `已按本文改代码`
- Modify: `docs/architecture/database.md` 文首 `状态` → 上下文列已迁移；删「尚未建」
- Modify: `docs/architecture/architecture.md` 4.2.2.5 代码现状：跨回合 = watermark 后 Persistent + running_summary；当前 Turn Runtime 全文；不写 context.md
- Modify: `docs/plans/README.md` 本文件说明改为「已实现，待审查」

不要改 DESIGN.md。不要大段复制契约。

---

### Task 10: 全量验证

- [ ] `uv run pytest tests/unit tests/integration -q` 全绿。
- [ ] 若本机有 Postgres：`uv run alembic upgrade head`。不要猜密码。
- [ ] 对照契约 §8 自检清单（写进最终汇报，不要只在心里勾）：

1. 同一会话第二句：模型输入含未压缩 Persistent（含更早 user），**不含**上一 Turn `read_file` 全文。
2. 进程重启：能装 summary + watermark 之后记录 + stub；UI 历史完整（需手工或集成测模拟 store 重开 engine）。
3. 一次 Turn 内两次工具：第二次 LLM 的 `runtime`/`messages` 含第一次 **全文**。
4. ≥80%W：只摘要更早完整 Turn；内部路径当前 Tool Result 仍完整。
5. summary 为拼接；watermark 不是当前未完成 turn。
6. GET messages 无 tool；无新的 context.md 记忆写入。

可选单测补强（若 Task 7 未覆盖 3/4）：在 `test_chat_agent_context.py` 用 ScriptedModel 第三次 replies 检查 `seen[1]` 含长 `ToolMessage`，`seen[2]`（下一 turn）不含。

---

## 审查 Agent 检查单（实现完成后由另一 Agent 执行）

对照仓库 diff，**不要**只看计划是否勾选：

- `InMemorySaver` / `create_agent` 是否已从 `agent.py` 消失
- `append_message` 是否仍允许不带 `turn_id`
- `list_messages` SQL 是否过滤 tool
- `append_tool_stub` 是否更新 `updated_at`（禁止）
- `apply_compact` 是否重写整篇 summary 而非 concat
- `summarize_on_exit` 是否仍 `write("context.md")`
- 前端 `home.html` 是否被无关重构
- 压缩是否按条数 K 而非 token K

---

## Spec 覆盖（作者自审）

| 契约条款 | Task |
|----------|------|
| user 立刻入库 + turn_id | 3, 8 |
| 默认 watermark 后全量 | 3, 6, 7 |
| 禁止每次只取 K 条 | 5–7 无 limit() |
| 80% 触发 / T=60% / K=T−F | 1, 5, 6, 7 |
| 完整 Turn 切割 | 5 |
| 内部保护当前 Result | 5 `current_turn_id` + 7 runtime 全文 |
| 每步 stub | 7 |
| 最终 assistant 后丢 Runtime | 7 局部 list |
| 列表过滤 stub | 3, 8 |
| 停 context.md | 7, 8 |
| 摘要拼接 | 3 `apply_compact` + 5 `concat_summary` |
| 至少 1 个已完成 Turn | 5 |
| stub 前 N token（环境） | 1, 3 `prefix_until_tokens` |
| 配置不写死在 compact/agent | 1, 5, 7 |
| 会话一栏 running_summary 追加 | 3 `apply_compact` |
| 压缩日志 | 7 |
| AgentTraceHandler | 7 |
| Draft 一行 | 6, 7 |
