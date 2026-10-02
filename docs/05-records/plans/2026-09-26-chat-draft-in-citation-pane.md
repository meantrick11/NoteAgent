# Chat 草稿显示在右侧引用面板：实现计划

> **交给 Claude 执行：**按任务顺序实现，每步执行并记录其验证结果。沿用仓库现有 Python、FastAPI 与原生 JavaScript 约定；先阅读 `CLAUDE.md`、相关模块 README、本文引用的实现和适用 `AGENTS.md`。保留用户已有改动，不自动提交、推送、合并或发布。

**目标：**AI 提出笔记草稿后，聊天助手气泡用简短文字说明已生成待审草稿，草稿正文、编辑和审批操作出现在现有右侧引用面板。

**架构：**扩展现有 cite pane 为按会话隔离的两种显示状态：引用笔记模式继续读写正式 Markdown；待审草稿模式读取并编辑 `conversations.pending_draft`，编辑保存只更新待审草稿，用户审批后才走既有 `POST /chat/review` 落盘。SSE `draft` 和会话恢复都进入草稿模式；取消/审批完成后清除面板草稿状态。保留草稿 action、目标文件、reason、similar、existing_files 及 create/append/replace/delete/override 的既有业务语义。

**技术栈：**FastAPI、Pydantic、SQLAlchemy、原生 JavaScript、pytest、现有 Markdown 编辑面板。

**需求依据：**用户要求将独立审批气泡卡片改为助手简短说明 + 右侧引用同款区域展示草稿；右侧可编辑；新建等草稿功能不变，其余功能和设计保持不变。现有实现位置见 `docs/architecture/frontend.md`、`src/noteagent/web/templates/home.html`、`src/noteagent/chat/{router.py,schemas.py,drafts.py,history.py}`。

## 执行结果摘要（2026-09-26 回填）

分支 `feat/draft-in-cite-pane`，三个任务各一个 Conventional Commit。实现与浏览器验证结果如下。

| 任务 | 状态 | 结果 |
|------|------|------|
| 1 持久化草稿正文 | 完成 | `DraftStore.update_content` + `ChatAgent.update_draft_content` + `PUT /chat/draft`（200 / 404 / 409 / 422 / 403）；只改 `pending_draft`，不动正式笔记与索引 |
| 2 面板接入 cite pane | 完成 | 面板分 citation / draft 两模式；草稿卡片与 `.draft-card` 样式删除；保存草稿、批准/拒绝/override、按会话隔离、未保存确认、会话恢复均按计划 |
| 3 架构说明与核对 | 完成 | frontend.md / chat-tools.md 更新；`renderDraftCard`、`.draft-card` 检索无残留 |
| 自动测试 | 通过 | `pytest tests` 488 passed（较改动前 +10），0 failed |
| 浏览器验证 | 完成 | 隔离实例（SQLite + 临时 notes 目录，端口 8123，不碰真实库与 `notes/`）实测，见下 |

浏览器实测记录（每项都做了实际交互，不是只读代码）：

- create / append / replace / delete 四种草稿的标题、徽标、确认语与按钮；create 与 append 有覆写控件（select 与文件名输入），replace 与 delete 没有；delete 无正文时「保存草稿」禁用。
- override 两条路径：改为新建文件（改名 `Renamed.md` 后落盘）、改为追加到所选文件（`Python.md`，`Go.md` 未被改动）。
- 编辑 → 保存草稿：`pending_draft` 正文更新、`action/file_name/reason/similar/existing_files` 保留、`notes/` 未变；刷新后草稿模式恢复编辑后的正文。
- 有未保存修改时直接批准：先 `PUT /chat/draft` 再 `/chat/review`，文件里是改过的正文明细。
- 拒绝：草稿清空、面板关闭、文件未变、不加索引。
- 审批失败重试：服务端无草稿时返回 409，面板保留草稿与动作选择、按钮恢复可用、提示「审批失败：no pending draft，可修正后重试」。
- 引用模式回归：点 ① 打开正式笔记并定位片段、编辑后「保存到 Markdown」写入文件。
- 切换会话：未保存的草稿缓冲按会话保留，切回后仍在；进 Documents 有未保存确认，取消后缓冲完好。
- 窄屏与键盘：面板处于 260px 最小宽度时 4 个按钮换行且无横向溢出；审批按钮可聚焦，空格键激活审批成功。
- 该轮实测抓到并修掉一个真 bug：草稿快照的 `hidden` 判断写反，导致草稿已存入快照但面板不显示。

偏离与说明（不改变计划目标）：

