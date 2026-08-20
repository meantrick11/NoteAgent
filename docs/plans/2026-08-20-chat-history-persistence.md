# 对话历史持久化 Implementation Plan

> **For agentic workers:** 按 Task 0 → 10 **严格顺序**执行。每完成一个 Task 再进入下一个。步骤用 `- [ ]` 勾选。不要并行改多个 Task 以免集成测中途全红。
>
> **不要 git commit**，除非用户明确要求。
>
> **做完后不要自称完成。** 列出：改过的文件、每条跑过的 pytest 命令与通过/失败、Task 4/手工验收是否连上本机 Postgres。交给审查 Agent。

**Goal:** 单用户能在左侧看到历史会话、新建会话、点开会话看到完整气泡；刷新或重启后端后历史仍在。数据在本机 PostgreSQL。

**Architecture:** 用户可见历史只存在 PostgreSQL。`ConversationStore` 是唯一写入口。HTTP 在 `/chat` 里先插入 user 消息、SSE 推 `conversation`、再跑现有 `ChatAgent`、流结束后插入 assistant。`ChatAgent` 继续用 `InMemorySaver`，`thread_id` = `conversation.id`。前端不把 localStorage 当主库。

**Tech stack:** FastAPI、SQLAlchemy 2.0（已有）、psycopg3、Alembic、本机 PostgreSQL、现有 `home.html`（vanilla JS）。单测用 SQLite 内存库。

---

## 怎么执行（Claude 必读）

1. 打开本文件，从 **Task 0** 开始。Task 0 只检查环境，不写业务代码。
2. **服务停了 / 没有密码 / 没有管理员权限：不要停工等密码。** 立刻继续 Task 1–3、5–10（单测全是 SQLite）。**只有** `alembic upgrade head` 和浏览器手工验收必须等本机 Postgres。不要猜密码、不要让用户把密码发到聊天里。
3. 每个 Task 内：先按「Files」创建/修改；有测试的先写测试再写实现；最后跑该 Task 的 verify 命令。
3. 不要发明本计划没有的表、字段、路由、前端框架。
4. 仓库规范见根目录 `CLAUDE.md`：少改无关文件；新建 class/function 写功能注释；DB 操作打日志（conversation id，不要打完整消息正文、不要打完整 `DATABASE_URL`）。
5. Windows + PowerShell：用 `uv run ...`，不要假设 `bash` heredoc。

---

## 非目标（禁止）

- `users` 表、JWT、登录页
- LangGraph `PostgresSaver`
- 把历史消息灌回模型 / 滚动摘要 / 改 `context.md` 退出逻辑
- 改 `src/noteagent/chat/agent.py`
- Vue/React 重写前端
- 删除/重命名会话 API
- 把 draft 审批写入 `messages`
- 新建 `docker-compose.yml`、为完成本任务安装 Docker
- 运行时用 SQLite 代替 PostgreSQL（仅**单元测试**允许 SQLite）

**必须写明的产品边界：** 进程重启后 UI 有历史；模型不会自动带上旧轮次。不要「顺手」修好这件事。

---

## 全局约束

- 包路径：`src/noteagent/`。新建 `noteagent.db`。Store 放 `noteagent.chat.history`。
- `chat` 可以 import `noteagent.db`；`db` **不得** import `chat`。
- `pythonpath = src` 已在 `pyproject.toml`。
- 集成测手拼 `AppContainer`，见 `tests/integration/test_app.py`。不要在单测里调用会加载 SentenceTransformer 的完整 `build_container`（URL 校验测试除外，见 Task 6）。
- 本机 Postgres：`.env` 的 `DATABASE_URL` 必须是 `postgresql+psycopg://...`（不是 `postgresql://`）。

---

## 目标文件树（做完后应存在）

```text
alembic.ini
alembic/env.py
alembic/script.py.mako
alembic/versions/<rev>_conversations_and_messages.py
src/noteagent/db/__init__.py
src/noteagent/db/README.md
src/noteagent/db/engine.py
src/noteagent/db/models.py
src/noteagent/chat/history.py
tests/unit/test_chat_history.py
```

修改（不要换路径）：

