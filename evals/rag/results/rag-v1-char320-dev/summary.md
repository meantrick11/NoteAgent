# Retrieval eval rag-v1-char320-dev

- variant: `char320` split: `dev` top_k: 5 probe_k: 20
- model: `all-MiniLM-L6-v2` revision `None`
- chunker: {'strategy': 'char', 'chunk_size': 320, 'chunk_overlap': 32} distance: chroma-default-l2
- corpus manifest sha256: `67cb5e504bbae91e693ea3835a5f83ecac9a0c7f7a9eebf2886f4a2fc5b7f4ad`
- queries sha256: `295300838802bc90243fb9e6451ab68c3fb07499ebefaf7fb32896a814aee636`
- git: `5a0745292fe31e56da6d49bc6d21f5c8cdbf5e6b` dirty: yes
- index build: 6861 ms

## Metrics

| set | metric | passed/total | rate |
|---|---|---|---|
| answerable | full Evidence Recall@5 | 7/18 | 0.3889 |
| answerable | Evidence Hit@3 | 2/18 | 0.1111 |
| answerable | mean Evidence Recall@5 | - | 0.3889 |
| answerable | MRR@5 | - | 0.1472 |
| answerable (diagnostic) | mean Evidence Recall@20 | - | 0.5278 |
| answerable (diagnostic) | full Recall@20 | 9/18 | 0.5 |

## By category

| category | full recall@k | hit@3 | mean recall@k | mrr | mean recall@probe |
|---|---|---|---|---|---|
| fact | 3/7 | 1/7 | 0.4286 | 0.2143 | 0.5714 |
| mixed_language | 1/3 | 0/3 | 0.3333 | 0.0667 | 0.6667 |
| multi_evidence | 2/4 | 1/4 | 0.5 | 0.175 | 0.625 |
| paraphrase | 1/4 | 0/4 | 0.25 | 0.0625 | 0.25 |

## Latency (hot queries)

- samples: 72 (warmup 3x24)
- min: 8.21 ms, p50: 11.27 ms, p95: 196.19 ms
- index build: 6861 ms
- 同机其他进程会显著干扰本机延迟；跨 run 比较以 min 为准，并注明测量时段。

## Token budget（模型实际收到的输入）

- model max tokens: 256
- chunks: 180 (p50 148, max 297, mean 147.0)
- 超限（被模型静默截断）的块数: **5** ['BinaryTree', 'Python_Tutorial_Interpreter', 'Python_Tutorial_Overview', 'Software_Architecture_Design']

## Failures

失败分类：`ranked_below_top_k` 放到更深候选就能覆盖；`partial_evidence` 只覆盖了部分 unit；`evidence_not_in_returned_fragments` 返回的片段里没有可完整覆盖的证据；`mapping_error` 片段无法映射回原文；`no_fragments` 检索为空。

| query | category | recall@k | recall@probe | hit@3 | failure | top hit (file, distance) |
|---|---|---|---|---|---|---|
| q01 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Overview.md, 0.5962 |
| q04 | fact | 0.0 | 1.0 | False | ranked_below_top_k | Python_Tutorial_Interpreter.md, 0.9475 |
| q05 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Overview.md, 0.9561 |
| q08 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Overview.md, 0.6201 |
| q09 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Writing_Effective_Tools_for_Agents.md, 0.9222 |
| q12 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Interpreter.md, 0.8277 |
| q16 | multi_evidence | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Overview.md, 0.8272 |
| q21 | mixed_language | 0.0 | 1.0 | False | ranked_below_top_k | Python_Tutorial_Overview.md, 0.8467 |
| q22 | multi_evidence | 0.0 | 0.5 | False | ranked_below_top_k | Python_Tutorial_Interpreter.md, 0.9712 |
| q24 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Software_Architecture_Design.md, 0.765 |
| q29 | mixed_language | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | OWL2_Document_Overview.md, 0.5654 |

> 命中正文与逐条位置只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。

## Unanswerable queries

- ids: q31, q32, q33, q34, q35, q36
- top-1 distances: [0.6277, 0.6317, 0.8225, 0.8432, 0.9822, 1.2192]
- 检索层无阈值，故这些查询仍会返回片段；正确处理在 Agent 层评价。
