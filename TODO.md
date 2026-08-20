# TODO

> 2026.8 → 2027.3，目标：Agent 为核心 + 全栈拉通 + 可上简历

---

## 全局时间线

| 阶段 | 时间 | 节奏 |
|---|---|---|
| 实习期间 | 8.8 → 10.1 | 低强度 |
| 后端+全栈 | 10.1 → 12 月底 | 中高强度 |
| Agent 深水区 | 1 月 → 3 月 | 高强度 |

---

## 1. 后端线

### PostgreSQL + ORM
- [ ] SQLAlchemy 2.0 建 Model（`users` / `threads` / `chat_messages`）
- [ ] `ForeignKey` + `relationship` 一对多关系
- [ ] 索引设计（`thread_id`, `user_id`, `created_at`）
- [ ] Alembic 数据库迁移

### JWT 鉴权
- [ ] `python-jose` 生成/验证 token
- [ ] `passlib` bcrypt 密码哈希
- [ ] `Depends(get_current_user)` 依赖注入
- [ ] 前后端联调：axios interceptor 带 token，401 跳登录

### 中间件
- [ ] CORS
- [ ] 请求日志（method + path + 耗时 + user_id + thread_id）
- [ ] Request ID 全链路追踪

### 缓存
- [ ] 理解缓存概念与命中率
- [ ] LLM 语义缓存（dict 实现，不含 Redis）
- [ ] Embedding 缓存（文件 hash → 向量缓存）

### 后台任务
- [ ] FastAPI BackgroundTasks：退出总结不阻塞响应
- [ ] 笔记变更自动触发 RAG 索引

### 配置管理
- [ ] pydantic-settings 替代裸读 `.env`
- [ ] Agent 行为参数配置化（temperature、工具列表、prompt 选择）

---

## 2. Agent 线

### 源码理解
- [ ] LangGraph Agent 循环走读（ReAct：思考→行动→观察→思考）
- [ ] Checkpoint 机制深读（`InMemorySaver` 内部存了什么）
- [ ] Tool 调用链路：LLM structured output → ToolMessage → 关联 `tool_call_id`
- [ ] 消息类型理解：SystemMessage / HumanMessage / AIMessage / ToolMessage 各自的权重

### 多用户 Agent
- [ ] PostgresSaver 持久化（替代 InMemorySaver）
- [ ] `thread_id` 绑 `user_id`，会话隔离 + 权限校验
- [ ] 按用户隔离 `notes/` 目录
- [ ] 按用户隔离 ChromaDB collection

### 可观测性
- [ ] Agent 决策日志写入 `chat_messages.metadata`（JSONB）
- [ ] 单次会话统计：工具调用次数、LLM token 用量、总耗时
- [ ] Request ID 贯穿 Agent→Tool→LLM 全链路

### RAG 质量
- [ ] 换中文 embedding（`BGE-small-zh`）
- [ ] 检索加相似度阈值过滤（distance > 0.6 丢弃）
- [ ] RAG 小评估：10 条 query + 人工标注，算准确率/召回率

### Agent 流式协议
- [ ] 不只 yield 文本，也 yield 工具调用状态（tool_call 事件）
- [ ] 前端展示：聊天气泡 + 工具调用状态栏
- [ ] SSE 流异常处理 + 前端错误展示

### Prompt 工程
- [ ] Prompt 文件纳入 git 版本管理
- [ ] 工具描述对比测试：改描述前后 Agent 调用行为差异
- [ ] 支持多场景 prompt（默认 / 专家模式）

### 评估
- [ ] 10 个典型对话场景的 Eval
- [ ] 自动检查工具调用序列是否符合预期

---

## 3. 前端线

- [ ] Vue3 `<script setup>` + Composition API
- [ ] Vue Router（`/login` / `/chat` / `/notes`）
- [ ] Pinia（auth store + chat store）
- [ ] axios 封装 + interceptor
- [ ] SSE 流式接收 + 逐 token 渲染 Markdown
- [ ] 会话列表 + 历史消息加载
- [ ] 笔记浏览 + 搜索页面

---

## 4. 工程化

- [ ] Docker + docker-compose（后端 + 前端 + PostgreSQL）
- [ ] pytest 关键链路（Agent 工具测试 + 缓存测试）
- [ ] GitHub Actions（push → 测试）

---

## 5. 不做的

| 砍掉 | 理由 |
|---|---|
| Redis | dict 够用，面试能讲清缓存策略即可 |
| Celery/消息队列 | BackgroundTasks 足够 |
| 速率限制 | 单用户项目 |
| refresh token | access token 24h 过期够用 |
| 微服务 | 单体架构正合适 |
| WebSocket | SSE 天然匹配 Agent 流式输出 |
| 全文搜索 (tsvector) | RAG 向量搜索是亮点，不分散注意力 |
