# Screen Note Agent — 项目架构书

> **注意（2026-08-17）：本文是早期屏幕/OCR 方案，与当前 Web 聊天实现不一致。**  
> 现行架构与工作流见：[knowledge-workflow-v1.md](./knowledge-workflow-v1.md)

> 版本：v1.0 | 日期：2024-01-15 | 作者：待填写

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构总览](#2-系统架构总览)
3. [目录结构](#3-目录结构)
4. [模块详细设计](#4-模块详细设计)
   - 4.1 [感知层 Capture](#41-感知层-capture)
   - 4.2 [Agent 核心层](#42-agent-核心层)
   - 4.3 [RAG 扩展层](#43-rag-扩展层)
   - 4.4 [配置层](#44-配置层)
5. [数据流设计](#5-数据流设计)
6. [I/O 规范](#6-io-规范)
7. [笔记文档格式规范](#7-笔记文档格式规范)
8. [开发路线图](#8-开发路线图)
9. [技术栈清单](#9-技术栈清单)
10. [环境配置](#10-环境配置)

---

## 1. 项目概述

### 1.1 背景

用户在观看视频、参加会议、浏览网页时，往往需要手动记录笔记，效率低且容易遗漏关键信息。本项目旨在构建一个**自主运行的屏幕笔记 Agent**，自动捕获屏幕内容和音频，实时生成结构化 Markdown 笔记，后期支持向量数据库检索。

### 1.2 核心目标

| 目标 | 说明 |
|------|------|
| **自动采集** | 无需手动触发，后台持续监控屏幕和音频 |
| **智能理解** | 多模态 LLM 融合截图 + 音频转写 + OCR 信息 |
| **结构化输出** | 输出标准 Markdown 文件，可直接用于 Obsidian / Notion |
| **可扩展** | Phase 2 支持向量数据库切片检索，加 Tool 即可扩展 |

### 1.3 设计原则

- **两阶段分离**：Phase 1 专注生成高质量 Markdown；Phase 2 再做切片入向量库
- **人工 Review 节点**：LLM 输出先经人工确认，再进入向量库，保证 RAG 质量
- **Tool 驱动扩展**：Agent 核心不变，新增功能通过添加 LangChain Tool 实现
- **本地优先**：感知层（截图、OCR、Whisper）全部本地运行，无隐私泄露风险

---

## 2. 系统架构总览

```
┌─────────────────────────────────────────────────────────┐
│                     Phase 1：实时笔记生成                  │
│                                                         │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │ 屏幕截图  │   │ 音频转写  │   │ OCR提取  │            │
│  │  (mss)   │   │(Whisper) │   │(Paddle)  │            │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘            │
│       └──────────────┼──────────────┘                  │
│                      ▼                                  │
│          ┌───────────────────────┐                      │
│          │   LangChain Agent     │                      │
│          │  ┌─────────────────┐  │                      │
│          │  │ Context Buffer  │  │                      │
│          │  ├─────────────────┤  │                      │
│          │  │understand_screen│  │  Tool 1              │
│          │  ├─────────────────┤  │                      │
│          │  │detect_topic_    │  │  Tool 2              │
│          │  │change           │  │                      │
│          │  ├─────────────────┤  │                      │
│          │  │write_note_block │  │  Tool 3              │
│          │  └─────────────────┘  │                      │
│          └───────────┬───────────┘                      │
│                      ▼                                  │
│              ┌───────────────┐                          │
│              │  Markdown 笔记 │  ← 核心输出资产           │
│              │  + 截图原件    │                          │
│              └───────────────┘                          │
└─────────────────────────────────────────────────────────┘
                        │
                   人工 Review
                        │
┌─────────────────────────────────────────────────────────┐
│                   Phase 2：RAG 知识库（后期）              │
│                                                         │
│  Markdown → 智能切片 → Embedding → Qdrant → 检索问答      │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 目录结构

```
screen-note-agent/
│
├── agent/                        # Agent 核心层（最先开发）
│   ├── __init__.py
│   ├── core.py                   # AgentExecutor 组装，主入口
│   ├── tools.py                  # 3 个 LangChain @tool 函数
│   └── context.py                # 滑动上下文窗口管理
│
├── capture/                      # 感知层（独立于 Agent）
│   ├── __init__.py
│   ├── screen.py                 # 截图 + pHash 变化检测
│   ├── audio.py                  # Whisper 实时音频转写
│   └── ocr.py                    # PaddleOCR 文字提取
│
├── rag/                          # Phase 2 RAG 扩展（占位，后期填充）
│   ├── __init__.py
│   ├── chunker.py                # Markdown 按标题切片
│   ├── embedder.py               # BGE-M3 生成向量
│   └── retriever.py              # Qdrant 写入 + 混合检索
│
├── notes/                        # 输出目录（程序自动创建）
│   ├── 2024-01-15.md             # 按日期命名的笔记文件
│   ├── 2024-01-16.md
│   └── snapshots/                # 截图原件
│       ├── snap_103042.png       # 时间戳命名
│       └── snap_103512.png
│
├── config/
│   └── settings.py               # 全局配置（间隔、模型、路径等）
│
├── main.py                       # 主循环入口
├── requirements.txt
├── .env                          # API Key（不提交 Git）
├── .gitignore
└── README.md
```

---

## 4. 模块详细设计

### 4.1 感知层 Capture

感知层负责原始数据采集，**完全独立于 Agent**，以队列方式向 Agent 提供数据。

#### `capture/screen.py`

| 项目 | 说明 |
|------|------|
| **职责** | 定时截图，过滤无变化帧 |
| **核心依赖** | `mss`（跨平台截图）、`Pillow`（图像处理）、`imagehash`（pHash） |
| **触发方式** | 定时（默认30秒）+ 变化检测双重过滤 |
| **输出** | PNG 文件路径，写入 `notes/snapshots/` |

变化检测逻辑：
```
当前帧 pHash  vs  上一帧 pHash
Hamming 距离 < 阈值(默认10) → 跳过，不触发 Agent
Hamming 距离 ≥ 阈值 → 保存截图，触发 Agent
```

#### `capture/audio.py`

| 项目 | 说明 |
|------|------|
| **职责** | 后台线程持续录音，分段转写为文本 |
| **核心依赖** | `faster-whisper`（本地推理）、`sounddevice`（系统音频） |
| **运行方式** | 独立后台线程，每 N 秒将转写结果写入共享队列 |
| **输出** | 转写文本字符串，Agent 主循环从队列取用 |

#### `capture/ocr.py`

| 项目 | 说明 |
|------|------|
| **职责** | 对截图进行文字识别，补充 LLM 视觉理解 |
| **核心依赖** | `paddleocr`（中英文双语） |
| **输入** | 截图文件路径 |
| **输出** | 识别出的文字列表（附坐标） |

---

### 4.2 Agent 核心层

#### `agent/core.py`

负责将 Tools、Prompt、LLM 组装成可执行的 `AgentExecutor`。

```python
# 核心结构
llm = ChatAnthropic(model="claude-opus-4-6")
tools = [understand_screen, detect_topic_change, write_note_block]
agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
```

**系统 Prompt 设计原则：**
- 明确规定 Tool 调用顺序：理解 → 检测主题 → 写入
- 约定笔记文件命名规则（日期）
- 约定时间戳格式（`HH:MM:SS`）

#### `agent/tools.py`

包含 3 个核心 Tool，职责严格分离：

| Tool 名称 | 输入 | 输出 | 说明 |
|-----------|------|------|------|
| `understand_screen` | 截图路径、转写文本、上下文摘要 | 主题 + 要点列表 + 是否新章节 | 调用多模态 LLM |
| `detect_topic_change` | 当前理解、上下文摘要 | `new_chapter:标题` 或 `continue` | 判断是否开新章节 |
| `write_note_block` | 笔记文件名、章节标题、要点、时间戳、截图文件名 | 写入状态 | 追加写入 .md 文件 |

#### `agent/context.py`

管理滑动上下文窗口，防止 prompt 随时间无限增长。

```
策略：
- 保留最近 5 次 understand_screen 的输出
- 超出后压缩为摘要（再调用一次 LLM 做摘要）
- 摘要 + 最新 N 条 = 传入下一次调用的 context_summary
```

---

### 4.3 RAG 扩展层

> Phase 2 模块，Phase 1 完成并经人工 Review 后再启用。

#### `rag/chunker.py`

| 项目 | 说明 |
|------|------|
| **切片策略** | 按 `##` 二级标题切分，每个标题 = 一个 chunk |
| **chunk 结构** | `{text, chapter, timestamp, source_file, keywords, snapshot_path}` |
| **最小 chunk** | 50 字符（过短的跳过或合并） |
| **最大 chunk** | 800 字符（过长的按段落二次切分） |

#### `rag/embedder.py`

| 项目 | 说明 |
|------|------|
| **模型** | `BGE-M3`（中英双语，本地运行）|
| **备选** | `text-embedding-3-small`（OpenAI，效果稳定）|
| **批处理** | 每批 32 个 chunk，避免 OOM |
| **输出** | 向量列表 + 对应 payload |

#### `rag/retriever.py`

| 项目 | 说明 |
|------|------|
| **向量库** | Qdrant（本地模式，无需独立部署）|
| **检索策略** | 向量相似度 + BM25 关键词混合检索，再做 Re-rank |
| **过滤支持** | 按 `source_file`、`timestamp` 范围、`chapter` 过滤 |
| **RAG 问答** | 召回 Top-K chunks → 注入 LLM → 返回答案 + 来源引用 |

---

### 4.4 配置层

#### `config/settings.py`

```python
# 采集配置
CAPTURE_INTERVAL = 30        # 截图间隔（秒）
PHASH_THRESHOLD = 10         # pHash 变化阈值
AUDIO_SEGMENT_SEC = 30       # 音频分段长度（秒）

# 路径配置
NOTES_DIR = "notes/"
SNAPSHOTS_DIR = "notes/snapshots/"

# 模型配置
LLM_MODEL = "claude-opus-4-6"
WHISPER_MODEL = "base"       # tiny / base / small / medium
EMBEDDING_MODEL = "BAAI/bge-m3"

# Agent 配置
CONTEXT_WINDOW_SIZE = 5      # 滑动窗口保留最近 N 次
MAX_TOKENS = 1024

# RAG 配置（Phase 2）
CHUNK_MIN_LEN = 50
CHUNK_MAX_LEN = 800
TOP_K = 5
QDRANT_PATH = ".qdrant/"
```

---

## 5. 数据流设计

```
[主循环 main.py]
      │
      ├─ 每 30 秒
      │      │
      │      ├─ capture/screen.py  →  snap_HHMMSS.png
      │      ├─ capture/audio.py   →  transcript (str)
      │      └─ capture/ocr.py     →  ocr_text (str)
      │
      └─ 组装 input → AgentExecutor.invoke()
                │
                ├─ Tool: understand_screen
                │      输入：snap路径 + transcript + ocr + context_summary
                │      输出：主题 + 要点列表
                │
                ├─ Tool: detect_topic_change
                │      输入：当前理解 + context_summary
                │      输出：new_chapter:标题 | continue
                │
                └─ Tool: write_note_block
                       输入：文件名 + 章节 + 要点 + 时间戳 + 截图名
                       输出：追加写入 notes/YYYY-MM-DD.md
                                          │
                               [人工 Review & 编辑]
                                          │
                              rag/chunker.py → rag/embedder.py
                                          │
                                    Qdrant 向量库
                                          │
                               rag/retriever.py → RAG 问答
```

---

## 6. I/O 规范

### Agent 输入（每次调用）

```python
{
    "input": """
截图路径：notes/snapshots/snap_103042.png
音频转写：今天我们来讲解 Transformer 的注意力机制...
上下文摘要：上一段在介绍 Encoder 的整体结构，讲到了 Self-Attention 的基本概念。
当前时间：10:30:42
笔记文件：2024-01-15.md
截图文件名：snap_103042.png
"""
}
```

### Agent 输出（写入 .md 文件的笔记块）

```markdown
## [10:30:42] Transformer 注意力机制

- Q、K、V 三个矩阵分别代表 Query、Key、Value
- 注意力分数 = softmax(QKᵀ / √d_k) · V
- Multi-Head Attention 并行运行多组注意力，捕获不同维度特征

![截图](snapshots/snap_103042.png)
```

---

## 7. 笔记文档格式规范

每个 `.md` 文件对应一天的学习内容，结构如下：

```markdown
# 2024-01-15 学习笔记

> 来源：YouTube · 《深度学习基础》第 3 集
> 总时长：01:02:35 | 生成时间：2024-01-15 11:45:00

---

## [10:15:00] 第一章节标题

- 要点 1
- 要点 2
- 要点 3

![截图](snapshots/snap_101500.png)

---

## [10:30:42] 第二章节标题

- 要点 1
- 要点 2

![截图](snapshots/snap_103042.png)

---

## 全文摘要（Session 结束后生成）

本次学习涵盖以下核心内容：...
```

**规范要点：**

- 文件名：`YYYY-MM-DD.md`，每天一个文件
- 章节标题格式：`## [HH:MM:SS] 章节名称`（时间戳用于 RAG 切片后溯源）
- 截图引用：相对路径 `![截图](snapshots/xxx.png)`
- 每个章节末尾空一行，便于切片工具识别边界

---

## 8. 开发路线图

### Phase 1（核心功能）

```
Week 1
├── agent/tools.py     ← 3 个 Tool 实现（Mock 截图测试）
├── agent/core.py      ← AgentExecutor 组装
└── 验收：输入假数据，能正确生成 .md 文件

Week 2
├── capture/screen.py  ← 真实截图 + pHash 变化检测
├── main.py            ← 主循环接入真实截图
└── 验收：观看视频10分钟，自动生成可读笔记

Week 3
├── capture/audio.py   ← Whisper 后台线程
├── agent/context.py   ← 滑动上下文窗口
└── 验收：音频+截图融合，笔记质量对比提升

Week 4
├── capture/ocr.py     ← OCR 接入
├── 调优 Prompt        ← 笔记结构和要点质量
└── 验收：完整 Phase 1 可用
```

### Phase 2（RAG 扩展）

```
Week 5-6
├── rag/chunker.py     ← Markdown 切片
├── rag/embedder.py    ← 向量生成
├── rag/retriever.py   ← Qdrant 检索
└── 验收：能用自然语言检索历史笔记
```

---

## 9. 技术栈清单

| 层级 | 组件 | 版本 | 用途 |
|------|------|------|------|
| Agent | LangChain | ≥0.2 | Agent 编排框架 |
| Agent | langchain- | latest | Claude 接入 |
| LLM | 多模态模型 | — | 多模态理解 + 笔记生成 |
| 截图 | mss | ≥9.0 | 跨平台屏幕捕获 |
| 截图 | imagehash | ≥4.3 | pHash 变化检测 |
| 音频 | faster-whisper | ≥1.0 | 本地语音转写 |
| 音频 | sounddevice | ≥0.4 | 系统音频捕获 |
| OCR | paddleocr | ≥2.7 | 中英文文字识别 |
| 图像 | Pillow | ≥10.0 | 图像处理 |
| Embedding | FlagEmbedding | ≥1.2 | BGE-M3 向量化 |
| 向量库 | qdrant-client | ≥1.8 | 本地向量存储检索 |
| 环境 | python-dotenv | ≥1.0 | 环境变量管理 |

---

## 10. 环境配置

### 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### `requirements.txt`

```
langchain>=0.2.0
langchain-anthropic
langchain-community
anthropic

# 感知层
mss>=9.0
Pillow>=10.0
imagehash>=4.3
faster-whisper>=1.0
sounddevice>=0.4
paddleocr>=2.7
paddlepaddle

# RAG（Phase 2）
FlagEmbedding>=1.2
qdrant-client>=1.8

# 工具
python-dotenv>=1.0
```

### `.env` 文件

```bash
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
```

### 启动

```bash
# Phase 1：实时笔记生成
python main.py

# Phase 2：对已有笔记建索引（手动触发）
python -m rag.chunker --file notes/2024-01-15.md
python -m rag.embedder
```

---

*本文档随项目迭代持续更新。如有模块变更，请同步更新对应章节。*