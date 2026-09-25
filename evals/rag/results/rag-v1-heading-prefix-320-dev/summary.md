# Retrieval eval rag-v1-heading-prefix-320-dev

- variant: `heading-prefix-320` split: `dev` top_k: 5 probe_k: 20
- model: `all-MiniLM-L6-v2` revision `None`
- chunker: {'strategy': 'heading', 'chunk_size': 320, 'chunk_overlap': 32} distance: chroma-default-l2
- corpus manifest sha256: `67cb5e504bbae91e693ea3835a5f83ecac9a0c7f7a9eebf2886f4a2fc5b7f4ad`
- queries sha256: `295300838802bc90243fb9e6451ab68c3fb07499ebefaf7fb32896a814aee636`
- git: `5a0745292fe31e56da6d49bc6d21f5c8cdbf5e6b` dirty: yes
- index build: 3003 ms

## Metrics

| set | metric | passed/total | rate |
|---|---|---|---|
| answerable | full Evidence Recall@5 | 8/18 | 0.4444 |
| answerable | Evidence Hit@3 | 7/18 | 0.3889 |
| answerable | mean Evidence Recall@5 | - | 0.4444 |
| answerable | MRR@5 | - | 0.3074 |
| answerable (diagnostic) | mean Evidence Recall@20 | - | 0.6667 |
| answerable (diagnostic) | full Recall@20 | 12/18 | 0.6667 |

## By category

| category | full recall@k | hit@3 | mean recall@k | mrr | mean recall@probe |
|---|---|---|---|---|---|
| fact | 4/7 | 3/7 | 0.5714 | 0.4571 | 0.7143 |
| mixed_language | 0/3 | 0/3 | 0.0 | 0.0 | 0.6667 |
| multi_evidence | 3/4 | 3/4 | 0.75 | 0.4583 | 0.75 |
| paraphrase | 1/4 | 1/4 | 0.25 | 0.125 | 0.5 |

## Latency (hot queries)

- samples: 72 (warmup 3x24)
- min: 6.25 ms, p50: 10.15 ms, p95: 11.02 ms
- index build: 3003 ms
- 同机其他进程会显著干扰本机延迟；跨 run 比较以 min 为准，并注明测量时段。

## Token budget（模型实际收到的输入）

- model max tokens: 256
- chunks: 223 (p50 128, max 295, mean 140.4)
- 超限（被模型静默截断）的块数: **7** ['Python_Tutorial_Interpreter', 'Python_Tutorial_Overview', 'Writing_Effective_Tools_for_Agents']

## Failures

失败分类：`ranked_below_top_k` 放到更深候选就能覆盖；`partial_evidence` 只覆盖了部分 unit；`evidence_not_in_returned_fragments` 返回的片段里没有可完整覆盖的证据；`mapping_error` 片段无法映射回原文；`no_fragments` 检索为空。

| query | category | recall@k | recall@probe | hit@3 | failure | top hit (file, distance) |
|---|---|---|---|---|---|---|
| q01 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Overview.md, 0.5479 |
| q05 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Backtracking.md, 0.9284 |
| q08 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Overview.md, 0.5456 |
| q09 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Backtracking.md, 0.9106 |
| q12 | paraphrase | 0.0 | 1.0 | False | ranked_below_top_k | BinaryTree.md, 1.1166 |
| q21 | mixed_language | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Overview.md, 1.0522 |
| q22 | multi_evidence | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Backtracking.md, 0.8772 |
| q24 | fact | 0.0 | 1.0 | False | ranked_below_top_k | Backtracking.md, 0.8543 |
| q26 | mixed_language | 0.0 | 1.0 | False | ranked_below_top_k | SQLAlchemy_psycopg.md, 0.8218 |
| q29 | mixed_language | 0.0 | 1.0 | False | ranked_below_top_k | OWL2_Document_Overview.md, 0.6038 |

> 命中正文与逐条位置只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。

## Unanswerable queries

- ids: q31, q32, q33, q34, q35, q36
- top-1 distances: [0.465, 0.6208, 0.6911, 0.7252, 0.8942, 1.2034]
- 检索层无阈值，故这些查询仍会返回片段；正确处理在 Agent 层评价。
