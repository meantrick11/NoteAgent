# Agent eval agent-v1-v10-dev

- variant: `v10` split: `dev` repeats: 3
- runs: 36

## Metrics

| metric | passed/total | rate |
|---|---|---|
| Agent 任务成功率（历史场景） | 30/30 | 1.0 |
| Agent 任务成功率（严格引用口径） | 29/30 | 0.9667 |
| 历史任务检索调用率 | 25/30 | 0.8333 |
| 无需检索误调用率 | 0/6 | 0.0 |
| 普通对话不写盘 | 5/6 | 0.8333 |
| 历史无答案正确处理率 | 6/6 | 1.0 |
| 检索片段覆盖必需证据 | 15/24 | 0.625 |
| 靠 read_file 兜回正确笔记 | 6/30 | 0.2 |
| 引用可定位到文件 | 34/34 | 1.0 |
| 引用带回引文（可到章节/原文） | 24/34 | 0.7059 |

## By scenario

| scenario | task success | strict | search called | errors |
|---|---|---|---|---|
| history_answer | 12/12 | 11/12 | 12/12 | 0 |
| history_append | 12/12 | 12/12 | 7/12 | 0 |
| history_unanswerable | 6/6 | 6/6 | 6/6 | 0 |
| plain_chat | 5/6 | 5/6 | 0/6 | 0 |

## Per case (逐次成功分布)

| case | runs | success | strict |
|---|---|---|---|
| a01 | 3 | 3 | 2 |
| a02 | 3 | 3 | 3 |
| a03 | 3 | 3 | 3 |
| a04 | 3 | 3 | 3 |
| a05 | 3 | 3 | 3 |
| a06 | 3 | 3 | 3 |
| a07 | 3 | 3 | 3 |
| a08 | 3 | 3 | 3 |
| a09 | 3 | 3 | 3 |
| a10 | 3 | 3 | 3 |
| a11 | 3 | 3 | 3 |
| a12 | 3 | 2 | 2 |

## Per run checks

- `a01` r1 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=['recovered_by_read']
- `a01` r2 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient']
- `a01` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=['recovered_by_read']
- `a02` r1 success=True tools=['search_relative_from_chromadb', 'list_files'] failed=['recovered_by_read']
- `a02` r2 success=True tools=['search_relative_from_chromadb'] failed=['recovered_by_read']
- `a02` r3 success=True tools=['search_relative_from_chromadb', 'list_files'] failed=['recovered_by_read']
- `a03` r1 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=['recovered_by_read']
- `a03` r2 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb', 'read_file'] failed=['recovered_by_read']
- `a03` r3 success=True tools=['search_relative_from_chromadb', 'list_files'] failed=['recovered_by_read']
- `a04` r1 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb'] failed=['recovered_by_read']
- `a04` r2 success=True tools=['search_relative_from_chromadb', 'list_files'] failed=['recovered_by_read']
- `a04` r3 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb'] failed=['recovered_by_read']
- `a05` r1 success=True tools=['list_files', 'read_file'] failed=['search_called', 'evidence_cited_search_only', 'retrieval_sufficient']
- `a05` r2 success=True tools=['list_files', 'read_file'] failed=['search_called', 'evidence_cited_search_only', 'retrieval_sufficient']
- `a05` r3 success=True tools=['list_files', 'read_file'] failed=['search_called', 'evidence_cited', 'evidence_cited_search_only', 'retrieval_sufficient', 'recovered_by_read']
- `a06` r1 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient', 'no_draft_explained']
- `a06` r2 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['recovered_by_read', 'no_draft_explained']
- `a06` r3 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient', 'no_draft_explained']
- `a07` r1 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited', 'evidence_cited_search_only', 'recovered_by_read', 'no_draft_explained']
- `a07` r2 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['recovered_by_read']
- `a07` r3 success=True tools=['list_files', 'read_file'] failed=['search_called', 'evidence_cited_search_only', 'retrieval_sufficient']
- `a08` r1 success=True tools=['list_files', 'read_file', 'propose_note'] failed=['search_called', 'evidence_cited', 'evidence_cited_search_only', 'retrieval_sufficient', 'recovered_by_read']
- `a08` r2 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file', 'propose_note'] failed=['evidence_cited', 'evidence_cited_search_only', 'retrieval_sufficient', 'recovered_by_read']
- `a08` r3 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file', 'propose_note'] failed=['evidence_cited', 'evidence_cited_search_only', 'recovered_by_read']
- `a09` r1 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb', 'list_files'] failed=none
- `a09` r2 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb', 'list_files'] failed=none
- `a09` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'search_relative_from_chromadb', 'search_relative_from_chromadb'] failed=none
- `a10` r1 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=none
- `a10` r2 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=none
- `a10` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=none
- `a11` r1 success=True tools=[] failed=none
- `a11` r2 success=True tools=[] failed=none
- `a11` r3 success=True tools=[] failed=none
- `a12` r1 success=True tools=[] failed=none
- `a12` r2 success=True tools=[] failed=none
- `a12` r3 success=False tools=['list_files', 'propose_note'] failed=['no_write']

> 模型回答、检索片段与草稿正文只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。