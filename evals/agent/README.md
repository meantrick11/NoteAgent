# agent evals

真实 `ChatAgent` 的 RAG 场景评测：调用时机、结果使用、引用与写入安全。准则与指标见 [docs/evaluations/rag-quality.md](../../docs/evaluations/rag-quality.md)；直接检索层见 [../rag/README.md](../rag/README.md)。

## 数据位置

| 路径 | 内容 | 进仓库 |
|------|------|--------|
| `rag_cases.v1.json` | 20 条场景（含 `new_content`、`pre_dialogue`、期望 action 与必须保留的引用） | **否**（隐私，`.gitignore`） |
| `results/<run-id>/summary.json`、`summary.md` | 指标、逐场景结果、逐 case 三次成功分布 | 是 |

模型回答、检索片段与草稿正文只保存在本地 `var/evals/rag/<run-id>/`。

## 怎么跑

```bash
uv run python scripts/eval_rag_agent.py --corpus evals/rag/corpus/v1 \
  --cases evals/agent/rag_cases.v1.json --split dev \
  --variant baseline --run-id agent-v1-baseline-dev --repeat 3

# 小范围冒烟（少花 API 调用）
uv run python scripts/eval_rag_agent.py --split dev --variant baseline \
  --run-id agent-smoke --ids a11 --repeat 1
```

每个 case 独立：自己的 `notes/` 副本、自己的 Chroma 目录、自己的 sqlite 会话库。不连 PostgreSQL，不写用户 `notes/`，不写生产索引。

## 场景配比

| 场景 | dev | holdout | 合计 |
|------|-----|---------|------|
| `history_answer` | 4 | 2 | 6 |
| `history_append` | 4 | 2 | 6 |
| `history_unanswerable` | 2 | 2 | 4 |
| `plain_chat` | 2 | 2 | 4 |

补充场景含 2 条重复信息、2 条需要澄清的冲突。每条真实运行 3 次，报逐次结果与波动。

## 字段

`id`、`group_id`、`split`、`scenario`、`user`、`pre_dialogue`、`expect_search`、`expect_action`、`target_file`、`new_content`、`evidence_refs`、`must_preserve_refs`、`must_not_contain_refs`、`expect_flags_conflict`、`conflict_markers`、`expect_no_write`、`notes`。

`*_refs` 引用 [../rag/queries.v1.jsonl](../rag/README.md) 的 query id，并与本 case 同 split——跨 split 的引用会被 `load_agent_cases` 拒绝。

## 判定口径

自动评分只做确定性检查，语义结论保留证据并标注自动审查：

- `search_called`：是否按期望调用检索；
- `reads_before_propose`：改目标文件前是否 `read_file` 过它；
- `action_ok` / `target_ok`：草稿的 action 与目标文件是否符合期望；
- `evidence_cited`：回答里的引用能否反查回必需证据单元；
- `retrieval_sufficient`：检索片段本身是否覆盖必需证据（与上一条分开报）；
- `must_preserve` / `must_not_contain`：把草稿应用到沙箱副本后，目标文件是否保留了原有事实、是否重复写入已有内容；
- `states_no_evidence`：历史无答案场景是否明确说明未找到。判定是**代理指标**：用「否定词 + 存在性动词」与「笔记/记录 + 否定」的窗口规则（`states_no_evidence()`），不是固定短语表——固定短语曾把「没有。…没有命中任何相关内容」这种正确回答判成失败。措辞无法穷举，所以完整回答会写进本地报告供人工复核，不能把自动通过当作独立验收。
- `flags_conflict`：用户说法与笔记冲突时是否指出冲突（关键词取自 case 自己的 `conflict_markers`）。

修口径不用重跑模型：`--rescore` 会复用已存的模型输出、只重算判定，并打印前后指标对比；重算是幂等的，前后一致即说明落盘结论与当前规则自洽。
