# Retrieval eval rag-v1-baseline-dev

- variant: `baseline` split: `dev` top_k: 5 probe_k: 20
- model: `all-MiniLM-L6-v2` revision `None`
- chunker: {'chunk_size': 500, 'chunk_overlap': 50} distance: chroma-default-l2
- corpus manifest sha256: `67cb5e504bbae91e693ea3835a5f83ecac9a0c7f7a9eebf2886f4a2fc5b7f4ad`
- queries sha256: `295300838802bc90243fb9e6451ab68c3fb07499ebefaf7fb32896a814aee636`
- git: `9e951ac1edd19396968e7107d59668096d00bc32` dirty: yes
- index build: 7781 ms

## Metrics

| set | metric | passed/total | rate |
|---|---|---|---|
| answerable | full Evidence Recall@5 | 5/18 | 0.2778 |
| answerable | Evidence Hit@3 | 3/18 | 0.1667 |
| answerable | mean Evidence Recall@5 | - | 0.2778 |
| answerable | MRR@5 | - | 0.1639 |
| answerable (diagnostic) | mean Evidence Recall@20 | - | 0.6944 |
| answerable (diagnostic) | full Recall@20 | 12/18 | 0.6667 |

## By category

| category | full recall@k | hit@3 | mean recall@k | mrr | mean recall@probe |
|---|---|---|---|---|---|
| fact | 3/7 | 2/7 | 0.4286 | 0.3214 | 0.7143 |
| mixed_language | 2/3 | 1/3 | 0.6667 | 0.2333 | 1.0 |
| multi_evidence | 0/4 | 0/4 | 0.0 | 0.0 | 0.875 |
| paraphrase | 0/4 | 0/4 | 0.0 | 0.0 | 0.25 |

## Latency (hot queries)

- samples: 72 (warmup 3x24)
- min: 65.57 ms, p50: 191.15 ms, p95: 240.14 ms
- index build: 7781 ms
- 同机其他进程会显著干扰本机延迟；跨 run 比较以 min 为准，并注明测量时段。

## Failures

失败分类：`ranked_below_top_k` 放到更深候选就能覆盖；`partial_evidence` 只覆盖了部分 unit；`evidence_not_in_returned_fragments` 返回的片段里没有可完整覆盖的证据；`mapping_error` 片段无法映射回原文；`no_fragments` 检索为空。

| query | category | recall@k | recall@probe | hit@3 | failure | top hit (file, distance) |
|---|---|---|---|---|---|---|
| q01 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Intro.md, 0.7508 |
| q02 | paraphrase | 0.0 | 1.0 | False | ranked_below_top_k | Python_Tutorial_Intro.md, 0.8768 |
| q05 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | OWL2_Document_Overview.md, 0.9788 |
| q08 | fact | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Intro.md, 0.7283 |
| q09 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | BinaryTree.md, 1.1128 |
| q11 | fact | 0.0 | 1.0 | False | ranked_below_top_k | Python_Tutorial_Intro.md, 0.928 |
| q12 | paraphrase | 0.0 | 0.0 | False | evidence_not_in_returned_fragments | Python_Tutorial_Intro.md, 1.128 |
| q13 | multi_evidence | 0.0 | 1.0 | False | ranked_below_top_k | Writing_Effective_Tools_for_Agents.md, 1.0269 |
| q16 | multi_evidence | 0.0 | 1.0 | False | ranked_below_top_k | Python_Tutorial_Intro.md, 0.9252 |
| q19 | multi_evidence | 0.0 | 1.0 | False | ranked_below_top_k | Python_Tutorial_Intro.md, 1.1546 |
| q21 | mixed_language | 0.0 | 1.0 | False | ranked_below_top_k | BinaryTree.md, 1.0363 |
| q22 | multi_evidence | 0.0 | 0.5 | False | ranked_below_top_k | BinaryTree.md, 1.0246 |
| q24 | fact | 0.0 | 1.0 | False | ranked_below_top_k | OWL2_Document_Overview.md, 0.9076 |

> 命中正文与逐条位置只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。

## Unanswerable queries

- ids: q31, q32, q33, q34, q35, q36
- top-1 distances: [0.6053, 0.8076, 0.8319, 1.0189, 1.0839, 1.2359]
- 检索层无阈值，故这些查询仍会返回片段；正确处理在 Agent 层评价。
