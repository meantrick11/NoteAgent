# NoteAgent

## 简介

NoteAgent 是一个基于 LLM 的个人学习笔记助手。通过 FastAPI 提供 Web UI 界面，用户以对话形式输入学习内容，后端 Agent（基于 LangGraph 编排）会根据系统提示词自动调用文件工具（创建、读取、写入），将对话内容整理为结构化的 Markdown 笔记，保存到本地 `notes/` 目录。同时集成了 RAG 检索工具，Agent 可检索历史笔记中的知识点，针对性地进行解答。

## 技术栈

| 层级 | 技术 |
|------|------|
| LLM 后端 | DeepSeek V4 Flash（通过 LangChain 调用） |
| Agent 框架 | LangGraph + LangChain（工具编排、多轮记忆） |
| Web 框架 | FastAPI + SSE 异步流式输出 |
| 前端 | 原生 HTML/CSS/JS，marked.js 渲染 Markdown |
| Embedding 模型 | all-MiniLM-L6-v2（SentenceTransformer 加载） |
| 向量数据库 | ChromaDB（本地持久化） |
| 文本分割 | LangChain RecursiveCharacterTextSplitter（500 字符块，50 字符重叠） |
| 运行时 | Python >= 3.13，uv 包管理 |

## 环境准备

1. 安装依赖：

   ```bash
   uv sync
   ```

2. 在项目根目录创建 `.env` 文件，配置 DeepSeek API：

   ```
   DEEPSEEK_API_KEY=your_api_key_here
   DEEPSEEK_API_BASE=https://api.deepseek.com
   ```

3. 预下载 Embedding 模型（当前 `rag/simple_rag.py` 中设置为本地加载，需要提前下载 `all-MiniLM-L6-v2` 到指定缓存目录，或修改 `init_embed_model` 中的 `local_files_only=False` 首次自动下载）。

4. 在项目根目录创建 `notes/context.md` 作为初始上下文文件（Agent 启动时会读取该文件了解用户学习状况）。

## 启动

```bash
python main.py
```

访问 `http://127.0.0.1:8000` 即可使用。

## 项目结构

```
NoteAgent/
├── main.py                  # 入口：初始化 RAG、Agent、FastAPI 并启动
├── config.py                # 环境变量加载与 LLM 模型创建
├── agent/
│   ├── engine.py            # AgentPipeline：系统提示词加载、Agent 初始化、流式对话
│   ├── tools.py             # Agent 工具：create_file / read_from_file / write_to_file / list_files / chromadb 检索
│   └── prompts/
│       └── system_prompts.txt  # Agent 系统提示词（定义笔记格式、工作流程）
├── rag/
│   └── simple_rag.py        # RAGPipeline：文本分割 → embedding → ChromaDB 入库 & 检索
├── router/
│   ├── __init__.py          # 路由注册
│   ├── chat.py              # GET /（首页）、POST /chat（SSE 流式对话）
│   └── json_schema.py       # 请求/响应 Pydantic 模型
├── templates/
│   └── home.html            # Web 前端页面
├── notes/                   # 笔记文件存储目录
├── chromadb_persist/        # ChromaDB 向量持久化目录
└── static/                  # 静态资源
```

## 注意事项

- Agent 的对话记忆通过 LangGraph `InMemorySaver` 实现，`thread_id` 用于区分不同会话，服务重启后记忆会丢失。
- RAG 向量入库目前需要手动调用 `RAGPipeline.path_to_save()`，尚未集成到 Agent 的自动工具链中。
- 笔记文件名按日期自动生成（`YYYY-MM-DD.md`），同一天的内容会追加到同一文件。

## 愿景

1. 通过聊天，Agent 自动记录所学内容，以便后续成为个人知识助理：复习所学、知识抽答等功能。

2. 增加自动化的屏幕输入 UI Agent，自动获取屏幕中的数据、音频、字幕、PPT 中的流程图等图片，自动生成图文并茂的笔记，用户不必手动记笔记，后台 Agent 自动获取并生成。


