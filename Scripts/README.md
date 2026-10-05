# Scripts

运维/调试脚本。只调用 `noteagent` 包，密钥只从环境变量读。

## 包含模块

| 文件 | 作用 |
|------|------|
| `IndexNotes.py` | 按篇重建 Chroma（与审批后的 `index_note` 相同；collection 损坏时用）。目标枚举与界面共用 `modules.retrieval.service.index_targets`，排除规则一致 |
| `SdkSmoke.py` | 用 `DEEPSEEK_API_KEY` ping 一次聊天 API |
| `EvalNotes.py` | 离线提示词评测：进程内 `ChatAgent`，结果写入 `evals/prompt/results/<jsonl 主文件名>/` |
| `CalibrateLearningNotes.py` | 用四个固定候选校准 v0.2 Judge（不生成草稿） |
| `BuildRagQueries.py` | 从人工标注草稿生成带偏移的检索查询集，并跑正式校验 |
| `VerifyRagCorpus.py` | 复核语料审查结论与 10 条无答案标注；任一条不成立即以非零码退出 |
| `DownloadModels.py` | 走镜像把候选向量模型取到 `EMBEDDING_CACHE_DIR`（huggingface_hub 会因镜像不回 `x-repo-commit` 头而拒下，故手工构建缓存布局；按 LFS sha256 校验） |
| `EvalRag.py` | 直接检索评测：真 `RetrievalService` + 独立 Chroma，指标与失败分类 |
| `EvalRagAgent.py` | 真实 `ChatAgent` 场景评测：调用时机、结果使用、引用、写入安全 |

## 基础使用

索引一篇笔记（需已配置 embedding 缓存）：

```bash
uv run python Scripts/IndexNotes.py Agent.md
# 成功会打印 indexed Agent.md: N chunks
uv run python Scripts/IndexNotes.py --help
```

注意它与界面切换向量模型的关系：

- 脚本与运行时用同一套解析：`MODEL_SETTINGS_DIR/settings.json` 里持久化的 active（模型 + collection）优先，没有保存过才用 `.env` 的 `EMBEDDING_MODEL` / `CHROMA_COLLECTION`。开头会打印 `model` / `collection` / `target from`，先看这三行再动手。
- 界面正在重建（维护窗口）时不要同时跑脚本：外部进程不受门禁约束，脚本的写入会让界面的"外部修改"校验失败并放弃发布。
- 界面切换用的集合名是 `{CHROMA_COLLECTION}__{模型短名}`；脚本按上面的规则写同一个集合，不会去改旧模型建的库。

检查 DeepSeek 密钥是否可用：

```bash
uv run python Scripts/SdkSmoke.py
# 未设置密钥时退出码 1
```

跑提示词黄金集（不启动 HTTP、不写用户 `notes/`、不人审）：

```bash
python Scripts/EvalNotes.py --ids b06,n05
python Scripts/EvalNotes.py --name v8 --ids n01,n03
python Scripts/EvalNotes.py --name v9 --judge --cases evals/prompt/learning_notes.jsonl --ids l01
python Scripts/CalibrateLearningNotes.py
# 结果在 evals/prompt/results/<jsonl 主文件名>/<标签_>题号_时间/ ；未设置密钥时退出码 1
```

跑检索与 Agent 评测（不改生产 `notes/`、不改生产 Chroma、不人审写盘）：

```bash
python Scripts/BuildRagQueries.py --corpus evals/rag/corpus/v1 \
  --draft evals/rag/queries.v1.draft.json --output evals/rag/queries.v1.jsonl
python Scripts/EvalRag.py --split dev --variant baseline --run-id rag-v1-baseline-dev
python Scripts/EvalRagAgent.py --split dev --variant baseline --run-id agent-v1-baseline-dev --repeat 3
# 换向量模型：编码指令按模型自动应用；复现旧基线要显式给 --strategy char --no-embed-heading-prefix
python Scripts/EvalRag.py --split holdout --variant selected --model intfloat/multilingual-e5-small \n  --run-id rag-v1-selected-holdout
python Scripts/EvalRagAgent.py --split holdout --variant selected --model intfloat/multilingual-e5-small \n  --run-id agent-v1-selected-holdout --repeat 3
# 只修判定口径、不重跑模型：复用已存结果重算结论（幂等）
python Scripts/EvalRagAgent.py --split dev --variant x --run-id agent-v1-v10-dev --rescore
# 候选模型下载（会写 EMBEDDING_CACHE_DIR，先跑 --dry-run 看清单）
python Scripts/DownloadModels.py --dry-run
python Scripts/DownloadModels.py
# 完整报告在 var/evals/rag/<run-id>/ ；提交版 summary 在 evals/{rag,agent}/results/<run-id>/
```

准则与字段契约：[rag-quality.md](../evals/criteria/rag-quality.md)；数据位置：[evals/rag/README.md](../evals/rag/README.md)、[evals/agent/README.md](../evals/agent/README.md)。

## 实现位置

Scripts 保留稳定的命令行入口。评测算法、评分、Judge、报告和检索实验实现在 [Tools/NoteAgentEvals](../Tools/NoteAgentEvals/README.md)；评测数据、准则、提示词历史及归档报告在 [evals](../evals/README.md)。业务源码导航见 [src/NoteAgent](../src/NoteAgent/README.md)。从仓库根目录运行上述命令，评测脚本会加入 Tools 搜索路径。
