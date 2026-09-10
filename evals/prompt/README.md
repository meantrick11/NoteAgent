# prompt evals

准则见 [docs/evaluations/note-quality.md](../../docs/evaluations/note-quality.md)。不要把私人笔记全文写进 `user`。本目录放考题 JSONL 和离线跑分结果。

## 包含模块

| 文件 | 作用 |
|------|------|
| [`cases.jsonl`](cases.jsonl) | 一行一条；20 条（n01–n13 正文，b01–b07 行为） |
| [`learning_notes.jsonl`](learning_notes.jsonl) | v0.2 学习型笔记校准集；首条为 Python 教程第 1 章 |
| [`fixtures/learning_notes/`](fixtures/learning_notes/) | 四个固定候选，只作评测输入，不写入用户 notes |
| [`results/`](results/README.md) | `python scripts/eval_notes.py` 写出的报告（按 jsonl 主文件名分子目录） |

| id | kind | 测什么 |
|----|------|--------|
| n01 | quality | 解释器教程标题树 + 记下来 |
| n02 | quality | 带 3. / 3.1. 的短节 + 整理成笔记 |
| n03 | quality | 含 python -c / -m 的命令段落；草稿须含围栏代码块（must_substrings） |
| n04 | quality | 无编号标题的叙述（GIL） |
| n05 | quality | 只要提纲 |
| n06 | quality | 只要 2.1.2 交互模式 |
| n07 | quality | 情态：通常 / 可能 / 往往 / 建议 / 默认 |
| n08 | quality | 备注 + 命令；须有 `>` 与围栏 |
| n09 | quality | 英文材料译成中文笔记 |
| n10 | quality | 长教程：勿压成提纲、勿合并标题 |
| n11 | quality | 无编号叙述（装饰器）；禁自拟「装饰器原理」 |
| n12 | quality | 段落整理，不要改成要点清单 |
| n13 | quality | 只要 2.2.1 编码一节 |
| b01 | behavior | 只贴长文、无说明 → 先问、不提案 |
| b02 | behavior | 短句 + 记下来 → list_files 再提案 |
| b03 | behavior | 寒暄 → 不提案 |
| b04 | behavior | 问旧笔记 argv → search、不提案（`seed_files`） |
| b05 | behavior | 明确更正过时表述 → list_files，提案 replace（`seed_files`） |
| b06 | behavior | 明确删文件 → list_files，提案 delete（`seed_files`） |
| b07 | behavior | 往已有主题再补一节 → list_files，提案 append 或 create，不得 replace |

## 基础使用

```bash
python scripts/eval_notes.py --ids b06,n05
python scripts/eval_notes.py --name v8 --ids n01,n03 --prompt src/noteagent/chat/prompts/system.txt
```

脚本在进程内跑 `ChatAgent`（真实 `CHAT_MODEL` + 四工具），不启动 FastAPI，不写用户 `notes/`，不 `commit_review`。无密钥时退出码 1。结果在 [`results/cases/`](results/README.md) 下，文件夹名含题号。不进默认 CI。

仍可把某条 `user` 贴进 `http://127.0.0.1:8000` 做人工对照；改过 [`system.txt`](../../src/noteagent/chat/prompts/system.txt) 后先重启进程。

## v0.2 学习型校准集

`learning_notes.jsonl` 的 `l01` 保存 Python 官方教程 “1. Whetting Your Appetite” 的完整英文材料，任务是“将这篇文章翻译并整理为合适的笔记”。新增字段描述任务模式、输出语言、必需概念、必需关系、应保留模态、禁止命题、复习问题和质量阈值；旧 `cases.jsonl` 未提供这些字段时按空值加载，保持兼容。

人工校准必须遵守固定排序：

```text
good.md > literal.md > omitted.md
hallucinated.md 因无来源命题被忠实硬门淘汰
```

- `good.md` 是忠实且完整的语义重组；
- `literal.md` 是忠实、完整但加工不足的逐段译文；
- `omitted.md` 文笔可读但缺关键内容，完整硬门失败；
- `hallucinated.md` 可读但加入动态类型、GIL、异步优势等来源外结论，忠实硬门失败。

边界：该数据集只校准“长篇教程 / 技术文章 → 中文学习型笔记”，不替代行为题，不进入用户私人笔记，也不证明对所有教程已经泛化。本阶段没有 Judge 自动判定；不得用字符比、句子边界或标题数量代替上述人工语义契约。
