# V1 收尾修复与生成验收集：Claude 执行计划

> **交给 Claude 执行：**按任务顺序完成实现、离线评测与结果归档，逐项勾选并记录实际结果。可使用环境中已有的 executing-plans / subagent-driven-development 技能辅助执行；技能不可用时按本计划直接执行，不为此安装依赖。手动功能测试由用户负责，不操作浏览器代替用户验收，不将其标为通过。

**目标：**修复审批写盘失败后草稿丢失的小 bug，构建至少 20 条真正产生笔记正文的完整验收样例，执行自动测试及真实模型生成评测，并归档可核对的验收结果。

**设计：**保持每个 conversation 只有一份 `conversations.pending_draft`，复用 `DraftStore` 和 `commit_review`。生成样例复用现有 `EvalCase`、JSONL 和 `scripts/eval_notes.py`，不新增运行时评分或自动审批流程。正文生成、行为回归和手动功能验收分别记账。

**技术栈：**Python 3.13、pytest、SQLAlchemy、现有 ChatAgent 与 prompt_eval。

**需求依据：**用户已指定三项工作：写入异常 bug 修复、完整生成验收样例集构建、执行测试并记录结果；用户自行执行手动功能测试。另参考 [版本路线图 V1](../roadmap/versions.md)、[评测说明](../evaluations/README.md)、[prompt 样例说明](../../evals/prompt/README.md)。本计划不代表 V1 已验收。

## 约束与执行前检查

- 阅读根目录 `CLAUDE.md`、当前目录适用的 `AGENTS.md`（若存在）及下表相关文件。
- 先运行 `git status --short`，保留用户已有修改，不覆盖参考笔记、代码解析文档等无关内容。不自动提交、推送、合并或发布。
- 本计划授权修复与测试，不授权扩展网页、多模态、通用工作流、并发审批协议或分布式事务。
- 不重写草稿存储机制，不引入新的测试框架、数据库或前端依赖。
- 自动测试只使用临时目录、测试数据库和模型替身；真实模型评测走已有离线入口，不写用户 `notes/`，不调用 `commit_review` 自动批准模型输出。
- 执行真实生成评测会调用已配置供应商并产生费用，属于本计划的评测步骤；只发送本计划的合成公开测试材料，不读取或上传私人笔记。不得输出凭据，不改用户模型配置。
- 模型凭据或网络不可用时，完成所有不依赖模型的工作，报告评测阻塞。不得以 mock 结果代替真实生成结果。
- 不把 V2 的结构加工高分作为 V1 退出门槛；也不通过删除失败样例、改期望或挑选最好的一次结果制造通过。
- 报告使用已有 `docs/evaluations/`，不另建 `evaluation/`。样例和原始跑分分别留在 `evals/prompt/` 与 `evals/prompt/results/`。

## 文件职责地图

| 路径 | 操作与职责 |
|---|---|
| `src/noteagent/chat/drafts.py` | 修复写盘异常后的草稿保留、错误返回及日志 |
| `tests/unit/test_drafts.py` | 异常、恢复、再次审批及不调用索引的回归测试 |
| `tests/unit/test_chat_history.py` | 已有数据库草稿契约；必要时补实际存储读取断言 |
| `src/noteagent/notes/repository.py` | 阅读以核对写入阶段和异常，不默认重构 |
| `evals/prompt/v1_acceptance.jsonl` | 新建 25 条生成验收输入，独立于旧集保存 |
| `evals/prompt/v1_acceptance.md` | 新建分类清单、目标文件、内容断言、运行及验收口径 |
| `tests/unit/test_v1_acceptance_cases.py` | 新建样例完整性、分类覆盖及现有加载器兼容检查 |
| `evals/prompt/README.md` | 补新样例集入口与边界 |
| `docs/evaluations/v1-acceptance-report.md` | 新建本轮自动测试、生成评测、失败及手动待验项目报告 |
| `docs/evaluations/README.md` | 增加报告入口 |
| `docs/roadmap/versions.md` | 仅同步有证据的状态、修正过时查询集描述，不宣布 V1 全部完成 |

## 任务 1：修复写盘异常导致待审草稿丢失

