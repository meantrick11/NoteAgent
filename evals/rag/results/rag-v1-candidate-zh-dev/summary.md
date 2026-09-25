# Retrieval eval rag-v1-candidate-zh-dev

- variant: `candidate-zh` split: `dev` top_k: 5 probe_k: 20
- model: `BAAI/bge-small-zh-v1.5` revision `7999e1d3359715c523056ef9478215996d62a620`
- chunker: {'strategy': 'heading', 'chunk_size': 500, 'chunk_overlap': 50} distance: chroma-default-l2
- corpus manifest sha256: `67cb5e504bbae91e693ea3835a5f83ecac9a0c7f7a9eebf2886f4a2fc5b7f4ad`
- queries sha256: `295300838802bc90243fb9e6451ab68c3fb07499ebefaf7fb32896a814aee636`
- git: `94ff312871be5e519b14050e90c9be035ca6ecd7` dirty: yes
- index build: 3171 ms

## Metrics

| set | metric | passed/total | rate |
|---|---|---|---|
| answerable | full Evidence Recall@5 | 15/18 | 0.8333 |
| answerable | Evidence Hit@3 | 16/18 | 0.8889 |
| answerable | mean Evidence Recall@5 | - | 0.8611 |
| answerable | MRR@5 | - | 0.787 |
| answerable (diagnostic) | mean Evidence Recall@20 | - | 0.9444 |
| answerable (diagnostic) | full Recall@20 | 17/18 | 0.9444 |

## By category

| category | full recall@k | hit@3 | mean recall@k | mrr | mean recall@probe |
|---|---|---|---|---|---|
| fact | 7/7 | 7/7 | 1.0 | 1.0 | 1.0 |
| mixed_language | 3/3 | 3/3 | 1.0 | 0.8333 | 1.0 |
| multi_evidence | 3/4 | 4/4 | 0.875 | 0.8333 | 1.0 |
| paraphrase | 2/4 | 2/4 | 0.5 | 0.3333 | 0.75 |

## Latency (hot queries)

- samples: 72 (warmup 3x24)
- min: 7.39 ms, p50: 9.82 ms, p95: 11.3 ms
- index build: 3171 ms
- 同机其他进程会显著干扰本机延迟；跨 run 比较以 min 为准，并注明测量时段。

## Token budget（模型实际收到的输入）

- model max tokens: 512
- chunks: 176 (p50 148, max 480, mean 183.8)
- 超限（被模型静默截断）的块数: **0** []

## Failures

失败分类：`ranked_below_top_k` 放到更深候选就能覆盖；`partial_evidence` 只覆盖了部分 unit；`evidence_not_in_returned_fragments` 返回的片段里没有可完整覆盖的证据；`mapping_error` 片段无法映射回原文；`no_fragments` 检索为空。

| query | category | recall@k | recall@probe | hit@3 | failure | top hit (file, distance) |
|---|---|---|---|---|---|---|
| q05 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Agent_Design_Patterns.md, 0.9076 |
| q09 | paraphrase | 0.0 | 1.0 | False | ranked_below_top_k | Python_Tutorial_Overview.md, 0.9348 |
| q22 | multi_evidence | 0.5 | 1.0 | True | ranked_below_top_k | Writing_Effective_Tools_for_Agents.md, 0.7462 |

> 命中正文与逐条位置只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。

## Unanswerable queries

- ids: q31, q32, q33, q34, q35, q36
- top-1 distances: [0.4235, 0.5981, 0.6991, 0.7081, 0.8249, 1.0838]
- 检索层无阈值，故这些查询仍会返回片段；正确处理在 Agent 层评价。