1. `renderDraftPane(draft)` 落地为 `restoreDraftPane` / `renderDraftActions` / `openDraftPane` 三个函数，职责与原计划一致，命名不同。
2. 未保存确认复用现有两按钮对话框（「放弃修改」/「取消」），保存入口是面板上的「保存草稿」按钮；没有为「保存/放弃/取消」三选项新增第三种弹窗类型。
3. 维护窗口断言加在 `tests/integration/test_model_settings_api.py` 既有维护用例里（真实重建 gate 在那里），不在 `test_app.py`；该用例已在 `test_app.py` 覆盖 404/409/422/403 与持久化。
4. `draft` SSE 事件未用真实模型触发（避免为验证产生付费调用）；SSE 分支调用的 `openDraftPane` 与恢复路径已用浏览器验证，跨会话时只 skip 可见面板更新、依赖服务端已持久化。
5. 文档同步超出计划列出的两个文件：还改了 `architecture.md`、根 `README.md`、`docs/tutorials/zh/getting-started.md`、`web/templates/README.md`，因为它们同样声称草稿以「卡片」出现；另顺带修正 chat-tools.md 里过时的写盘异常范围（`OSError`/`ValueError`）。
6. `prompts/system.txt` 按计划做了最小修改（「卡片会单独显示」→「正文显示在右侧待审面板」），该文件哈希变化，生成评测与 v1.0.0 归档不再同 prompt 可比。

## 全局约束

- 只改草稿展示位置及使右侧草稿编辑可持久化所需的接口/状态；不得改变 Agent 提案权限、审批后写盘/索引顺序、动作语义、对话存储或引用笔记保存行为。
- 草稿编辑保存仅更新 `pending_draft`，绝不能调用 `PUT /notes/{path}`、不能写入 Markdown、不能索引 Chroma；只有现有审批操作允许提交文件变更。
- 拒绝仍清除草稿但不写文件；批准/覆写成功仍清除草稿并同步向量；审批失败保留草稿并允许修正或重试。
- 每个 conversation 仍只有一份待审草稿。聊天切换时引用和草稿编辑状态按 conversation 隔离，不得互相覆盖；无会话的新对话草稿随服务端返回的 conversation id 归属。
- 引用模式保持当前行为：读取正式笔记、定位引用片段、编辑正式笔记、保存到 Markdown 并同步向量。两种模式应有明确标识与独立保存动作。
- 不新增前端框架、状态管理库、测试依赖或数据库迁移；复用当前数据模型和前端布局。
- AI 只能在真正收到已保存的 `draft` 事件后给出“已生成待审批草稿”类描述。禁止声称正式笔记已写入；普通对话与仅引用回答的行为不变。
- 右侧面板可见的草稿操作需在窄屏可用、键盘可达，按钮应有明确中文名称和 disabled/busy 状态。

## 文件职责地图

| 路径 | 职责 |
|---|---|
| `src/noteagent/chat/history.py` | 更新 `pending_draft` 内容时保留同一会话草稿的其它字段；沿用现有持久化写入口 |
| `src/noteagent/chat/drafts.py` | 提供针对当前待审草稿的内容更新操作；不写正式笔记 |
| `src/noteagent/chat/agent.py` | 暴露 `update_draft_content(thread_id: str, content: str) -> dict`，把路由与 DraftStore 解耦 |
| `src/noteagent/chat/schemas.py` | 定义更新草稿请求的 Pydantic 输入 |
| `src/noteagent/chat/router.py` | 提供同源保护/写租约下的草稿更新路由；既有 `/chat/review` 契约不变 |
| `src/noteagent/web/templates/home.html` | 把草稿正文与原卡片操作渲染进 cite pane；管理模式切换、保存、审批、恢复及会话隔离 |
| `tests/unit/test_drafts.py` | 测试只更新待审正文且保留其余元数据，不写文件/不索引 |
| `tests/integration/test_app.py` | 测试草稿更新路由输入校验、持久化、无待审稿、同源/维护窗口行为及原审批接口兼容 |
| `docs/architecture/frontend.md` | 更新 SSE、引用面板模式和审批交互说明 |
| `docs/architecture/chat-tools.md` | 更新提案成功后的回复内容和前端呈现契约 |

## 设计选择

用同一个右侧面板承载引用和草稿，内部显式区分 `citation` 与 `draft` 模式。保留独立草稿卡片会继续把草稿内容留在聊天流里；把草稿转换成引用条目会错误地把尚未写盘的草稿当成正式笔记。模式化的现有面板能复用布局和编辑器，同时让草稿保存只写入待审状态，不混用正式笔记保存接口。

右侧草稿操作沿用当前卡片已有的全部操作：批准当前动作、拒绝、append/create 的目标覆写和文件名修改。草稿文本的“保存”是保存回当前会话 `pending_draft`，与引用模式“保存到 Markdown”是不同操作。批准/拒绝按钮只在草稿模式显示。