### 已确认的原因与修复边界

`commit_review` 先 `store.pop(thread_id)`，该操作读取后清空数据库字段。随后 `_write_draft` 发生异常时，当前只处理 `FileNotFoundError / FileExistsError / NotePathError / ValueError`，没有处理 `PermissionError` 或其它 `OSError`，因此不能恢复唯一的待审草稿。

采用局部修复：保持当前审批流程，扩展明确的文件操作异常捕获。`FileNotFoundError` 和 `FileExistsError` 都是 `OSError` 子类，可将该捕获元组简化为 `(OSError, ValueError)`；`NotePathError` 继承 `ValueError`。不要直接捕获所有 `Exception` 并吞掉程序错误。

这项修复保证**写盘异常后草稿仍在数据库中**。它不自动保证文件写入原子性：当前 create 是先创建标题再追加正文，append/replace 也可能部分写入。必须检查并记录这个边界，不得把“保留草稿”写成“文件和数据库事务回滚成功”。本轮不扩展为文件事务改造。

### 执行步骤

- [ ] 在 `tests/unit/test_drafts.py` 引入 `pytest`，增加下面的异常与重试测试。使用既有 `_store_with` 和 `FakeRetrieval`，它们分别操作测试数据库和记录索引调用。

```python
@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("disk failure")])
def test_write_error_preserves_draft_and_allows_retry(tmp_path, monkeypatch, error):
    notes = FileNoteRepository(tmp_path)
    notes.create("A.md", "A")
    before = notes.read("A.md")
    draft = NoteDraft(action="append", file_name="A.md", content="## New\n\nbody\n")
    store, tid = _store_with(draft)
    retrieval = FakeRetrieval()
    original_write = notes.write

    def fail_write(*args, **kwargs):
        raise error

    monkeypatch.setattr(notes, "write", fail_write)
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert "error" in result
    # 新包装器重新读取同一个测试数据库，不能只检查局部 draft 变量。
    assert DraftStore(store._history).get(tid).as_dict() == draft.as_dict()
    assert notes.read("A.md") == before
    assert retrieval.indexed == []
    assert retrieval.deleted == []

    monkeypatch.setattr(notes, "write", original_write)
    result = commit_review(notes, store, tid, "approve", retrieval=retrieval)
    assert result["status"] == "written"
    assert store.get(tid) is None
    assert notes.read("A.md").count("## New") == 1
    assert retrieval.indexed == ["A.md"]
```

- [ ] 运行该测试，确认修复前由注入的文件操作异常导致失败，而非测试环境错误。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_drafts.py -q -k write_error
```

- [ ] 将 `commit_review` 的写盘捕获分支改为以下逻辑；沿用现有错误响应，日志保留 thread、action、目标文件及异常，不打印草稿全文。

```python
    except (OSError, ValueError) as exc:
        store.put(thread_id, draft)
        _logger.warning(
            "draft write failed thread=%s action=%s file=%s error=%s",
            thread_id, target_action, target_name, exc,
        )
        return {"error": str(exc)}