```text
pyproject.toml
uv.lock          # 只通过 uv add 更新
.env.example
README.md
src/noteagent/README.md
src/noteagent/bootstrap/settings.py
src/noteagent/bootstrap/app.py
src/noteagent/bootstrap/README.md
src/noteagent/chat/schemas.py
src/noteagent/chat/router.py
src/noteagent/chat/README.md
src/noteagent/web/templates/home.html
tests/unit/test_settings.py
tests/integration/test_app.py
```

可选一行：`docs/architecture/knowledge-workflow-v1.md` 文首状态，说明「聊天展示历史已落 PG」。不要改 Job/RAG 章节。

---

## 架构（不要偏离）

```text
home.html --GET /conversations(+messages)--> chat.router --> ConversationStore --> PostgreSQL
home.html --POST /chat SSE----------------> chat.router --> ConversationStore --> PostgreSQL
                                         \-> ChatAgent --> InMemorySaver
```

用户可见历史 = PostgreSQL。Checkpoint ≠ 聊天库。后端追加，前端只展示。

---

### Task 0: 本机 PostgreSQL 前置

**Files:** 无。禁止为本任务改代码、装 Docker。

**做什么：** 确认本机 PostgreSQL **Windows 服务已启动**。建议：

```sql
CREATE DATABASE noteagent;
```

不要把业务表建进默认库 `postgres`。表本身等 Task 4 用 Alembic 建。

`.env`（仓库根，gitignore，不要提交）增加一行，账号密码端口换成你本机的：

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/noteagent
```

规则：

- 前缀必须 `postgresql+psycopg://`。`postgresql://` 会走未安装的 psycopg2。
- 密码里的 `@` `:` `/` 要 URL 编码。
- 端口不是 5432 就改 URL。

**verify：** 能连上 `noteagent` 库。`uv --version` 与 `uv run python --version`（≥3.13）可用。

**服务是 Stopped、Start-Service 报没权限：** 这是用户本机问题，实现 Agent 做不了。按下面「人类操作」处理；Agent 同时继续写代码。

**实现 Agent 禁止：** `net start` / `Start-Service`（通常要管理员）、猜测密码、把密码写进 git、为了连库去装 Docker。

- [ ] 有 `DATABASE_URL` 且能连上则 Task 0 完成。否则标「Postgres 待用户启动」，继续 Task 1。

#### 人类操作（你来做，不要交给无管理员权限的 Agent）

**1. 启动服务（管理员）：**

- Win + X →「终端（管理员）」或「Windows PowerShell（管理员）」：

```text
net start postgresql-x64-18
```

- 或 `Win + R` → `services.msc` → 找到 **postgresql-x64-18 - PostgreSQL Server 18** → 启动。可把启动类型改成「自动」，避免下次又停。

**2. 密码不要发到聊天里。** 你自己在仓库根 `.env` 加一行（用户名安装时一般是 `postgres`，端口一般是 `5432`）：

```text
DATABASE_URL=postgresql+psycopg://postgres:这里换成你的密码@127.0.0.1:5432/noteagent
```

密码里如果有 `@` `#` `:` `%` `/`，要做 URL 编码（`@` → `%40`）。

然后对实现 Agent 只说：「`.env` 已写 DATABASE_URL，服务已启动，继续 Task 4 建库/迁移。」不要把密码贴进对话。

**3. 忘了安装时的密码：** 服务先启动，再用 trust 改密码（典型路径 `C:\Program Files\PostgreSQL\18\data\pg_hba.conf`，以你机器为准）：

1. 用管理员记事本打开 `pg_hba.conf`
2. 把 `127.0.0.1/32` 和 `::1/128` 那两行的方法暂时改成 `trust`
3. 管理员 PowerShell：`net stop postgresql-x64-18` 再 `net start postgresql-x64-18`
4. `psql -U postgres -d postgres` 应能免密进入，执行：

```sql
ALTER USER postgres PASSWORD '你的新密码';
CREATE DATABASE noteagent;
```

5. 把 `pg_hba.conf` 改回 `scram-sha-256`（或原来的 `md5`），再重启服务
6. 把新密码写进 `.env` 的 `DATABASE_URL`，不要发聊天

**4. 库还没有：** 你或已有密码的 Agent 都可以执行 `CREATE DATABASE noteagent;`。没有密码时 Agent 不能建库。

---

### Task 1: 依赖与 Settings

