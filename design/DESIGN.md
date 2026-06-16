# Phase 1 模块设计文档

> 写给实现阶段的自己看。这里记的是**为什么这样设计**、**各模块的职责边界**、**关键权衡**，不是任务清单。

---

## MVP 分步策略

MVP 不是一次写完所有模块。按依赖关系增量构建，每步跑通再往下走：

```
MVP-1：纯文本 → Agent → Markdown
    │  只写 agent/llm/ + agent/tools.py + agent/core.py
    │  人工给一段文本，Agent 生成笔记
    │  验证：Agent 的理解、章节判断、笔记结构是否正确
    │   finished at 2026-6-16
MVP-2：+ 音频感知
    │  加 capture/audio.py + main.py
    │  音频 → Whisper → 并入文本流 → Agent 实时写笔记
    │  验证：看视频 10 分钟，自动生成可读笔记
    │
MVP-3：+ 截图感知
    │  加 capture/screen.py
    │  截图 pHash 检测 → 存 snapshots/ → 笔记插图引用
    │  验证：笔记里有带时间戳的截图引用
    │
Phase 2：+ RAG
        rag/chunker.py → embedder.py → retriever.py
        历史笔记可检索
```

**MVP-1 只做 3 个文件**：`agent/llm/base.py` + `agent/llm/deepseek.py` + `agent/tools.py` + `agent/core.py` + `config/settings.py`。感知层、主循环都先不动。把 Agent 笔记生成的逻辑跑通、跑稳，再往上加。

---

## 整体分层

```
┌─────────────────────────────────┐
│           main.py               │  ← 主循环，串联两层
├───────────────┬─────────────────┤
│   capture/    │    agent/        │
│   (感知层)    │    (认知层)       │
│               │                 │
│   screen.py   │    engine.py      │
│   audio.py    │    tools.py     │
│               │    context.py   │
│               │    llm/         │
└───────┬───────┴────────┬────────┘
        │                │
   原始数据           Markdown 笔记
```

**感知层和 Agent 层完全解耦**，通过队列通信。

为什么这样分：
- 感知层的职责是"抓到什么"，不管"怎么理解"。截图、音频转写独立跑，互不依赖
- Agent 层的职责是"理解并写笔记"，不管数据怎么来的。以后加爬虫感知层，Agent 层零改动
- 两层各自可替换：感知换采集方式、Agent 换模型，互不影响

---

## 一、感知层 `capture/`

### 1.1 `capture/screen.py` — 屏幕截图 + 变化检测

**职责**：截取学习窗口，过滤无变化帧，只保留有意义画面

**为什么是事件驱动而不是定时轮询**：
视频学习场景下画面变化极不均匀。PPT 可能 5 分钟不动，也可能 10 秒翻一页。定时 30 秒要么漏 PPT 翻页，要么存一堆重复图片。pHash 汉明距离直接衡量"画面内容变了多少"——翻页、切场景时距离陡增，静止时距离为 0。

**pHash 为什么不是像素差**：
像素差对亮度缩放敏感。视频播放器最小化再恢复、窗外光线变化，像素差全爆炸。pHash 对缩放、亮度变化鲁棒，只对内容结构变化敏感。

**输出**：截图文件路径（写入 `notes/snapshots/`），入队列待 Agent 消费。变化不大的帧直接丢弃，不落盘。

**关键参数（可调）**：
- `PHASH_THRESHOLD`：汉明距离阈值，默认 10。越小越敏感（更多帧判为变化），越大越保守
- 不做最小间隔限制（翻页就是一瞬间的事，没必要等）

### 1.2 `capture/audio.py` — 系统音频捕获 + 转写

**职责**：后台线程持续录制系统音，分段送给 Whisper 转写，输出带时间戳的文本

**为什么 WASAPI loopback 而不是虚拟声卡**：
WASAPI 是 Windows 原生 API，`sounddevice` 直接走 loopback 模式抓系统音频输出，不经过麦克风再录音这条弯路。没有音质损失，也不需要装 VB-Cable。
代价：只能抓到系统发出的声音（视频的声音），抓不到你对着麦克风说话的声音。但这正好是我们需要的。