```

- [ ] 按同一断言契约补齐以下有意义的操作边界，用 `monkeypatch` 注入异常，不修改真实目录权限：

| 场景 | 注入位置 | 必须断言 |
|---|---|---|
| create 在创建前失败 | `notes.create` | 数据库草稿完整保留、未建目标文件、不索引；恢复后同一草稿可创建 |
| replace 在写入前失败 | `notes.write` | 原文不变、草稿保留；恢复后可覆盖 |
| delete 在删除前失败 | `notes.delete` | 文件仍在、草稿保留、未删向量；恢复后可删除 |
| override 写盘失败 | 覆写目标的 `notes.write` | 保留原始提案全部字段，目标文件未变，可再次指定 override |
| create 已建标题、追加正文失败 | `notes.write` | 草稿保留、不索引；明确记录残留标题文件及同名 create 重试冲突，不宣称无损重试 |

- [ ] 保留并运行拒绝、不存在文件、非法路径、成功后清空草稿的原有测试。特别确认 `test_index_failure_keeps_written_file` 仍通过：索引失败不是文件写盘失败，已成功写入的草稿不应恢复成待审而导致重复写入。
- [ ] 运行 `tests/unit/test_drafts.py`、`tests/unit/test_chat_history.py`、`tests/integration/test_retrieval_service.py`。在报告中区分“写入前失败可直接重试”与“部分写入后保留草稿但可能需核对文件”。

## 任务 2：构建完整生成验收样例集

### 数据与数量口径

建立新的 `v1_acceptance.jsonl`，固定 **25 个不同输入，五类各 5 条**。每条 `kind=quality`、`expect_propose=true`，预期动作仅为 create / append / replace，必须要求非空笔记正文。寒暄、拒绝生成、只检索、删除和固定候选评分不计入这 25 条；旧行为题仍单独回归。

每行兼容 `src/noteagent/prompt_eval/cases.py` 的现有字段。额外增加 `category` 仅供原始 JSON 数据的完整性检查和报告分组；现有加载器忽略未知字段，不需要为此修改运行时模型。目标文件及逐条语义断言放在配套 Markdown 清单中，不伪称现有脚本已自动校验这些内容。

| ID | 分类 | 完整输入应包含的内容与主要断言 |
|---|---|---|
| g01 | dialogue | 项目周会对话：负责人、任务、截止日期；保留各自归属 |
| g02 | dialogue | 学习讨论：定义、一个例子、一项限制；不可只记结论 |
| g03 | dialogue | 决策讨论：两个方案、理由、最终选择；区分讨论与已决定事项 |
| g04 | dialogue | 故障排查对话：现象、失败尝试、有效步骤；保留先后顺序 |
| g05 | dialogue | 计划变更对话：旧日期与明确更正的新日期；按最新决定整理 |
| g06 | long_text | 合成教程：至少 5 节，含定义、步骤、例子和限制 |
| g07 | long_text | 合成操作手册：前提、安装、执行、检查、恢复；不得遗漏恢复条件 |
| g08 | long_text | 合成技术文章：概念关系和适用边界；不添加来源外结论 |
| g09 | long_text | 合成对比材料：至少 3 种方案及明确的比较维度 |
| g10 | long_text | 合成长文：主线夹有备注、例外、条件；保留限定语 |
| g11 | english | 英文说明转中文笔记，含 may / must / usually 的区别 |
| g12 | english | 英文操作步骤，命令与选项保持原样 |
| g13 | english | 中英混合术语说明，保留技术标识符 |
| g14 | english | 英文比较材料，准确保留比较对象及数值 |
| g15 | english | 英文故障说明，区分原因、现象与 workaround |
| g16 | code | Python 函数及输入输出例子；围栏、缩进、返回值正确 |
| g17 | code | SQL 查询及表结构说明；保留字段、过滤条件与排序 |
| g18 | code | PowerShell 命令步骤；保留参数、引号与路径示例 |
| g19 | code | JSON 配置与逐项解释；保留键和值，不写真实密钥 |
| g20 | code | 错误示例与修正版；不能将错误代码当推荐实现 |
| g21 | modify | seed 一篇笔记，明确 append 新小节，保留原文 |
| g22 | modify | seed 一篇笔记，明确 replace 一项过时值，保留其它章节 |
| g23 | modify | seed 两篇相近主题笔记，明确向指定文件追加，不能选错目标 |
| g24 | modify | seed 一层目录下笔记，明确 replace 指定内容，路径保持一致 |
| g25 | modify | seed 含代码笔记，明确 replace 更新函数签名，保留无关示例 |

对话类将完整多轮角色文本放进 `user`，本轮不新增多轮会话驱动器。长文每条至少 2,000 个 Unicode 字符，正文自洽且有实际信息，不能重复句子凑长度。长度仅是覆盖检查，不作为质量分数。所有材料自行编写，不需要联网抓取文章。

### 执行步骤

- [ ] 先创建覆盖完整性检查的 `tests/unit/test_v1_acceptance_cases.py`。核心测试如下；加载路径沿用现有项目测试习惯。

```python
import json
from collections import Counter
from pathlib import Path

from noteagent.prompt_eval.cases import load_cases


