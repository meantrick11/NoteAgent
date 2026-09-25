# Agent eval agent-v1-baseline-holdout

- variant: `baseline` split: `holdout` repeats: 3
- runs: 24

## Metrics

| metric | passed/total | rate |
|---|---|---|
| Agent 任务成功率（历史场景） | 17/18 | 0.9444 |
| Agent 任务成功率（严格引用口径） | 11/18 | 0.6111 |
| 历史任务检索调用率（门槛口径：问答+无答案） | 12/12 | 1.0 |
| 检索调用率（全部历史场景，含追加） | 16/18 | 0.8889 |
| 追加场景检索调用率（另报，不计门槛） | 4/6 | 0.6667 |
| 无需检索误调用率 | 0/6 | 0.0 |
| 普通对话不写盘 | 6/6 | 1.0 |
| 历史无答案正确处理率 | 5/6 | 0.8333 |
| 检索片段覆盖必需证据 | 4/12 | 0.3333 |
| 靠 read_file 兜回正确笔记 | 5/18 | 0.2778 |
| 引用可定位到文件 | 19/19 | 1.0 |
| 引用带回引文（可到章节/原文） | 9/19 | 0.4737 |

## By scenario

| scenario | task success | strict | search called | errors |
|---|---|---|---|---|
| history_answer | 6/6 | 0/6 | 6/6 | 0 |
| history_append | 6/6 | 6/6 | 4/6 | 0 |
| history_unanswerable | 5/6 | 5/6 | 6/6 | 0 |
| plain_chat | 6/6 | 6/6 | 0/6 | 0 |

## Per case (逐次成功分布)

| case | runs | success | strict |
|---|---|---|---|
| a13 | 3 | 3 | 0 |
| a14 | 3 | 3 | 0 |
| a15 | 3 | 3 | 3 |
| a16 | 3 | 3 | 3 |
| a17 | 3 | 2 | 2 |
| a18 | 3 | 3 | 3 |
| a19 | 3 | 3 | 3 |
| a20 | 3 | 3 | 3 |

## Per run checks

- `a13` r1 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient']
- `a13` r2 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'recovered_by_read']
- `a13` r3 success=True tools=['search_relative_from_chromadb', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'recovered_by_read']
- `a14` r1 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient']
- `a14` r2 success=True tools=['search_relative_from_chromadb', 'list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient']
- `a14` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'search_relative_from_chromadb', 'read_file'] failed=['evidence_cited_search_only', 'retrieval_sufficient']
- `a15` r1 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file', 'propose_note'] failed=['evidence_cited', 'evidence_cited_search_only', 'retrieval_sufficient', 'recovered_by_read']
- `a15` r2 success=True tools=['list_files', 'search_relative_from_chromadb', 'read_file', 'propose_note'] failed=['evidence_cited', 'evidence_cited_search_only', 'retrieval_sufficient', 'recovered_by_read']
- `a15` r3 success=True tools=['list_files', 'read_file', 'propose_note'] failed=['search_called', 'evidence_cited', 'evidence_cited_search_only', 'retrieval_sufficient', 'recovered_by_read']
- `a16` r1 success=True tools=['list_files', 'read_file'] failed=['search_called', 'evidence_cited_search_only', 'retrieval_sufficient']
- `a16` r2 success=True tools=['list_files', 'search_relative_from_chromadb'] failed=['recovered_by_read']
- `a16` r3 success=True tools=['list_files', 'search_relative_from_chromadb'] failed=['recovered_by_read']
- `a17` r1 success=False tools=['search_relative_from_chromadb', 'list_files'] failed=['states_no_evidence']
- `a17` r2 success=True tools=['search_relative_from_chromadb', 'list_files'] failed=none
- `a17` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'search_relative_from_chromadb'] failed=none
- `a18` r1 success=True tools=['search_relative_from_chromadb', 'list_files', 'search_relative_from_chromadb', 'search_relative_from_chromadb', 'read_file'] failed=none
- `a18` r2 success=True tools=['search_relative_from_chromadb', 'list_files', 'search_relative_from_chromadb', 'read_file'] failed=none
- `a18` r3 success=True tools=['search_relative_from_chromadb', 'list_files', 'read_file', 'search_relative_from_chromadb'] failed=none
- `a19` r1 success=True tools=[] failed=none
- `a19` r2 success=True tools=[] failed=none
- `a19` r3 success=True tools=[] failed=none
- `a20` r1 success=True tools=[] failed=none
- `a20` r2 success=True tools=[] failed=none
- `a20` r3 success=True tools=[] failed=none

> 模型回答、检索片段与草稿正文只保存在本地 `var/evals/rag/<run-id>/`（隐私语料）。