**为什么 faster-whisper 而不是 openai-whisper**：
faster-whisper 在 CPU 上推理速度快 4 倍（CTranslate2 推理引擎），内存占用更低。选 `base` 模型：中文英文都能用，准确度够，跑在笔记本上不卡。

**分段策略**：
按静音检测（VAD）分段，不是固定 N 秒一刀切。固定切段会在你说话一半时截断，一句话变成两截上下文断裂。VAD 按自然停顿切，每段是完整的句子。

**输出**：`(timestamp, text)` 元组入队列。timestamp 是这段语音的起始时间，用于 Agent 时间戳标记。

**为什么不在 GPU 上跑 whisper**：
Phase 1 先保证能跑通。绝大多数笔记本没有 NVIDIA 卡。base 模型 CPU 推理够用，后续可加 `--device cuda` 选项。

### 1.3 两层的时间对齐问题

截图的时刻和音频转写的时刻不是同一秒。Agent 消费时按**时间窗口聚合**：
- 取最近 N 秒（如 60s）内的截图 + 转写文本
- 打上同一个时间戳区间
- 传给 Agent 的 input 里同时包含两者

这样做 Agent 看到的信息是同步的，不会出现"截图是 10:30 的 PPT，转写是 10:32 的内容"这种错位。

---

## 二、Agent 层 `agent/`

### 2.1 `agent/llm/` — LLM 抽象层（关键设计）

**为什么需要抽象层**：
Phase 1 用 DeepSeek，Phase 2 可能换 GPT-4V 或国内多模态模型。如果 Agent 代码里到处是 `ChatDeepSeek(...)`，换个模型要改十几处。抽象成接口，换模型 = 改一行配置 + 写一个实现类。

**接口设计**：
```python
class BaseLLM(ABC):
    def invoke(self, prompt: str) -> str: ...
    def invoke_with_image(self, prompt: str, image_path: str) -> str: ...
```

两个方法分别对应纯文本推理和多模态推理。当前 DeepSeek 只实现 `invoke`，`invoke_with_image` 返回 NotImplementedError。后续多模态模型实现两者。

**为什么不是 LangChain 的 BaseChatModel**：
LangChain 的 BaseChatModel 也可以当抽象。但它的接口太重，包含 bind_tools、stream 等一堆我们可能不需要的东西。自己定一个轻量接口，只暴露我们需要的方法，后续换 LangChain 版本也不用跟着改接口。

**当前实现 `deepseek.py`**：
内部封装 `langchain_deepseek.ChatDeepSeek`，读取 `.env` 中的 `DEEPSEEK_API_KEY` 和 `DEEPSEEK_API_BASE`。对外暴露简单的 `invoke(prompt) -> str`。

### 2.2 `agent/tools.py` — 3 个 LangChain Tool

Agent 的认知过程拆成 3 个 Tool，模拟人做笔记时的思维：

| Tool | 输入 | 输出 | 什么时候调 |
|------|------|------|-----------|
| `understand_content` | 转写文本 + 上下文摘要 | 主题 + 要点列表 | 有新的转写文本到达 |
| `detect_topic_change` | 当前理解 + 上下文摘要 | `new_chapter:标题` 或 `continue` | understand 之后，决定笔记结构 |
| `write_note_block` | 文件名 + 章节 + 要点 + 时间戳 + 截图名 | 写入状态 | 判断有值得记录的内容 |

**为什么是 3 个而不是 1 个大 Tool**：
一个 Tool 全干了也能出笔记，但 LLM 容易把"理解"和"判断结构"混在一起——要么每个转写段都开新章节（笔记碎片化），要么永远不开新章节（整篇一块）。拆开后：
- `understand_content` 只管"这段在讲什么"
- `detect_topic_change` 只管"这是不是新话题"——它只看当前理解和历史摘要的关系
- `write_note_block` 只管"写"——格式化、文件操作

三个 Tool 调用顺序不硬编码，Agent 根据 prompt 指引自主决定。LangChain 的 `create_tool_calling_agent` 会编排。

**`detect_topic_change` 为什么重要**：
这是笔记结构的关键。比如你今天看"操作系统第二章上半截"，明天看"下半截"——Agent 面对的内容是连续的，但笔记应该追加到同一个 `## 第二章` 下面。这个 Tool 的职责就是判断：当前内容属于刚才那个话题，还是新话题？它输出 `continue` 或 `new_chapter:xxx`。