def test_v1_acceptance_set_is_complete_and_loadable():
    path = Path(__file__).resolve().parents[2] / "evals/prompt/v1_acceptance.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    assert len(rows) == 25
    assert {row["id"] for row in rows} == {f"g{i:02d}" for i in range(1, 26)}
    assert Counter(row["category"] for row in rows) == {
        "dialogue": 5, "long_text": 5, "english": 5, "code": 5, "modify": 5,
    }
    assert len({row["user"] for row in rows}) == 25
    for row in rows:
        assert row["kind"] == "quality"
        assert row["expect_propose"] is True
        assert row["expect_action"] in {"create", "append", "replace"}
        assert row["user"].strip()
        if row["category"] == "long_text":
            assert len(row["user"]) >= 2000
        if row["category"] == "modify":
            assert row["seed_files"]
    assert len(load_cases(path)) == 25
```

- [ ] 确认新测试因数据文件尚不存在而失败，随后撰写上述 25 条完整输入，不留占位材料。每条明确要求整理并保存笔记；modify 类提供完整 `seed_files` 原文及操作要求。
- [ ] 配置现有可用的 `expect_action`、`expect_tools_prefix`、`must_headings`、`must_substrings` 等。仅对用户明确要求的内容设置精确字串，不将合理转述误判为失败。不要给每条任意设同一工具顺序，先核对当前系统提示词契约。
- [ ] 编写 `v1_acceptance.md`，逐条记录输入类型、预期动作、目标文件（或合理文件名范围）、必须保留事实、禁止添加事实、代码/路径约束、是否允许合理改写及失败判定。modify 类必须列出不能被删除的原有内容。
- [ ] 运行新数据检查及现有 prompt_eval 测试，确认无需修改加载器或 CLI 即可运行；若确实需要工具改动，先用失败测试证明缺口，只做必要兼容扩展。
- [ ] 更新 `evals/prompt/README.md`，说明新集是 V1 生成覆盖验收，旧行为集和 v0.2 学习型质量集仍独立，不混算分数。

## 任务 3：执行测试、真实生成评测与结果归档

### 3.1 自动测试

- [ ] 执行下面的测试，分别记录命令、时间、退出码、通过/失败/跳过数；可用 `uv run pytest` 替代本机解释器路径。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_drafts.py tests/unit/test_chat_history.py tests/integration/test_retrieval_service.py -q
.\.venv\Scripts\python.exe -m pytest tests/unit/test_v1_acceptance_cases.py tests/unit/test_prompt_eval_run.py tests/unit/test_prompt_eval_score.py -q
.\.venv\Scripts\python.exe -m pytest tests -q
```

- [ ] 若临时目录权限导致 fixture 初始化失败，区分环境错误与产品断言失败。选取可写的全新绝对目录作为 `--basetemp`，先创建其父目录；pytest 可能清理该目录，绝不能指向用户目录或已有数据。仍失败则记录实际边界，不反复把相同环境错误报告为代码失败。
- [ ] 修复本次引入的测试回归。已有不相关失败记录来源和影响；不为全绿修改无关功能或旧期望。

### 3.2 真实模型生成与内容审查

- [ ] 固定当前代码版本、未提交差异、系统提示词、样例集、生成模型和可见模型参数，记录样例与 prompt 的 SHA-256。CLI 使用 `Settings` 的模型配置，不保证等于界面已激活 profile；必须记录实际运行模型，不能只抄 UI 名称。
- [ ] 先跑 g01、g16、g21 三条冒烟，确认普通生成、代码材料和已有笔记修改能执行。冒烟仅检查运行入口，不计作全量验收的额外样例。

```powershell
uv run python scripts/eval_notes.py --cases evals/prompt/v1_acceptance.jsonl --ids g01,g16,g21 --name v1-acceptance-smoke
```

- [ ] 使用同一配置完整运行 25 条一次，同时运行已有 20 条旧集作为行为/正文回归；保存 CLI 实际输出目录，不使用 `--force` 覆盖旧结果。

```powershell
uv run python scripts/eval_notes.py --cases evals/prompt/v1_acceptance.jsonl --name v1-acceptance-full
uv run python scripts/eval_notes.py --cases evals/prompt/cases.jsonl --name v1-acceptance-regression
```

