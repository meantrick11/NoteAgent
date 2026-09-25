# Agent eval agent-v1-baseline-dev

- variant: `baseline` split: `dev` repeats: 3
- runs: 36

## Metrics

| metric | passed/total | rate |
|---|---|---|
| Agent 任务成功率（历史场景） | 25/30 | 0.8333 |
| Agent 任务成功率（严格引用口径） | 22/30 | 0.7333 |
| 历史任务检索调用率 | 26/30 | 0.8667 |
| 无需检索误调用率 | 0/6 | 0.0 |
| 普通对话不写盘 | 6/6 | 1.0 |
| 历史无答案正确处理率 | 3/6 | 0.5 |
| 检索片段覆盖必需证据 | 15/24 | 0.625 |
| 靠 read_file 兜回正确笔记 | 7/30 | 0.2333 |
| 引用可定位到文件 | 32/32 | 1.0 |
| 引用带回引文（可到章节/原文） | 18/32 | 0.5625 |

## By scenario

| scenario | task success | strict | search called | errors |
|---|---|---|---|---|
| history_answer | 12/12 | 9/12 | 12/12 | 0 |
| history_append | 10/12 | 10/12 | 8/12 | 0 |
| history_unanswerable | 3/6 | 3/6 | 6/6 | 0 |
| plain_chat | 6/6 | 6/6 | 0/6 | 0 |

## Per case (逐次成功分布)

| case | runs | success | strict |
|---|---|---|---|
| a01 | 3 | 3 | 0 |
| a02 | 3 | 3 | 3 |
| a03 | 3 | 3 | 3 |
| a04 | 3 | 3 | 3 |
| a05 | 3 | 3 | 3 |
| a06 | 3 | 1 | 1 |
| a07 | 3 | 3 | 3 |
| a08 | 3 | 3 | 3 |
| a09 | 3 | 1 | 1 |
| a10 | 3 | 2 | 2 |
| a11 | 3 | 3 | 3 |
| a12 | 3 | 3 | 3 |

## Per run checks

- `a01` r1 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient']
- `a01` r2 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb', 'list_files', 'search_relative_from_chromadb', 'read_file', 'search_relative_from_chromadb'] failed=['evidence_cited_search_only', 'retrieval_sufficient']
- `a01` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient']
- `a02` r1 success=True tools=['search_relative_from_chromadb', 'list_files'] failed=['recovered_by_read']
- `a02` r2 success=True tools=['search_relative_from_chromadb', 'list_files'] failed=['recovered_by_read']
- `a02` r3 success=True tools=['search_relative_from_chromadb', 'list_files'] failed=['recovered_by_read']
- `a03` r1 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb'] failed=['recovered_by_read']
- `a03` r2 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=['recovered_by_read']
- `a03` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=['recovered_by_read']
- `a04` r1 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb'] failed=['recovered_by_read']
- `a04` r2 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb', 'search_relative_from_chromadb', 'search_relative_from_chromadb'] failed=['recovered_by_read']
- `a04` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file', 'search_relative_from_chromadb'] failed=['recovered_by_read']
- `a05` r1 success=True tools=['list_files', 'read_file'] failed=['search_called', 'evidence_cited_search_only', 'retrieval_sufficient']
- `a05` r2 success=True tools=['list_files', 'read_file'] failed=['search_called', 'evidence_cited_search_only', 'retrieval_sufficient']
- `a05` r3 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'recovered_by_read']
- `a06` r1 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient', 'no_draft_explained']
- `a06` r2 success=False tools=['list_files', 'search_relative_from_chromadb', 'read_file', 'propose_note'] failed=['evidence_cited', 'evidence_cited_search_only', 'retrieval_sufficient', 'recovered_by_read', 'flags_conflict', 'must_preserve']
- `a06` r3 success=False tools=['list_files', 'read_file', 'propose_note'] failed=['search_called', 'evidence_cited_search_only', 'retrieval_sufficient', 'flags_conflict', 'must_preserve']
- `a07` r1 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'recovered_by_read']
- `a07` r2 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'recovered_by_read']
- `a07` r3 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'recovered_by_read']
- `a08` r1 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file', 'propose_note'] failed=['evidence_cited', 'evidence_cited_search_only', 'recovered_by_read']
- `a08` r2 success=True tools=['list_files', 'read_file', 'propose_note'] failed=['search_called', 'evidence_cited', 'evidence_cited_search_only', 'retrieval_sufficient', 'recovered_by_read']
- `a08` r3 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file', 'propose_note'] failed=['evidence_cited', 'evidence_cited_search_only', 'recovered_by_read']
- `a09` r1 success=False tools=['search_relative_from_chromadb', 'list_files', 'search_relative_from_chromadb'] failed=['states_no_evidence']
- `a09` r2 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb', 'list_files'] failed=none
- `a09` r3 success=False tools=['search_relative_from_chromadb', 'list_files', 'search_relative_from_chromadb', 'search_relative_from_chromadb'] failed=['states_no_evidence']
- `a10` r1 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=none
- `a10` r2 success=False tools=['search_relative_from_chromadb', 'list_files', 'read_file', 'search_relative_from_chromadb', 'search_relative_from_chromadb'] failed=['states_no_evidence']
- `a10` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file', 'search_relative_from_chromadb'] failed=none
- `a11` r1 success=True tools=[] failed=none
- `a11` r2 success=True tools=[] failed=none
- `a11` r3 success=True tools=[] failed=none
- `a12` r1 success=True tools=[] failed=none
- `a12` r2 success=True tools=[] failed=none
- `a12` r3 success=True tools=[] failed=none

> 模型回答、检索片段与草稿正文只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。