## Task 1：持久化编辑后的 pending draft

**文件：**修改 `history.py`、`drafts.py`、`schemas.py`、`router.py`；测试 `test_drafts.py`、`test_app.py`。

**接口：**新增 `PUT /chat/draft`，JSON `{ "thread_id": "...", "content": "..." }`。成功返回更新后的 `pending_draft`；conversation 不存在返回 404；无待审草稿返回 409；维护窗口仍按现有 `write_lease` 语义拒绝写入。路由沿用同源写保护。此接口只更新 content，action、file_name、reason、similar、existing_files 必须从原稿保留。

- [x] 先在 `tests/unit/test_drafts.py` 增加失败测试：创建一个含非默认 `reason`、`similar`、`existing_files` 的 `NoteDraft`，调用待实现的 `DraftStore.update_content(thread_id, content)`，经重新构造的 `DraftStore` 读取数据库并验证仅 `content` 改变。用临时 notes、fake retrieval 或直接验证仓库完全不触碰这些对象，确认没有 Markdown 写入和向量操作。
- [x] 增加无草稿时更新返回稳定失败结果的测试，并确认数据库字段仍为 null。
- [x] 运行 `uv run pytest tests/unit/test_drafts.py -q`，确认新增用例在实现前失败。
- [x] 在 `DraftStore` 添加 `update_content(thread_id: str, content: str) -> NoteDraft | None`：读取现有 `NoteDraft`；不存在返回 `None`；存在时用 `dataclasses.replace(draft, content=content)` 保留全部其它字段，再调用 `put` 保存并返回更新稿。拒绝空白正文（如 `not content.strip()`），避免保存后无法通过现有非 delete 写入校验。
- [x] 在 `history.py` 复用 `get_pending_draft` / `set_pending_draft`，不新增 ORM 字段或迁移。若需在 store 层写更新方法，签名接收 `conversation_id` 和完整 JSON payload，按现有事务/日志风格保存。
- [x] 在 `schemas.py` 新增草稿编辑请求模型，使用 `thread_id: str`、`content: str` 并约束正文非空；保留现有 `ReviewRequest` 字段和行为。
- [x] 在 `ChatAgent` 添加 `update_draft_content(thread_id: str, content: str) -> dict`，委托 `_drafts.update_content`，返回 `{"status": "updated", "pending_draft": draft.as_dict()}`；无草稿返回 `{"error": "no pending draft"}`。不读写正式笔记、不调用 retrieval。
- [x] 在 `router.py` 添加 `PUT /chat/draft`，使用 `RuntimeSnapshot = Depends(write_lease)`、同源校验依赖，调用 `snapshot.chat_agent.update_draft_content(...)`；把无草稿映射为 HTTP 409。不得接收或更改 action/file_name，亦不得调用 notes repository 或 retrieval。
- [x] 集成测试覆盖有效更新后 `GET /conversations/{id}` 返回完整且元数据不变的 pending draft；无草稿 409；未知会话 404；跨源拒绝；维护窗口期间拒绝更新；既有 approve/reject/override API 仍可用。
- [x] 运行 `uv run pytest tests/unit/test_drafts.py tests/integration/test_app.py -q`。

## Task 2：将草稿面板接入现有 cite pane

**文件：**修改 `src/noteagent/web/templates/home.html`。

**前端状态接口：**扩展当前 `citePaneByConv` 快照加入 `mode` 与待审草稿对象；当前面板的 `citeFileName` 表示正式笔记目标路径，新增独立 draft state，不将 draft file_name 当作已存在笔记。按模式显隐编辑器、草稿说明、动作和保存按钮。