### 2.3 `agent/context.py` — 滑动上下文窗口

**为什么需要**：
30 分钟视频的转写文本可能有几千字。每次都把完整历史发给 LLM，token 费用爆炸且会超过上下文限制。

**策略**：
- 保留最近 N 次（默认 5）`understand_content` 的完整输出
- 超出 N 次的历史内容，压缩为一段摘要（调一次 LLM 做摘要）
- 每次调 Agent 时传入：`摘要 + 最近 N 条完整输出`

这是记忆系统的 MVP。Phase 2 会升级为向量检索——历史笔记切片 embedding 后存入 Qdrant，Agent 需要时检索相关片段。

**为什么不是固定 token 数截断**：
按 token 截断可能在句子中间切断。按"完整理解单元"（每次 understand_content 的输出是一个单元）保留，信息是完整的。

### 2.4 `agent/core.py` — AgentExecutor 组装

**职责**：把 LLM + Tools + Prompt + Context 拼成一个可执行体。它不干具体活，只管"组装"。

**系统 Prompt 设计要点**：
- 明确 3 个 Tool 的用途和调用时机
- 约定笔记格式：章节标题用 `## [HH:MM:SS] 标题`，截图用相对路径，时间戳用音频段起始时间
- 告诉 Agent：不是每个转写段都要写笔记。判断是否有实质内容再写。闲聊开场白跳过
- Prompt 从独立文件加载（`agent/prompts/system_prompt.txt`），方便调试调优

---

## 三、主循环 `main.py`

**职责**：感知层和 Agent 层之间的胶水代码

**循环逻辑（事件驱动，非固定间隔）**：
```
loop:
    检查音频队列 → 有新转写文本？
        是 → 取最近 60s 窗口内的截图 + 转写 → 组装 input → Agent.invoke()
        否 → sleep 0.5s，继续检查
    
    截图队列有新帧？
        是 → 先存着，等下次音频触发时一起喂给 Agent
    
    用户按了 i？
        是 → 暂停，展示当前笔记，等待审核指令
```

**为什么不是定时触发**：
PPT 翻页和说话都是事件。没内容变化时 Agent 无需运行。事件驱动更省 token，也更符合"人做笔记"的节奏——有值得记的东西才动笔。

**人工打断机制**：
主线程监听键盘，按 `i` 打断 → 暂停 Agent → 打印当前笔记 → 等待输入：
- 回车：继续
- `save`：保存当前笔记到文件
- `q`：退出并生成全文摘要

**启动参数**：
- `--topic "操作系统第二章"`：指定主题，Agent 检查 `notes/` 下是否有相关已有笔记
- `--date 2024-06-15`：覆盖默认日期文件名

---

## 四、关键权衡记录

| 权衡 | 选择 | 原因 |
|------|------|------|
| 截图理解 vs 先截后存 | Phase 1 只存不分析 | DeepSeek 无视觉能力，强行理解是自欺欺人。截图作为笔记插图有价值，理解留给多模态模型 |
| 固定定时 vs 事件驱动 | 事件驱动（音频触发为主） | 视频学习节奏由内容驱动，不应由时钟驱动 |
| 单 Agent vs 多 Agent | 单 Agent + 3 Tool | Phase 1 复杂度刚好。多 Agent 是 Phase 3 的事 |
| Tool 调用顺序固定 vs 自由 | Agent 自主决定 | LangChain tool_calling 已经能做，硬编码会失去灵活性 |
| 本地 OCR vs 不做 | Phase 1 不做 | 截图里的文字未来多模态模型直接能读，OCR 是过渡方案且增加复杂度 |
| 笔记按日期 vs 按话题 | 按日期 | 简单。话题间 Agent 通过 `detect_topic_change` 自动在文件内分章节 |

---

## 五、Phase 2 预留扩展点

- `agent/llm/` 下加新的模型实现类
- `capture/` 下可加 `crawler.py`（URL/爬虫感知）
- `agent/context.py` 升级为向量检索（当前滑动窗口能力有限）
- `rag/` 目录已预留，chunker → embedder → retriever 三件套