- [ ] 逐条对照完整输入、seed、工具轨迹和生成草稿进行内容审查，填写配套清单中所有断言的实际结果。由 Claude 执行的检查标为“执行代理内容审查”，不是独立人工验收；引用输出片段或产物路径支撑结论。实际草稿非空、动作与目标正确、关键事实无明显遗漏、没有来源外关键结论、代码和标识符符合输入要求，才判该条通过。
- [ ] 自动评分仅作为辅助。没有执行语义 Judge 时，不得把 `semantic_completed=false` 写为语义通过，也不得用旧 v0.1 `total` 代替内容审查。无需为了 V1 引入新的 Judge 服务或追求 v0.2 加工高分。
- [ ] 首次全量结果必须保留。失败时记录运行错误、动作错误、目标错误、内容遗漏、事实增添、代码损坏等具体分类；区分旧失败和新回归。必要的定向复跑保存独立 run ID，不覆盖首次结果、不按最好结果取代分母。
- [ ] 本任务不扩大为 prompt 调优项目。若失败需要改提示词或生成策略，记录对应输入与输出，作为后续明确任务；不得暗改提示词后继续引用旧全量结果。

### 3.3 验收报告

- [ ] 创建 `docs/evaluations/v1-acceptance-report.md`，必须包括以下内容，并填写实际结果；未执行的写明“未执行”及原因，不填估计值。

| 报告部分 | 必需内容 |
|---|---|
| 范围与身份 | 日期、执行者、代码提交及未提交修改、Python/平台、模型、prompt 和样例哈希 |
| bug 修复 | 原因、修改路径、回归测试、数据库草稿恢复证据、部分写入限制 |
| 自动测试 | 命令、退出码、计数、失败栈摘要、环境限制、原始记录位置 |
| 样例覆盖 | 五类各 5 条；生成样例、旧行为题、重复运行分开计数 |
| 25 条明细 | ID、分类、预期/实际动作、预期/实际目标、非空正文、事实/代码审查、结论、结果链接 |
| 分组汇总 | 各类通过数/5、全量通过数/25、运行错误数；不排除失败后重算分母 |
| 旧集回归 | 行为结果与正文结果分别记录，和可比较历史配置的差异 |
| 失败与复跑 | 首次失败、原因、后续 run ID、是否解决、尚存风险 |
| 手动功能验收 | 用户负责，状态“待用户执行/反馈”；没有反馈不得标为通过 |
| 结论 | 自动化结果、生成覆盖结果、手动功能结果分别陈述，明确是否还有未完成项 |

- [ ] 为用户附一份简短手动测试清单即可，不代执行：创建后跨会话检索、追加、覆盖清旧、删除、拒绝不变、重启后历史与待审草稿恢复。每项初始状态均为“待用户测试”。
- [ ] 更新评测 README 的报告链接，并在路线图链接本报告。删除或更正“仍缺有效 RAG 查询集”的过时说法，引用既有 RAG 报告并标注其历史日期；本轮不重跑 RAG，也不把历史检索结果写成本轮实测。
- [ ] 将本计划每项勾选状态与报告保持一致，最终回复列出交付路径、真实执行结果、未完成项及需用户手动测试的内容。

## 完成条件与结论规则

1. 文件操作 `OSError` 后唯一待审草稿仍可从数据库读取；失败前未产生文件变更的场景能够再次审批成功，失败时不调用索引；拒绝、成功、索引失败语义不回归。
2. 25 条完整生成输入及逐条期望已落库，五类覆盖与现有加载器兼容检查通过，行为题不冒充生成样例。
3. 自动测试与真实模型评测均按实际执行情况留存。若凭据或环境阻塞，明确哪些产物已完成、哪些运行尚未完成，不能声称全部执行完成。
4. 只有 25 条均满足预先固定的 V1 判据时，报告才可写“本轮生成验收集通过”；否则写具体通过数和失败，不因报告已归档就判通过。
5. 用户的手动功能验收尚未反馈前，最多声明“本轮修复/自动化/生成评测的实际完成状态，手动功能待验”，不得声明 V1 整体验收完成。
