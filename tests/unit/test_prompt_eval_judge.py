"""Learning-note Judge parsing and scoring contracts."""

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from noteagent.prompt_eval.cases import EvalCase
from noteagent.prompt_eval.judge import JudgeResultError, judge_learning_note, parse_judge_result
from noteagent.prompt_eval.score import LearningNoteSemanticResult, score_note


_PROMPT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "noteagent"
    / "prompt_eval"
    / "prompts"
    / "learning_note_judge.txt"
)
_GATES = {"task_alignment": True, "faithful": True, "complete": True}
_DIMENSIONS = {
    "structure": 3,
    "fluent": 4,
    "form": 3,
    "retrievable": 3,
    "processing": 3,
}
_EVIDENCE = {
    name: {"source": [f"source-{name}"], "draft": [f"draft-{name}"]}
    for name in (*_GATES, *_DIMENSIONS)
}


def _payload(**overrides) -> dict:
    """Return one valid Judge payload with optional top-level replacements."""
    data = {
        "hard_gates": dict(_GATES),
        "dimensions": dict(_DIMENSIONS),
        "evidence": dict(_EVIDENCE),
    }
    data.update(overrides)
    return data


def _case(**overrides) -> EvalCase:
    """Build a minimal learning-note case."""
    data = {
        "id": "l-test",
        "kind": "quality",
        "user": "整理成中文学习笔记。\n\nSource fact.",
        "expect_propose": True,
        "task_mode": "learning_note",
        "quality_thresholds": {"structure": 3, "processing": 3},
    }
    data.update(overrides)
    return EvalCase(**data)


def test_parse_judge_result_accepts_strict_json_and_json_fence():
    """Strict JSON and one json Markdown fence parse to the same contract."""
    raw = json.dumps(_payload(), ensure_ascii=False)

    plain = parse_judge_result(raw)
    fenced = parse_judge_result(f"```json\n{raw}\n```")

    assert plain == fenced
    assert plain.hard_gates == _GATES
    assert plain.dimensions == _DIMENSIONS
    assert plain.evidence["faithful"]["source"] == ["source-faithful"]


@pytest.mark.parametrize(
    "payload",
    [
        {"hard_gates": _GATES, "dimensions": _DIMENSIONS},
        _payload(hard_gates={"task_alignment": True, "faithful": True}),
        _payload(dimensions={**_DIMENSIONS, "processing": 5}),
        _payload(evidence={**_EVIDENCE, "faithful": {"source": [], "draft": []}}),
    ],
)
def test_parse_judge_result_rejects_missing_or_invalid_fields(payload: dict):
    """Missing fields, out-of-range scores, and empty evidence fail explicitly."""
    with pytest.raises(JudgeResultError):
        parse_judge_result(json.dumps(payload))


def test_learning_note_without_judge_is_incomplete_not_behavior_failure():
    """A generated learning note without semantics has no misleading total."""
    result = score_note(
        _case(),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="笔记",
    )

    assert result.behavior_pass is True
    assert result.qualified is None
    assert result.total is None
    assert result.hard_gates == {}
    assert result.dimensions == {}


@pytest.mark.parametrize("failed_gate", list(_GATES))
def test_learning_note_fails_when_any_hard_gate_fails(failed_gate: str):
    """No quality dimension can compensate for one failed hard gate."""
    gates = dict(_GATES)
    gates[failed_gate] = False
    semantic = LearningNoteSemanticResult(gates, dict(_DIMENSIONS), dict(_EVIDENCE))

    result = score_note(
        _case(),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="笔记",
        semantic_result=semantic,
    )

    assert result.qualified is False
    assert result.total is None


def test_learning_note_applies_only_configured_dimension_thresholds():
    """Configured thresholds determine qualification after all gates pass."""
    dimensions = dict(_DIMENSIONS)
    dimensions["processing"] = 2
    semantic = LearningNoteSemanticResult(_GATES, dimensions, _EVIDENCE)

    failed = score_note(
        _case(),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="笔记",
        semantic_result=semantic,
    )
    passed = score_note(
        _case(quality_thresholds={"structure": 3}),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="笔记",
        semantic_result=semantic,
    )

    assert failed.qualified is False
    assert passed.qualified is True


class ScriptedJudge:
    """Fake LangChain-compatible Judge with one asynchronous reply."""

    def __init__(self, content: str):
        self.content = content
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return AIMessage(content=self.content)


async def test_judge_learning_note_uses_scripted_model():
    """Judge performs one independent model call and returns parsed semantics."""
    model = ScriptedJudge(json.dumps(_payload()))

    result = await judge_learning_note(
        model,
        model_name="judge-scripted",
        case=_case(),
        draft={"file_name": "Python.md", "content": "笔记"},
        prompt_path=_PROMPT,
    )

    assert result.hard_gates == _GATES
    assert model.messages