- [x] 检查 `cite-pane` HTML、CSS、`snapshotCitePane`、`restoreCitePane`、`openCitedNote`、`saveCitedNote`、`closeCitePane`、`openConversation`、`newChat`、SSE `draft` 分支、`renderDraftCard`、`sendReview` 的调用关系与已有未保存确认行为。
- [x] 删除草稿独立卡片样式和 `renderDraftCard` 的 DOM 插入职责；新增 `renderDraftPane(draft)`，将其动作选择、目标文件选择、新建文件名及 approve/reject 处理提取为 cite pane 草稿模式的渲染/事件处理函数。不得更改 create/append/replace/delete 语义和 API 参数。
- [x] 扩充 `citePane` 标题区：显示当前文件名或草稿状态、动作、目标文件，并显示“待审批草稿”提示。复用同一个 Markdown textarea 展示 `draft.content`；草稿区域不得调用引用的 `noteUrl()` 读取草稿目标文件。
- [x] 草稿模式提供“保存草稿”“批准（按动作命名）”“拒绝”；append/create 按当前独立卡片保留“改为追加到所选文件”和“改为新建文件”控件。replace/delete 不显示原本不存在的 override 选项。delete 无正文时仍展示确认提示和批准/拒绝按钮。
- [x] 点击“保存草稿”调用 `PUT /chat/draft`，仅在服务端成功响应后将本地草稿更新为响应中的 canonical pending draft、清除 dirty 状态并显示已保存提示。失败时保留编辑文本和 dirty 状态，显示具体错误，可重试。
- [x] 若用户在未保存草稿编辑时直接批准、拒绝、切换引用、切换会话、关闭面板或进入 Documents，先使用现有确认交互提示保存/放弃/取消；确认放弃只丢弃前端编辑缓冲，不改变数据库草稿。若用户选择批准且草稿有未保存内容，先成功 `PUT /chat/draft`，然后才调用既有 `/chat/review`；保存失败不得审批旧版本。
- [x] `sendReview` 统一支持面板草稿模式：成功审批或拒绝后清除 `pending_draft` 模式快照并回到引用面板关闭态（若当前无引用内容）；失败保留草稿、文本、动作选择和文件名输入，恢复按钮可重试。保留当前审批结果聊天消息行为，若不再需要 card 参数，移除对应死参数。
- [x] SSE `draft` 事件到达后打开右侧草稿模式并填入服务端 payload；确保同步时仍在对应 conversation 中时才更新可见面板，切换会话期间到达的草稿进入其会话快照。
- [x] Assistant 气泡只显示模型生成的简短审批提示，不显示完整草稿正文。用户已有 prompt 约定“已提交审批”；只在确有必要时最小修改 `system.txt`，要求工具成功后可明确说“草稿已生成并待你审批”，不得说已正式写入/保存。引用答案不含 cite marker 时仍按既有规则显示，不因此强制打开草稿面板。
- [x] 恢复会话时读取 `GET /conversations/{id}` 的 pending_draft 并显示右侧草稿；如果同会话已有未保存的草稿编辑缓冲，保留该缓冲，不能被服务端旧快照无提示覆盖。批准/拒绝后切换会话不得再次恢复已完成草稿。
- [x] 引用模式行为逐项保持：点击 `cite-ref` 请求并定位正式笔记；textarea 保存走 `PUT /notes/{path}`；dirty 确认、会话 snapshot、Documents 切换均仍有效。引用面板打开后若新 draft 到达，按现有未保存确认约定再切换到草稿模式。
- [x] 使用现有浏览器开发工具做以下手工前端流程并记录：create/append/replace/delete，override append/create，草稿修改保存再刷新恢复，修改后直接批准，拒绝，批准错误后重试；并回归引用读取、定位、编辑保存、会话切换、Documents 切换、窄屏和键盘操作。若浏览器工具不可用，记录为未执行，不能虚报。

## Task 3：更新架构说明和最终核对

**文件：**修改 `docs/architecture/frontend.md`、`docs/architecture/chat-tools.md`，按需更新 `src/noteagent/chat/README.md`。

- [x] 更新前端数据流说明：`draft` SSE 与 `pending_draft` 恢复均打开 cite pane 的 draft mode；引用仍打开 citation mode；草稿保存仅改 conversation pending state；只有 approve/override 写 Markdown 与同步索引。
- [x] 更新审批 UI 描述：独立草稿卡片被右侧草稿面板取代；列出仍保留的审批/拒绝/override 能力与 delete 无正文行为。
- [x] 更新 Agent 提案成功后的回复说明：助手简短说明已生成待审批草稿，正文只在右侧面板，不复制到 assistant bubble；禁止声称已落盘。
- [x] 核对 API/响应文档包含 `PUT /chat/draft` 请求与错误语义，且没有误改 `POST /chat/review` 契约。
- [x] 审阅 diff，确认文案不再声称草稿卡片单独显示；检索 `renderDraftCard` 和 `.draft-card`，仅当不存在残留实现/样式时判通过。

## 完成检查

- [x] 单元与集成测试通过，包含草稿内容保存的数据库持久化、metadata 保留和原审批回归。
- [x] 浏览器流程证明草稿正文只出现在右侧面板、编辑保存能跨刷新恢复、正式文件只在审批后改变；引用编辑行为保持原样。
- [x] 每种草稿动作和 override 能力与改动前一致；拒绝不写盘/不索引，审批成功仍按原路径写盘和同步向量。
- [x] 所有遇到的测试/浏览器失败均记录实际原因；未执行的验证明确标注。更新 plans 索引中本计划条目。
