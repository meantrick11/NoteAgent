# rag_eval

离线检索（RAG）评测：读冻结语料与证据标注，跑真 `RetrievalService` 和真 `ChatAgent`，用确定性规则计分，写 `evals/{rag,agent}/results/<run-id>/`（完整版落 `var/evals/rag/<run-id>/`）。

**chat 不得 import 本包。** 不写用户 `NOTES_DIR`，不写 `CHROMA_DIR`，不连应用数据库，不 `POST /chat`。

## 包含模块

| 文件 | 作用 |
|------|------|
| `dataset.py` | 读 manifest / 语料 / 查询集 / Agent 场景并做运行时校验；解析带围栏感知的 heading_path |
| `metrics.py` | 纯计分：证据区间合并、unit 覆盖、Recall、Hit@3、MRR；无 I/O、不加载模型 |
| `run.py` | 直接检索层：建独立 Chroma、跑真检索、把片段映射回笔记偏移、写报告 |
| `agent_run.py` | Agent 层：每场景独立沙箱（notes 副本 / Chroma / sqlite）、记录工具与检索轨迹、确定性判定 |

入口：[scripts/eval_rag.py](../../../scripts/eval_rag.py)、[scripts/eval_rag_agent.py](../../../scripts/eval_rag_agent.py)、[scripts/build_rag_queries.py](../../../scripts/build_rag_queries.py)、[scripts/verify_rag_corpus.py](../../../scripts/verify_rag_corpus.py)。
准则与字段契约：[docs/evaluations/rag-quality.md](../../../docs/evaluations/rag-quality.md)。数据位置：[evals/rag/README.md](../../../evals/rag/README.md)、[evals/agent/README.md](../../../evals/agent/README.md)。

## 基础使用

```bash
python scripts/eval_rag.py --split dev --variant baseline --run-id rag-v1-baseline-dev
python scripts/eval_rag_agent.py --split dev --variant baseline --run-id agent-v1-baseline-dev --repeat 3
python scripts/verify_rag_corpus.py          # 复核审查结论与无答案标注，任一条不成立即非零码退出
```

## 边界与口径

- **偏移基准**是应用实际读到的文本（`FileNoteRepository.read` 走 `Path.read_text`，会把 CRLF 规范成 LF），不是原始字节；`quote` 必须等于该文本的对应切片。
- **失败要能被区分**：`ranked_below_top_k`（放深候选就能覆盖）与 `evidence_not_in_returned_fragments` 是不同问题；片段映射不回原文时记 `mapping_error`，不猜测、不静默跳过。
- **Agent 层只做确定性检查**（引用反查证据、写盘后比对原文、工具因果顺序、未找到/重复/冲突的关键词代理），语义结论保留证据交人工复核，不用同模型自评。
- **harness 不变量**：工具事件与落库 stub、检索调用与记录必须一致，不一致时记为该次运行的错误，避免把测量故障当成模型失败。
- 无答案查询不进正例 Recall 分母；检索层当前无相似度阈值，因此正确处理在 Agent 层评价。
- 单测不加载真实模型、不联网、不建 Chroma：`tests/unit/test_rag_eval.py`、`tests/unit/test_rag_agent_eval.py`。
