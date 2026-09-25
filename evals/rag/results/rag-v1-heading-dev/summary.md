# Retrieval eval rag-v1-heading-dev

- variant: `heading` split: `dev` top_k: 5 probe_k: 20
- model: `all-MiniLM-L6-v2` revision `None`
- chunker: {'strategy': 'heading', 'chunk_size': 500, 'chunk_overlap': 50} distance: chroma-default-l2
- corpus manifest sha256: `67cb5e504bbae91e693ea3835a5f83ecac9a0c7f7a9eebf2886f4a2fc5b7f4ad`
- queries sha256: `295300838802bc90243fb9e6451ab68c3fb07499ebefaf7fb32896a814aee636`
- git: `5a0745292fe31e56da6d49bc6d21f5c8cdbf5e6b` dirty: yes
- index build: 7052 ms

## Metrics

| set | metric | passed/total | rate |
|---|---|---|---|
| answerable | full Evidence Recall@5 | 5/18 | 0.2778 |
| answerable | Evidence Hit@3 | 5/18 | 0.2778 |
| answerable | mean Evidence Recall@5 | - | 0.2778 |
| answerable | MRR@5 | - | 0.25 |
| answerable (diagnostic) | mean Evidence Recall@20 | - | 0.5556 |
| answerable (diagnostic) | full Recall@20 | 10/18 | 0.5556 |

## By category

| category | full recall@k | hit@3 | mean recall@k | mrr | mean recall@probe |
|---|---|---|---|---|---|
| fact | 3/7 | 3/7 | 0.4286 | 0.3571 | 0.5714 |
| mixed_language | 0/3 | 0/3 | 0.0 | 0.0 | 0.6667 |
| multi_evidence | 1/4 | 1/4 | 0.25 | 0.25 | 0.5 |
| paraphrase | 1/4 | 1/4 | 0.25 | 0.25 | 0.5 |

## Latency (hot queries)

- samples: 72 (warmup 3x24)
- min: 87.81 ms, p50: 173.06 ms, p95: 244.91 ms
- index build: 7052 ms
- 同机其他进程会显著干扰本机延迟；跨 run 比较以 min 为准，并注明测量时段。

## Token budget（模型实际收到的输入）

- model max tokens: 256
- chunks: 176 (p50 127, max 449, mean 147.1)
- 超限（被模型静默截断）的块数: **25** ['Python_Tutorial_Interpreter', 'Python_Tutorial_Overview', 'Writing_Effective_Tools_for_Agents']

## Failures

失败分类：`ranked_below_top_k` 放到更深候选就能覆盖；`partial_evidence` 只覆盖了部分 unit；`evidence_not_in_returned_fragments` 返回的片段里没有可完整覆盖的证据；`mapping_error` 片段无法映射回原文；`no_fragments` 检索为空。

| query | category | recall@k | recall@probe | hit@3 | failure | top hit (file, distance) |
|---|---|---|---|---|---|---|
| q01 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Intro.md, 0.4766 |
| q04 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Interpreter.md, 0.8952 |
| q05 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Backtracking.md, 0.7393 |
| q08 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Intro.md, 0.4214 |
| q09 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Software_Architecture_Design.md, 0.8345 |
| q12 | paraphrase | 0.0 | 1.0 | False | ranked_below_top_k | Software_Architecture_Design.md, 0.954 |
| q13 | multi_evidence | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Backtracking.md, 0.5343 |
| q16 | multi_evidence | 0.0 | 1.0 | False | ranked_below_top_k | Software_Architecture_Design.md, 0.6877 |
| q21 | mixed_language | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Backtracking.md, 0.8669 |
| q22 | multi_evidence | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Software_Architecture_Design.md, 0.8015 |
| q24 | fact | 0.0 | 1.0 | False | ranked_below_top_k | Software_Architecture_Design.md, 0.4964 |
| q26 | mixed_language | 0.0 | 1.0 | False | ranked_below_top_k | SQLAlchemy_psycopg.md, 0.5831 |
| q29 | mixed_language | 0.0 | 1.0 | False | ranked_below_top_k | OWL2_Document_Overview.md, 0.6748 |

> 命中正文与逐条位置只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。

## Unanswerable queries

- ids: q31, q32, q33, q34, q35, q36
- top-1 distances: [0.4427, 0.6016, 0.6631, 0.7666, 0.8338, 1.1015]
- 检索层无阈值，故这些查询仍会返回片段；正确处理在 Agent 层评价。
