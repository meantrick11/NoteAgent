# Retrieval eval rag-v1-selected-holdout

- variant: `selected` split: `holdout` top_k: 5 probe_k: 20
- model: `intfloat/multilingual-e5-small` revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`
- chunker: {'strategy': 'heading', 'chunk_size': 500, 'chunk_overlap': 50} distance: chroma-default-l2
- corpus manifest sha256: `67cb5e504bbae91e693ea3835a5f83ecac9a0c7f7a9eebf2886f4a2fc5b7f4ad`
- queries sha256: `295300838802bc90243fb9e6451ab68c3fb07499ebefaf7fb32896a814aee636`
- git: `1b0c60f52ff2518ca2e9f13cf28d747f324f3c6f` dirty: yes
- index build: 4845 ms

## Metrics

| set | metric | passed/total | rate |
|---|---|---|---|
| answerable | full Evidence Recall@5 | 11/12 | 0.9167 |
| answerable | Evidence Hit@3 | 11/12 | 0.9167 |
| answerable | mean Evidence Recall@5 | - | 0.9167 |
| answerable | MRR@5 | - | 0.9167 |
| answerable (diagnostic) | mean Evidence Recall@20 | - | 1.0 |
| answerable (diagnostic) | full Recall@20 | 12/12 | 1.0 |

## By category

| category | full recall@k | hit@3 | mean recall@k | mrr | mean recall@probe |
|---|---|---|---|---|---|
| fact | 0/1 | 0/1 | 0.0 | 0.0 | 1.0 |
| mixed_language | 3/3 | 3/3 | 1.0 | 1.0 | 1.0 |
| multi_evidence | 4/4 | 4/4 | 1.0 | 1.0 | 1.0 |
| paraphrase | 4/4 | 4/4 | 1.0 | 1.0 | 1.0 |

## Latency (hot queries)

- samples: 48 (warmup 3x16)
- min: 10.37 ms, p50: 14.67 ms, p95: 16.51 ms
- index build: 4845 ms
- 同机其他进程会显著干扰本机延迟；跨 run 比较以 min 为准，并注明测量时段。

## Token budget（模型实际收到的输入）

- model max tokens: 512
- chunks: 176 (p50 127, max 371, mean 151.6)
- 超限（被模型静默截断）的块数: **0** []

## Failures

失败分类：`ranked_below_top_k` 放到更深候选就能覆盖；`partial_evidence` 只覆盖了部分 unit；`evidence_not_in_returned_fragments` 返回的片段里没有可完整覆盖的证据；`mapping_error` 片段无法映射回原文；`no_fragments` 检索为空。

| query | category | recall@k | recall@probe | hit@3 | failure | top hit (file, distance) |
|---|---|---|---|---|---|---|
| q28 | fact | 0.0 | 1.0 | False | ranked_below_top_k | OWL2_Document_Overview.md, 0.1636 |

> 命中正文与逐条位置只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。

## Unanswerable queries

- ids: q37, q38, q39, q40
- top-1 distances: [0.2185, 0.2209, 0.2673, 0.2852]
- 检索层无阈值，故这些查询仍会返回片段；正确处理在 Agent 层评价。