**Files:**
- Modify: `pyproject.toml`（通过命令，不要手填假版本）
- Modify: `src/noteagent/bootstrap/settings.py`
- Modify: `.env.example`
- Modify: `tests/unit/test_settings.py`

**现有 Settings 位置：** `src/noteagent/bootstrap/settings.py` 的 `class Settings`。在 `log_level` 附近增加字段，保持 `SettingsConfigDict` 不变。

```python
database_url: str = Field(default="", validation_alias="DATABASE_URL")
```

- 默认 `""`，这样现有 `Settings()` 单测仍能构造。
- 不要用 `SecretStr`。日志禁止打印完整 URL。

`.env.example` 追加（示例用户名不要写成 docker 的 `noteagent:noteagent`）：

```text
# PostgreSQL. Prefix must be postgresql+psycopg://  (not postgresql://)
# DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@127.0.0.1:5432/noteagent
```

**测试**追加到 `tests/unit/test_settings.py`：

```python
def test_env_override_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:secret@127.0.0.1:5432/noteagent",
    )
    settings = Settings()
    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.database_url.endswith("/noteagent")
```

- [ ] 在仓库根执行：`uv add "psycopg[binary]" alembic`（保留已有 `sqlalchemy==2.0.51`，不要降到 1.x）
- [ ] 改 Settings、`.env.example`、测试
- [ ] `uv run pytest tests/unit/test_settings.py -v` 全绿

---

### Task 2: 根 README 写本机连库（不要 compose）

**Files:**
- Modify: `README.md` — 只加一小节，不要重写全文。

建议插在「启动」之后，标题如 `### PostgreSQL（对话历史）`：

1. 本机启动 PostgreSQL 服务
2. `CREATE DATABASE noteagent;`
3. `.env` 设置 `DATABASE_URL=postgresql+psycopg://...`
4. `uv run alembic upgrade head`（Task 4 之后才真正有迁移；现在先把步骤写上）
5. 再 `uv run python main.py`

环境变量表增加一行 `DATABASE_URL`。

**禁止：** 新建 `docker-compose.yml`。

- [ ] README 一小段
- [ ] `git status` 确认没有 compose 文件被添加

---

### Task 3: ORM 与 Engine

**Files:**
- Create: `src/noteagent/db/__init__.py`
- Create: `src/noteagent/db/README.md`
- Create: `src/noteagent/db/models.py`
- Create: `src/noteagent/db/engine.py`

`README.md` 写清：本包只放 Base、表、engine；不写 HTTP、不调 LLM。

`__init__.py` 导出：`Base`、`Conversation`、`Message`、`create_engine_from_url`、`create_session_factory`。

#### models.py（列名必须一致）

```text
conversations
  id           UUID PK
  title        TEXT NOT NULL
  created_at   timestamptz NOT NULL
  updated_at   timestamptz NOT NULL

messages
  id                UUID PK
  conversation_id   UUID NOT NULL FK → conversations.id ON DELETE CASCADE
  role              TEXT NOT NULL
  content           TEXT NOT NULL
  created_at        timestamptz NOT NULL
```

索引名：

- `ix_messages_conversation_created`：`(conversation_id, created_at)`
- `ix_conversations_updated_at`：`conversations.updated_at`

实现约束：

- `class Base(DeclarativeBase):`
- SQLAlchemy 2.0 `Mapped[]` / `mapped_column`
- UUID：`Uuid(as_uuid=True)` + `default=uuid.uuid4`。**不要** `postgresql.UUID`（SQLite 单测会挂）
- 时间：`DateTime(timezone=True)`，`default` 用 `lambda: datetime.now(timezone.utc)`。不要 `datetime.utcnow`
- `Conversation.messages` relationship，`cascade="all, delete-orphan"`
- `role` 不做 DB CHECK；Store 校验
- 本任务不加 `user_id`、JSONB

`models.py` 形状参考（可微调 import，不可改表名列名）：

```python
class Conversation(Base):
    """A single chat thread shown in the sidebar."""

    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    """One user or assistant bubble in a conversation."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )
```

`conversations.updated_at` 的 Index 写在 `Conversation.__table_args__`。

#### engine.py

