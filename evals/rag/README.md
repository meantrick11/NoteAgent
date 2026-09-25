# rag evals

检索（RAG）评测的**数据与产物**。准则、指标定义与字段契约在 [docs/evaluations/rag-quality.md](../../docs/evaluations/rag-quality.md)。

## 数据位置

| 路径 | 内容 | 进仓库 |
|------|------|--------|
| `corpus/v1/notes/` | 10 篇冻结笔记副本（字节级等于用户原笔记） | **否**（隐私，`.gitignore`） |
| `corpus/v1/sources/` | 可获得的原始材料 | 否 |
| `corpus/v1/manifest.jsonl` | 每篇 `note_id`、相对路径、sha256、原路径、来源状态、审查状态、已知问题 | 是 |
| `corpus/v1/audit.md` | 逐篇：可回答的问题、缺失上下文、已发现缺陷 | 是 |
| `queries.v1.draft.json` | 人工标注草稿（含逐字引文，偏移由脚本推算） | 否 |
| `queries.v1.jsonl` | 40 条带证据标注的查询（含 `quote` 正文） | 否 |
| `results/<run-id>/summary.json`、`summary.md` | 指标、逐类结果、失败分类 | 是 |

完整报告（逐条命中正文、位置、距离）落在 `var/evals/rag/<run-id>/`，该目录被 `.gitignore` 排除。

**为什么正文不进仓库。** 正式 `notes/*` 已被忽略；语料是它的副本，`quote` 与命中记录都会逐字包含正文。仓库只保留哈希与不含正文的结论。

## 怎么跑

```bash
# 从草稿重建查询集（逐字定位引文、推算 heading_path 与偏移，并跑正式校验）
uv run python scripts/build_rag_queries.py \
  --corpus evals/rag/corpus/v1 \
  --draft evals/rag/queries.v1.draft.json \
  --output evals/rag/queries.v1.jsonl

# 直接检索评测：真 RetrievalService + 真 embedding + 独立 Chroma
uv run python scripts/eval_rag.py --corpus evals/rag/corpus/v1 \
  --queries evals/rag/queries.v1.jsonl --split dev \
  --variant baseline --run-id rag-v1-baseline-dev
```

参数：`--top-k`（主指标口径，默认 5）、`--probe-k`（诊断用的更深候选，默认 20）、`--repeats`、`--warmup`。每个 run 在 `var/evals/rag/<run-id>/` 新建独立 Chroma，不复用生产索引，也不写生产 `notes/`。

## 查询集字段

契约见 [docs/evaluations/rag-quality.md](../../docs/evaluations/rag-quality.md) §3。要点：

- `id`、`group_id`、`split`（dev/holdout）、`query`、`category`、`answerable`、`evidence_units`；
- 证据写 `note_id`、`heading_path`、`start_char`、`end_char`、`quote`，偏移基于**应用实际读到的文本**（`Path.read_text` 会把 CRLF 规范成 LF），`quote` 必须等于该切片；
- 相同信息需求的改写共用 `group_id`，整组只进一种 split；
- 40 条 = dev 24（18 有答案 + 6 无答案）+ holdout 16（12 + 4）。

## 不索引什么

只索引 `manifest.jsonl` 指定的 10 篇 notes。不索引本目录的 README、`sources/`、标注文件与 `results/`。
