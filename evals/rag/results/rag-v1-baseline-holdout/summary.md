# Retrieval eval rag-v1-baseline-holdout

- variant: `baseline` split: `holdout` top_k: 5 probe_k: 20
- model: `sentence-transformers/all-MiniLM-L6-v2` revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
- chunker: {'strategy': 'char', 'chunk_size': 500, 'chunk_overlap': 50} distance: chroma-default-l2
- corpus manifest sha256: `67cb5e504bbae91e693ea3835a5f83ecac9a0c7f7a9eebf2886f4a2fc5b7f4ad`
- queries sha256: `295300838802bc90243fb9e6451ab68c3fb07499ebefaf7fb32896a814aee636`
- git: `1b0c60f52ff2518ca2e9f13cf28d747f324f3c6f` dirty: yes
- index build: 5925 ms

## Metrics

| set | metric | passed/total | rate |
|---|---|---|---|
| answerable | full Evidence Recall@5 | 6/12 | 0.5 |
| answerable | Evidence Hit@3 | 2/12 | 0.1667 |
| answerable | mean Evidence Recall@5 | - | 0.5 |
| answerable | MRR@5 | - | 0.2 |
| answerable (diagnostic) | mean Evidence Recall@20 | - | 0.7917 |
| answerable (diagnostic) | full Recall@20 | 9/12 | 0.75 |

## By category

| category | full recall@k | hit@3 | mean recall@k | mrr | mean recall@probe |
|---|---|---|---|---|---|
| fact | 1/1 | 0/1 | 1.0 | 0.25 | 1.0 |
| mixed_language | 2/3 | 1/3 | 0.6667 | 0.4 | 0.6667 |
| multi_evidence | 1/4 | 1/4 | 0.25 | 0.125 | 0.875 |
| paraphrase | 2/4 | 0/4 | 0.5 | 0.1125 | 0.75 |

## Latency (hot queries)

- samples: 48 (warmup 3x16)
- min: 89.23 ms, p50: 174.44 ms, p95: 233.51 ms
- index build: 5925 ms
- 同机其他进程会显著干扰本机延迟；跨 run 比较以 min 为准，并注明测量时段。

## Token budget（模型实际收到的输入）

- model max tokens: 256
- chunks: 107 (p50 247, max 449, mean 246.2)
- 超限（被模型静默截断）的块数: **50** ['Agent_Design_Patterns', 'Backtracking', 'BinaryTree', 'OWL2_Document_Overview', 'Python_Tutorial_Interpreter', 'Python_Tutorial_Intro', 'Python_Tutorial_Overview', 'SQLAlchemy_psycopg', 'Software_Architecture_Design', 'Writing_Effective_Tools_for_Agents']

## Failures

失败分类：`ranked_below_top_k` 放到更深候选就能覆盖；`partial_evidence` 只覆盖了部分 unit；`evidence_not_in_returned_fragments` 返回的片段里没有可完整覆盖的证据；`mapping_error` 片段无法映射回原文；`no_fragments` 检索为空。

| query | category | recall@k | recall@probe | hit@3 | failure | top hit (file, distance) |
|---|---|---|---|---|---|---|
| q07 | multi_evidence | 0.0 | 0.5 | False | ranked_below_top_k | Python_Tutorial_Interpreter.md, 0.9724 |
| q10 | mixed_language | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | OWL2_Document_Overview.md, 0.9812 |
| q14 | multi_evidence | 0.0 | 1.0 | False | ranked_below_top_k | Python_Tutorial_Intro.md, 0.9714 |
| q20 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Intro.md, 0.9333 |
| q25 | paraphrase | 0.0 | 1.0 | False | ranked_below_top_k | OWL2_Document_Overview.md, 0.6121 |
| q30 | multi_evidence | 0.0 | 1.0 | False | ranked_below_top_k | OWL2_Document_Overview.md, 0.4381 |

> 命中正文与逐条位置只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。

## Unanswerable queries

- ids: q37, q38, q39, q40
- top-1 distances: [0.4153, 0.8263, 0.954, 0.9726]
- 检索层无阈值，故这些查询仍会返回片段；正确处理在 Agent 层评价。