```python
def create_engine_from_url(url: str) -> Engine:
    """Create a sync engine. Enable SQLite foreign keys and check_same_thread=False."""

def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)."""
```

SQLite（url 以 `sqlite:` 开头）必须：

- `connect_args={"check_same_thread": False}`
- `event.listen(engine, "connect", ...)` 里 `cursor.execute("PRAGMA foreign_keys=ON")`

Postgres URL 不要加 `check_same_thread`。

- [ ] 四个文件落地
- [ ] 冒烟（可选）：`uv run python -c "from noteagent.db import Base, create_engine_from_url; e=create_engine_from_url('sqlite:///:memory:'); Base.metadata.create_all(e)"`

---

### Task 4: Alembic 首迁

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py` 等（用命令生成再改）

在仓库根：

```text
uv run alembic init alembic
```

然后改 `alembic/env.py`：

- `from noteagent.bootstrap.settings import Settings`
- `from noteagent.db.models import Base`
- `target_metadata = Base.metadata`
- `url = Settings().database_url.strip()`；若空：`raise RuntimeError("DATABASE_URL is required for alembic")`
- `config.set_main_option("sqlalchemy.url", url)` 或在 `engine_from_config` 前写入
- **不要**把真实密码写进 `alembic.ini`
- `alembic.ini` 里 `sqlalchemy.url` 可留空占位

生成迁移（需能 import 模型；autogenerate 会连 `DATABASE_URL`，本机库要已存在）：

```text
uv run alembic revision --autogenerate -m "conversations and messages"
```

检查生成的 `alembic/versions/*.py`：两张表、两个索引、FK `ondelete="CASCADE"`。缺了就手改升级脚本，不要依赖「差不多」。

**verify：**

```text
uv run alembic upgrade head
```

pgAdmin/`psql` 看到 `conversations`、`messages`、`alembic_version`。连不上就停，不要把运行时改成 SQLite。

- [ ] init + 改 env.py
- [ ] autogenerate 并核对脚本
- [ ] `upgrade head` 成功

---

### Task 5: ConversationStore

**Files:**
- Create: `src/noteagent/chat/history.py`
- Create: `tests/unit/test_chat_history.py`

**禁止：** `router` 里 `session.add`。HTTP 只调 Store。

把 `conversation_title_from_question` 放在 `history.py`（router 与测试都 import 它）：

```python
def conversation_title_from_question(question: str, max_len: int = 40) -> str:
    """Collapse whitespace and truncate for the sidebar title."""
    text = " ".join(question.split())
    if not text:
        return "新对话"
    return text if len(text) <= max_len else text[:max_len]
```

DTO 与 Store **方法名必须如下**（后续 Task 按名字调用）：

```python
@dataclass(slots=True)
class ConversationRecord:
    id: str
    title: str
    created_at: datetime
    updated_at: datetime

@dataclass(slots=True)
class MessageRecord:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime


class ConversationStore:
    """Persist conversations and messages. One short-lived Session per method."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None: ...

    def create(self, title: str) -> ConversationRecord: ...

    def get(self, conversation_id: str) -> ConversationRecord | None: ...

    def list_conversations(self) -> list[ConversationRecord]:
        """Order by updated_at DESC, then created_at DESC."""

    def list_messages(self, conversation_id: str) -> list[MessageRecord] | None:
        """None if conversation missing; [] if empty. Order created_at ASC, id ASC."""

    def append_message(self, conversation_id: str, role: str, content: str) -> MessageRecord:
        """Insert message and bump conversations.updated_at.
        KeyError if conversation missing. ValueError if role not in {user, assistant}.
        """
```

实现要点：

- UUID 入参：`uuid.UUID(conversation_id)`，非法格式视为不存在（`get`/`list_messages` 返回 None；`append_message` raise `KeyError`）
- 每方法 `with self._session_factory() as session:`，成功 `commit`，异常 `rollback` 再 raise
- ORM → DTO 时 `id=str(row.id)`
- `create` 原样存 title（截断在 router）
- `append_message` **不改 title**
- 日志：`created conversation=%s`、`append role=%s conversation=%s chars=%d`

**先写测试** `tests/unit/test_chat_history.py`：

```python
@pytest.fixture
def store() -> ConversationStore:
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return ConversationStore(create_session_factory(engine))
```

必须覆盖：

- `conversation_title_from_question("  a   b  ") == "a b"`；空字符串 → `"新对话"`；超长截到 40
- create 后 get 同 id/title
- 空库 `list_conversations() == []`
- 先 A 后 B，list[0] 是 B
- 对 A append user 再 assistant，`list_messages` 顺序 user → assistant
- `list_messages` 未知 id → `None`
- `append_message` 未知 id → `KeyError`
- `append_message(..., "system", "x")` → `ValueError`
- CASCADE：用 **第二个** session 从 store 的 factory 删除 Conversation 后，messages 表计数为 0（不要只测 ORM 内存对象）。例如 `session.get(Conversation, uuid)` + `session.delete` + `commit`，再 `select(func.count()).select_from(Message)`

- [ ] 测试先红
- [ ] 实现 Store
- [ ] `uv run pytest tests/unit/test_chat_history.py -v` 全绿

---

### Task 6: 装配 AppContainer

**Files:**
- Modify: `src/noteagent/bootstrap/app.py`
- Modify: `src/noteagent/bootstrap/README.md`
- Modify: `tests/integration/test_app.py`
- Modify: `tests/unit/test_settings.py` 或新建 `tests/unit/test_app_container.py`（URL 校验）

现有 `AppContainer` 在 `app.py`，字段是 `settings, notes, retrieval, chat_agent`。改为增加：

```python
engine: Engine
history: ConversationStore
```

`build_container` **第一件事**（在创建 embedder **之前**）：

```python
if not settings.database_url.strip():
    _logger.error("DATABASE_URL is required (postgresql+psycopg://...)")
    raise ValueError("DATABASE_URL is required")
```

然后 `engine = create_engine_from_url(settings.database_url)`，`history = ConversationStore(create_session_factory(engine))`，放进 `AppContainer`。

`create_app` 增加 lifespan，shutdown 时 `container.engine.dispose()`。不要每个请求 dispose。形状：

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    app.state.container.engine.dispose()

def create_app(container: AppContainer) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.state.container = container
    app.include_router(chat_router)
    return app
```

**立刻修集成测**，否则 dataclass 缺字段。在 `tests/integration/test_app.py` 增加 helper：

```python
def _sqlite_history():
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, ConversationStore(create_session_factory(engine))
```

`_client` 里：

```python
engine, history = _sqlite_history()
container = AppContainer(
    settings=settings,
    notes=FileNoteRepository(tmp_path),
    retrieval=None,
    chat_agent=FakeAgent(),
    engine=engine,
    history=history,
)
```

URL 校验测试（不要加载 embedding）：把校验放在 `build_container` 开头后，可：

```python
def test_build_container_requires_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    settings = Settings()
    # 若 Settings 仍从 .env 读到真实 URL，改为 Settings(database_url="")
    with pytest.raises(ValueError, match="DATABASE_URL"):
        build_container(Settings(database_url=""))
```

若 `Settings(database_url="")` 仍被 `.env` 覆盖，用 `monkeypatch.delenv("DATABASE_URL", raising=False)` 再显式传空。**失败就改 Settings 测试方式，不要为了测试去连网下载模型。**

bootstrap README 表格加上 `engine` / `history`。

- [ ] 改容器、lifespan、测试构造
- [ ] `uv run pytest tests/unit/test_settings.py tests/unit/test_chat_history.py tests/integration/test_app.py -v`

---

### Task 7: GET 列表与消息

**Files:**
- Modify: `src/noteagent/chat/schemas.py`
- Modify: `src/noteagent/chat/router.py`
- Modify: `tests/integration/test_app.py`

`schemas.py` 增加（不要塞进 `RequestModel`）：

```python
class ConversationOut(BaseModel):
    id: str
    title: str
    updated_at: datetime

class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
```

`router.py` 现有 `APIRouter` 上增加（不要新建 router 文件）：

- `GET /conversations` → `list[ConversationOut]`，空列表 `[]` 是 200
- `GET /conversations/{conversation_id}/messages` → `list[MessageOut]`  
  Store 返回 `None` 时：`raise HTTPException(status_code=404, detail="conversation not found")`

取 Store：`request.app.state.container.history`。

日志：`list conversations count=%d`、`list messages conversation=%s count=%d`。

集成测：

- GET `/conversations` → 200 `[]`
- 用 `_client` 拿到的同一 container：`history.create("t")` + `append_message(..., "user", "hi")`，再 GET 列表长度 1，GET messages 长度 1
- GET `/conversations/00000000-0000-0000-0000-000000000001/messages` → 404

注意：`_client` 每次新建内存库。要在同一 client 上预置数据，把 `history` 留在闭包或改 `_client` 返回 `(client, history)`。推荐改成：

```python
def _client(tmp_path: Path) -> tuple[TestClient, ConversationStore]:
    ...
    return TestClient(create_app(container)), history
```

并改现有 `test_home_serves_template` / `test_chat_and_exit_routes` 为 `client, _ = _client(tmp_path)`。

- [ ] 路由 + 测试
- [ ] `uv run pytest tests/integration/test_app.py -v`

---

### Task 8: POST /chat 后端追加

**Files:**
- Modify: `src/noteagent/chat/schemas.py` 的 `RequestModel`
- Modify: `src/noteagent/chat/router.py` 的 `chat_with`
- Modify: `tests/integration/test_app.py`
- **不要改** `src/noteagent/chat/agent.py`

`RequestModel`：

```python
class RequestModel(BaseModel):
    """JSON body for /chat and /chat/user_exit."""

    question: str
    conversation_id: str | None = None
    thread_id: str | None = None
```

解析：`conv_id = require.conversation_id or require.thread_id`。  
`/chat/review` 继续用 `ReviewRequest.thread_id`（前端会把当前会话 id 填进去）。`/chat/user_exit` 本次不改行为。

`chat_with` **必须按此顺序**（不要先跑 Agent）：

1. `history = request.app.state.container.history`
2. `conv_id = require.conversation_id or require.thread_id`
3. 若 `conv_id` 为空：`record = history.create(conversation_title_from_question(require.question))`
4. 若有值：`record = history.get(conv_id)`；`None` 则 404 `conversation not found`，不要自动 create
5. `history.append_message(record.id, "user", require.question)`
6. **先** `yield ServerSentEvent(event="conversation", data=json.dumps({"id": record.id, "title": record.title}, ensure_ascii=False))`
7. `assistant_text = ""`
8. `async for item in agent.stream(require.question, thread_id=record.id):` 与现在一样 yield token/draft；若 `event=="token"` 且 data 是 str，拼到 `assistant_text`
9. 循环结束后若 `assistant_text`：`history.append_message(record.id, "assistant", assistant_text)`

`json.dumps` 必须用。前端 `JSON.parse`。不要 `str(dict)`。

FakeAgent 保持：

```python
yield {"event": "token", "data": f"echo:{question}"}
```

集成测增加（同一 `history`）：

1. `POST /chat` body `{"question":"你好"}`（无 id）→ 200 SSE；文本含 `event: conversation`；从 data 行 `JSON.parse` 得到 `id`；`GET /conversations/{id}/messages` 两条，roles `user`/`assistant`，assistant 含 `echo:你好`
2. `POST /chat` `{"question":"x","conversation_id":"00000000-0000-0000-0000-000000000001"}` → 404
3. 用步骤 1 的 id：`POST /chat` `{"question":"第二轮","thread_id": id}` → messages 共 4 条

解析 SSE 时注意 FastAPI TestClient：`response.text` 里 `event: conversation` 与 `data: {...}` 成对。不要假设只有 token。

现有 `test_chat_and_exit_routes` 仍应通过：它 POST `thread_id: "t1"`。这会走「有 id」分支，`get("t1")` 为 None → **404**，会打破旧测试。

**处理方式（选这个，不要改 FakeAgent 去建会话）：** 旧测试改为不传 `thread_id`，只传 `question`，让后端 create；或测试里先 `history.create` 再用返回的真实 UUID 当 `thread_id`。推荐：**先 create 再 chat**，与「坏 id 404」一致。

```python
record = history.create("t")
chat = client.post("/chat", json={"question": "你好", "thread_id": record.id})
```

- [ ] 写路径 + 修旧测试 + 新测试
- [ ] `uv run pytest tests/integration/test_app.py tests/unit/test_chat_history.py -v`

---

### Task 9: 前端侧栏

**Files:**
- Modify: `src/noteagent/web/templates/home.html` 仅 HTML/CSS/JS。不要 Vue。不要 localStorage 当主存储。

**现有锚点（以文件为准，行号大约）：**

- 侧栏 `.sidebar-body` 内 placeholder「对话历史（后续实现）」
- `let currentThreadId = "1";`
- `function newChat()`
- `ask()` 的 `JSON.stringify({ question, thread_id: currentThreadId })`
- `sendReview` 的 `thread_id: currentThreadId`

**HTML：** `.sidebar-body` 改为：

```html
<div class="sidebar-body">
  <div id="conversationList"></div>
  <p class="placeholder" id="historyEmpty">暂无对话</p>
</div>
```

**CSS：** 列表项 padding、cursor、选中项 `background: var(--bg)`。不要新主色。

**JS：**

```javascript
let currentConversationId = null;
```

删除 `"1"`。

实现：

- `loadConversations()`：`GET /conversations`，渲染 `#conversationList`；空则显示 `#historyEmpty`，否则 hide
- 每项 `dataset.id`，点击 `openConversation(id)`
- `openConversation(id)`：`GET /conversations/${id}/messages`；清空 `#chatInner`；对每条消息调现有 `appendMessage`；`role==="assistant"` 时 `body` 用 `marked.parse(content)`；设 `currentConversationId`；给对应列表项加 `active`
- `newChat()`：`currentConversationId = null`；恢复 welcome HTML（与现在一致）；去掉 `active`；**禁止** POST 创建会话
- `DOMContentLoaded`：`loadConversations()` 后若 `list.length` 则 `openConversation(list[0].id)`
- `ask()`：`body: JSON.stringify({ question, conversation_id: currentConversationId })`。`null` 时字段为 `null` 或省略均可
- SSE：`eventName === "conversation"` 且 payload 为对象：`currentConversationId = payload.id`，再 `loadConversations()` 并高亮
- `sendReview`：`thread_id: currentConversationId`

刷新后必须再 GET，不要只靠内存数组当真相。

`tests/integration/test_app.py` 的 `test_home_serves_template` 仍只检查页面含 `NoteAgent`。可加：`assert "conversationList" in response.text`。

- [ ] 改 home.html
- [ ] `uv run pytest tests/integration/test_app.py -v`

---

### Task 10: 模块 README 契约

**Files:**
- Modify: `src/noteagent/chat/README.md` — 路由表增加两个 GET；`POST /chat` 写 `conversation_id` 可选、`event: conversation`；注明 InMemorySaver 重启不恢复模型上下文
- Modify: `src/noteagent/README.md` — 子包表增加 `db/`
- 核对: `src/noteagent/db/README.md`、`src/noteagent/bootstrap/README.md`
- 可选一行: `docs/architecture/knowledge-workflow-v1.md` 文首

不要新增长文、不要复制本 plan 进 README。

- [ ] README 与实现一致

---

## 全量验证（全部 Task 完成后）

```text
uv run pytest -q
uv run alembic upgrade head
uv run python main.py
```

浏览器 `http://127.0.0.1:8000`：

1. 空库：欢迎页 + 空侧栏
2. 发一条：侧栏出现会话；刷新气泡仍在
3. 新对话再发一条：侧栏两条；点第一条只显示第一会话
4. 停掉再启动 `main.py`，刷新，历史仍在

---

## 给审查 Agent 的清单

有一条失败就记缺陷，不要只看 pytest 绿：

1. 无 users/JWT/PostgresSaver；未改 `agent.py` 灌历史
2. 表/列/索引/FK CASCADE 与 Task 3 一致
3. `/chat`：无 id 则 create；先 user 后 assistant；坏 id 404；SSE `conversation` 为 JSON 字符串
4. 前端无 localStorage 主存储；刷新走 GET
5. 单测不连真实 PG；集成测不调真实 LLM
6. `build_container` 空 URL 在 embedder 之前失败
7. `db` 不 import `chat`；未改无关 retrieval/tools
8. 日志有 conversation id；无完整 DATABASE_URL；无密钥
9. 无 `docker-compose.yml` 因本任务新增
10. 手工重启后端后 UI 历史仍在；未验证则标「未验证」
11. 若把全量 messages 灌进 Agent，记范围蔓延
