# 评测实现

生产应用不依赖本包。测试通过根 pyproject.toml 的 Tools 搜索路径加载；脚本显式加入 Tools 路径，现有命令保持可用。

| 目录 | 职责 |
|---|---|
| [prompt](Prompt/README.md) | 样例、运行、评分、Judge、校准与报告 |
| [rag](Rag/README.md) | 检索数据集、指标、RAG 与 Agent 评测 |

样例、准则和结果在 [evals](../../evals/README.md)，当前提示词在 src/NoteAgent/BusinessModules/ChatAgent/SystemPrompts/system.txt，历史版本在 evals/prompt/iterations。

```powershell
uv run python Scripts/EvalNotes.py --help
uv run python Scripts/EvalRag.py --help
uv run python Scripts/EvalRagAgent.py --help
uv run pytest Tests/Unit/TestPromptEvalRun.py Tests/Unit/TestRagEval.py -q
```
