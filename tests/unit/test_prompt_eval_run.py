"""Prompt eval runner without network: scripted ChatAgent + report files."""

import json
from datetime import datetime
from pathlib import Path

from langchain_core.messages import AIMessage

from noteagent.bootstrap.settings import Settings
from noteagent.notes.repository import FileNoteRepository
from noteagent.prompt_eval.cases import EvalCase, load_cases
from noteagent.prompt_eval.report import case_filename, result_dest, write_stage
from noteagent.prompt_eval.run import CaseRun, ToolHop, build_eval_agent, run_case, seed_notes
from noteagent.prompt_eval.score import RUBRIC_VERSION, score_note


class ScriptedModel:
    """Fake model: bind_tools returns self; astream pops a scripted reply."""

    def __init__(self, replies):
        self.replies = list(replies)

    def bind_tools(self, tools):
        return self

    async def astream(self, messages, config=None):
        yield self.replies.pop(0)

    def invoke(self, messages):
        return AIMessage(content="SUMCHUNK")

_CASES = Path(__file__).resolve().parents[2] / "evals" / "prompt" / "cases.jsonl"
_PROMPT = Path(__file__).resolve().parents[2] / "src" / "noteagent" / "chat" / "prompts" / "system.txt"


def _settings() -> Settings:
    return Settings(deepseek_api_key="x", database_url="sqlite:///:memory:")


async def test_run_case_scripted_propose(tmp_path: Path):
    case = load_cases(_CASES, ["b02"])[0]
    model = ScriptedModel(
        [
            AIMessage(content="", tool_calls=[{"name": "list_files", "id": "c1", "args": {}}]),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "propose_note",
                        "id": "c2",
                        "args": {
                            "action": "create",
                            "file_name": "For.md",
                            "content": "Python 的 for 循环按可迭代对象逐项取值。",
                            "reason": "new",
                            "similar": "",
                        },
                    }
                ],
            ),
            AIMessage(content="已提交草稿"),
        ]
    )
    agent, notes, history, drafts = build_eval_agent(
        tmp_path / "notes",
        model=model,
        prompt_path=_PROMPT,
        settings=_settings(),
    )
    run = await run_case(
        case, seq=1, agent=agent, notes=notes, history=history, drafts=drafts
    )
    assert run.draft is not None
    assert run.draft["file_name"] == "For.md"
    assert [hop.name for hop in run.tools] == ["list_files", "propose_note"]
    assert run.score.behavior_pass is True
    assert run.assistant_final == "已提交草稿"


async def test_seed_files_and_behavior_search(tmp_path: Path):
    case = load_cases(_CASES, ["b04"])[0]
    assert "Python.md" in case.seed_files
    model = ScriptedModel(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_relative_from_chromadb",
                        "id": "c1",
                        "args": {"query": "argv"},
                    }
                ],
            ),
            AIMessage(content="以前笔记说参数在 sys.argv。"),
        ]
    )
    agent, notes, history, drafts = build_eval_agent(
        tmp_path / "notes",
        model=model,
        prompt_path=_PROMPT,
        settings=_settings(),
    )
    run = await run_case(
        case, seq=4, agent=agent, notes=notes, history=history, drafts=drafts
    )
    assert notes.exists("Python.md")
    assert "argv" in notes.read("Python.md")
    assert [hop.name for hop in run.tools] == ["search_relative_from_chromadb"]
    assert run.draft is None
    assert run.score.behavior_pass is True
    assert run.score.total is None


def test_write_stage_layout(tmp_path: Path):
    case = EvalCase(
        id="n00",
        kind="quality",
        user="记下来：hi",
        expect_propose=True,
        expect_tools_prefix=["list_files"],
        style="faithful_paragraphs",
    )
    score = score_note(
        case,
        proposed=True,
        tools=["list_files"],
        action="create",
        file_name="Hi.md",
        content="hi",
    )

    run = CaseRun(
        seq=1,
        case=case,
        score=score,
        tools=[ToolHop(name="list_files", arguments="{}", output_preview="[]", status="ok")],
        draft={"action": "create", "file_name": "Hi.md", "content": "hi", "reason": "x"},
        assistant_final="ok",
    )
    dest = tmp_path / "v8-test"
    write_stage(
        dest,
        prompt_text="ROLE",
        config={
            "rubric_version": RUBRIC_VERSION,
            "chat_model": "deepseek-v4-flash",
            "prompt_sha256": "abc",
            "prompt_path": "src/noteagent/chat/prompts/system.txt",
            "cases_path": "evals/prompt/cases.jsonl",
            "case_filter": ["n00"],
            "label": "v8-test",
            "started_at": "t0",
            "finished_at": "t1",
            "case_ids": {"n00": "n00.md"},
        },
        runs=[run],
    )
    assert (dest / "system.txt").read_text(encoding="utf-8") == "ROLE"
    assert (dest / "config.json").is_file()
    index = json.loads((dest / "index.json").read_text(encoding="utf-8"))
    assert index["cases_path"] == "evals/prompt/cases.jsonl"
    assert index["case_filter"] == ["n00"]
    assert index["cases"][0]["file"] == "n00.md"
    md = (dest / case_filename("n00")).read_text(encoding="utf-8")
    assert md.startswith("# n00")
    assert "evals/prompt/cases.jsonl" in md
    assert "## 7. 草稿" in md
    assert "hi" in md


def test_result_dest_nests_dataset_and_ids(tmp_path: Path):
    dest = result_dest(
        tmp_path / "results",
        cases_path=Path("evals/prompt/cases.jsonl"),
        ids=["b06", "n05"],
        label="v8-smoke",
        when=datetime(2026, 9, 6, 19, 26, 15),
    )
    assert dest == (tmp_path / "results" / "cases" / "v8-smoke_b06-n05_20260906-192615").resolve()
    unlabeled = result_dest(
        tmp_path / "results",
        cases_path=Path("evals/prompt/cases.jsonl"),
        ids=None,
        label=None,
        when=datetime(2026, 9, 6, 19, 26, 15),
    )
    assert unlabeled.name == "all_20260906-192615"


def test_load_cases_count_and_seeds():
    cases = load_cases(_CASES)
    assert len(cases) >= 20
    by_id = {item.id: item for item in cases}
    assert by_id["n07"].must_anchors
    assert by_id["b04"].seed_files["Python.md"]
    assert by_id["b05"].seed_files["Python.md"]
    assert by_id["b06"].seed_files["GIL.md"]


def test_seed_notes_overwrites_create_stub(tmp_path: Path):
    notes = FileNoteRepository(tmp_path)
    seed_notes(notes, {"GIL.md": "# GIL\n\nargv 在这里。\n"})
    text = notes.read("GIL.md")
    assert text.startswith("# GIL")
    assert "argv" in text
