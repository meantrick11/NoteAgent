"""Learning-note Judge parsing and scoring contracts."""

import copy
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from noteagent.prompt_eval.cases import EvalCase
from noteagent.prompt_eval.judge import JudgeResultError, judge_learning_note, parse_judge_result
from noteagent.prompt_eval.score import LearningNoteSemanticResult, SemanticEvidence, score_note


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
    name: {
        "source": [f"source-{name}"],
        "draft": [f"draft-{name}"],
        "reason": f"reason-{name}",
    }
    for name in (*_GATES, *_DIMENSIONS)
}


def _semantic_evidence() -> dict[str, SemanticEvidence]:
    """Build typed semantic evidence for direct LearningNoteSemanticResult use."""
    return {
        name: SemanticEvidence(**item)
        for name, item in _EVIDENCE.items()
    }


def _payload(**overrides) -> dict:
    """Return one valid Judge payload with optional top-level replacements."""
    data = {
        "hard_gates": dict(_GATES),
        "dimensions": dict(_DIMENSIONS),
        "evidence": copy.deepcopy(_EVIDENCE),
        "review_questions": [],
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
    assert plain.evidence["faithful"].source == ["source-faithful"]
    assert plain.evidence["faithful"].reason == "reason-faithful"
    assert plain.review_questions == []


@pytest.mark.parametrize(
    "payload",
    [
        {"hard_gates": _GATES, "dimensions": _DIMENSIONS},
        {"hard_gates": _GATES, "dimensions": _DIMENSIONS, "evidence": _EVIDENCE},
        _payload(hard_gates={"task_alignment": True, "faithful": True}),
        _payload(dimensions={**_DIMENSIONS, "processing": 5}),
        _payload(evidence={**_EVIDENCE, "faithful": {"source": [], "draft": [], "reason": "x"}}),
        _payload(
            evidence={
                **_EVIDENCE,
                "faithful": {"source": ["source-faithful"], "draft": ["draft-faithful"]},
            }
        ),
        _payload(
            evidence={
                **_EVIDENCE,
                "faithful": {
                    "source": ["source-faithful"],
                    "draft": ["draft-faithful"],
                    "reason": "",
                },
            }
        ),
        _payload(review_questions=[{"question": "Q"}]),
        _payload(
            review_questions=[
                {
                    "question": "Q",
                    "answerable": True,
                    "answer": "",
                    "draft_evidence": [],
                    "reason": "",
                }
            ]
        ),
        _payload(
            review_questions=[
                {
                    "question": "Q",
                    "answerable": False,
                    "answer": "",
                    "draft_evidence": [],
                    "reason": "",
                }
            ]
        ),
    ],
)
def test_parse_judge_result_rejects_missing_or_invalid_fields(payload: dict):
    """Missing fields, out-of-range scores, and empty evidence fail explicitly."""
    with pytest.raises(JudgeResultError):
        parse_judge_result(json.dumps(payload))


@pytest.mark.parametrize(
    ("path", "expected_error"),
    [
        ("result", "result unexpected key: private_extra"),
        ("hard_gates", "hard_gates unexpected key: private_extra"),
        ("dimensions", "dimensions unexpected key: private_extra"),
        ("evidence", "evidence unexpected key: private_extra"),
        (
            "evidence.faithful",
            "evidence.faithful unexpected key: private_extra",
        ),
        (
            "review_questions[0]",
            "review_questions[0] unexpected key: private_extra",
        ),
    ],
)
def test_parse_judge_result_rejects_unknown_keys_without_values(
    path: str, expected_error: str
):
    """Every Judge object rejects extras while errors expose no private values."""
    data = copy.deepcopy(_payload())
    data["review_questions"] = [
        {
            "question": "私人测试问题",
            "answerable": True,
            "answer": "私人测试答案",
            "draft_evidence": ["私人草稿证据"],
            "reason": "",
        }
    ]
    target = data
    for part in path.split("."):
        if part == "result":
            continue
        if part == "review_questions[0]":
            target = data["review_questions"][0]
        else:
            target = target[part]
    target["private_extra"] = "绝不能出现在异常里的私人值"

    with pytest.raises(JudgeResultError) as caught:
        parse_judge_result(json.dumps(data, ensure_ascii=False))

    assert str(caught.value) == expected_error
    assert "绝不能出现在异常里的私人值" not in str(caught.value)
    assert "私人测试问题" not in str(caught.value)
    assert "私人测试答案" not in str(caught.value)


def test_parse_judge_result_requires_evidence_reason():
    """Every hard gate and dimension evidence object must include a non-empty reason."""
    data = _payload()
    del data["evidence"]["faithful"]["reason"]

    with pytest.raises(JudgeResultError) as caught:
        parse_judge_result(json.dumps(data))

    assert str(caught.value) == "missing field: evidence.faithful.reason"


def test_parse_judge_result_rejects_empty_evidence_reason():
    """Evidence reason must be a non-empty string even when gates fail."""
    data = _payload()
    data["evidence"]["faithful"]["reason"] = "   "

    with pytest.raises(JudgeResultError) as caught:
        parse_judge_result(json.dumps(data))

    assert str(caught.value) == "evidence.faithful.reason must be a non-empty string"


def test_parse_judge_result_keeps_clear_missing_field_path():
    """Exact-key validation preserves the existing explicit required-field error."""
    data = _payload()
    del data["hard_gates"]["faithful"]

    with pytest.raises(JudgeResultError) as caught:
        parse_judge_result(json.dumps(data))

    assert str(caught.value) == "missing field: hard_gates.faithful"


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
    assert result.semantic_completed is False
    assert result.total is None
    assert result.hard_gates == {}
    assert result.dimensions == {}


def test_learning_behavior_failure_without_judge_is_unqualified_and_incomplete():
    """Behavior failure rejects a learning run even when no Judge was available."""
    result = score_note(
        _case(expect_tools_prefix=["list_files"]),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="笔记",
    )

    assert result.behavior_pass is False
    assert result.qualified is False
    assert result.semantic_completed is False
    assert result.total is None
    assert result.hard_gates == {}
    assert result.dimensions == {}


def test_learning_note_without_judge_rejects_invalid_threshold_configuration():
    """Threshold errors are reported even when semantic evaluation did not run."""
    result = score_note(
        _case(quality_thresholds={"unknown": 3}),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="笔记",
    )

    assert result.qualified is False
    assert result.semantic_completed is False
    assert result.total is None
    assert any(
        "quality_thresholds unknown dimension 'unknown'" in item
        for item in result.behavior_evidence
    )


@pytest.mark.parametrize("failed_gate", list(_GATES))
def test_learning_note_fails_when_any_hard_gate_fails(failed_gate: str):
    """No quality dimension can compensate for one failed hard gate."""
    gates = dict(_GATES)
    gates[failed_gate] = False
    semantic = LearningNoteSemanticResult(gates, dict(_DIMENSIONS), _semantic_evidence())

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
    assert result.semantic_completed is True
    assert result.total is None


def test_learning_note_applies_only_configured_dimension_thresholds():
    """Configured thresholds determine qualification after all gates pass."""
    dimensions = dict(_DIMENSIONS)
    dimensions["processing"] = 2
    semantic = LearningNoteSemanticResult(_GATES, dimensions, _semantic_evidence())

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


def test_learning_note_requires_every_review_question_answerable():
    """One unanswerable preset review question makes an otherwise strong note fail."""
    assessment = {
        "question": "为什么？",
        "answerable": False,
        "answer": "",
        "draft_evidence": [],
        "reason": "草稿未说明原因",
    }
    semantic = parse_judge_result(
        json.dumps(_payload(review_questions=[assessment]), ensure_ascii=False)
    )

    result = score_note(
        _case(review_questions=["为什么？"]),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="笔记",
        semantic_result=semantic,
    )

    assert result.qualified is False
    assert result.review_questions_answered == 0
    assert result.review_questions_total == 1


def test_learning_note_rejects_missing_review_question_assessment():
    """A semantic result cannot qualify by omitting a configured review question."""
    semantic = parse_judge_result(json.dumps(_payload()))

    result = score_note(
        _case(review_questions=["为什么？"]),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="笔记",
        semantic_result=semantic,
    )

    assert result.qualified is False
    assert result.review_questions_total == 1


def test_learning_note_invalid_output_path_fails_behavior_gate():
    """A semantically strong note cannot pass with an unsafe draft path."""
    semantic = parse_judge_result(json.dumps(_payload()))

    result = score_note(
        _case(),
        proposed=True,
        tools=[],
        action="create",
        file_name="../Python.md",
        content="笔记",
        semantic_result=semantic,
    )

    assert result.behavior_pass is False
    assert result.qualified is False
    assert "路径不合法" in " ".join(result.behavior_evidence)


def test_learning_note_literal_diagnostics_do_not_override_semantic_judge():
    """Potentially noisy literal diagnostics stay auditable but do not veto semantics."""
    semantic = parse_judge_result(json.dumps(_payload()))

    result = score_note(
        _case(),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="草稿提到 /draft-only/path，但 Judge 已结合语义判定忠实。",
        semantic_result=semantic,
    )

    assert result.behavior_pass is True
    assert result.qualified is True
    literal = next(
        item for item in result.metrics if item.metric_id == "faithful.literals"
    )
    assert literal.score == 0


class ScriptedJudge:
    """Fake LangChain-compatible Judge with one asynchronous reply."""

    def __init__(self, content: str):
        self.content = content
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        return AIMessage(content=self.content)


async def test_judge_learning_note_uses_scripted_model():
    """Judge accepts evidence copied exactly from the source and draft."""
    evidence = {
        name: {
            "source": ["Source fact."],
            "draft": ["笔记"],
            "reason": "任务与草稿片段支持该判定",
        }
        for name in (*_GATES, *_DIMENSIONS)
    }
    model = ScriptedJudge(json.dumps(_payload(evidence=evidence)))

    result = await judge_learning_note(
        model,
        model_name="judge-scripted",
        case=_case(),
        draft={"file_name": "Python.md", "content": "笔记"},
        prompt_path=_PROMPT,
    )

    assert result.hard_gates == _GATES
    assert model.messages


async def test_retrievable_evidence_may_use_file_name():
    """Retrievability may cite the draft file name outside review-question evidence."""
    evidence = {
        name: {
            "source": ["Source fact."],
            "draft": ["笔记"],
            "reason": "任务与草稿片段支持该判定",
        }
        for name in (*_GATES, *_DIMENSIONS)
    }
    evidence["retrievable"]["draft"] = ["Python.md"]
    model = ScriptedJudge(json.dumps(_payload(evidence=evidence)))

    result = await judge_learning_note(
        model,
        model_name="judge-scripted",
        case=_case(),
        draft={"file_name": "Python.md", "content": "笔记"},
        prompt_path=_PROMPT,
    )

    assert result.evidence["retrievable"].draft == ["Python.md"]


async def test_judge_learning_note_validates_review_questions_in_order():
    """Every preset question is assessed in the original order from draft evidence."""
    questions = ["为什么？", "如何做？"]
    assessments = [
        {
            "question": questions[0],
            "answerable": True,
            "answer": "因为草稿说明了原因",
            "draft_evidence": ["草稿说明了原因"],
            "reason": "",
        },
        {
            "question": questions[1],
            "answerable": False,
            "answer": "",
            "draft_evidence": [],
            "reason": "草稿没有步骤",
        },
    ]
    evidence = {
        name: {
            "source": ["Source fact."],
            "draft": ["草稿说明了原因"],
            "reason": "草稿片段直接说明原因",
        }
        for name in (*_GATES, *_DIMENSIONS)
    }
    model = ScriptedJudge(
        json.dumps(_payload(evidence=evidence, review_questions=assessments))
    )

    result = await judge_learning_note(
        model,
        model_name="judge-scripted",
        case=_case(review_questions=questions),
        draft={"file_name": "Python.md", "content": "草稿说明了原因"},
        prompt_path=_PROMPT,
    )

    assert [item.question for item in result.review_questions] == questions
    assert result.review_questions[0].answerable is True
    assert result.review_questions[1].reason == "草稿没有步骤"


@pytest.mark.parametrize(
    ("assessments", "message"),
    [
        (
            [
                {
                    "question": "如何做？",
                    "answerable": True,
                    "answer": "有答案",
                    "draft_evidence": ["草稿证据"],
                    "reason": "",
                },
                {
                    "question": "为什么？",
                    "answerable": True,
                    "answer": "有答案",
                    "draft_evidence": ["草稿证据"],
                    "reason": "",
                },
            ],
            "question mismatch",
        ),
        (
            [
                {
                    "question": "为什么？",
                    "answerable": True,
                    "answer": "有答案",
                    "draft_evidence": ["不在草稿里"],
                    "reason": "",
                },
                {
                    "question": "如何做？",
                    "answerable": False,
                    "answer": "",
                    "draft_evidence": [],
                    "reason": "无步骤",
                },
            ],
            r"review_questions\[0\]\.draft_evidence\[0\]",
        ),
    ],
)
async def test_judge_learning_note_rejects_review_question_contract_errors(
    assessments: list[dict], message: str
):
    """Wrong order and non-draft review evidence fail with an explicit field path."""
    evidence = {
        name: {
            "source": ["Source fact."],
            "draft": ["草稿证据"],
            "reason": "草稿证据支持判定",
        }
        for name in (*_GATES, *_DIMENSIONS)
    }
    model = ScriptedJudge(
        json.dumps(_payload(evidence=evidence, review_questions=assessments))
    )

    with pytest.raises(JudgeResultError, match=message):
        await judge_learning_note(
            model,
            model_name="judge-scripted",
            case=_case(review_questions=["为什么？", "如何做？"]),
            draft={"file_name": "Python.md", "content": "草稿证据"},
            prompt_path=_PROMPT,
        )


@pytest.mark.parametrize(
    ("expected_questions", "assessments", "expected_error"),
    [
        (
            ["私人问题甲"],
            [],
            "review_questions length mismatch",
        ),
        (
            ["私人问题甲"],
            [
                {
                    "question": "私人问题乙",
                    "answerable": True,
                    "answer": "私人答案",
                    "draft_evidence": ["草稿证据"],
                    "reason": "",
                }
            ],
            "review_questions[0].question mismatch",
        ),
    ],
)
async def test_review_question_mismatch_errors_do_not_leak_text(
    expected_questions: list[str],
    assessments: list[dict],
    expected_error: str,
):
    """Question count and text mismatches expose only a structural error path."""
    evidence = {
        name: {
            "source": ["Source fact."],
            "draft": ["草稿证据"],
            "reason": "草稿证据支持判定",
        }
        for name in (*_GATES, *_DIMENSIONS)
    }
    model = ScriptedJudge(
        json.dumps(
            _payload(evidence=evidence, review_questions=assessments),
            ensure_ascii=False,
        )
    )

    with pytest.raises(JudgeResultError) as caught:
        await judge_learning_note(
            model,
            model_name="judge-scripted",
            case=_case(review_questions=expected_questions),
            draft={"file_name": "Python.md", "content": "草稿证据"},
            prompt_path=_PROMPT,
        )

    error = str(caught.value)
    assert error == expected_error
    assert "私人问题甲" not in error
    assert "私人问题乙" not in error
    assert "私人答案" not in error


async def test_judge_learning_note_requires_empty_assessments_without_questions():
    """A case with no preset questions accepts only an empty assessment array."""
    evidence = {
        name: {
            "source": ["Source fact."],
            "draft": ["笔记"],
            "reason": "任务与草稿片段支持该判定",
        }
        for name in (*_GATES, *_DIMENSIONS)
    }
    model = ScriptedJudge(
        json.dumps(
            _payload(
                evidence=evidence,
                review_questions=[
                    {
                        "question": "额外问题",
                        "answerable": True,
                        "answer": "答案",
                        "draft_evidence": ["笔记"],
                        "reason": "",
                    }
                ],
            )
        )
    )

    with pytest.raises(JudgeResultError, match="review_questions length"):
        await judge_learning_note(
            model,
            model_name="judge-scripted",
            case=_case(),
            draft={"file_name": "Python.md", "content": "笔记"},
            prompt_path=_PROMPT,
        )


async def test_judge_learning_note_rejects_generic_unverifiable_evidence():
    """Generic Judge prose not present in either input fails at its evidence path."""
    model = ScriptedJudge(json.dumps(_payload()))

    with pytest.raises(
        JudgeResultError,
        match=r"evidence\.task_alignment\.source\[0\]",
    ):
        await judge_learning_note(
            model,
            model_name="judge-scripted",
            case=_case(),
            draft={"file_name": "Python.md", "content": "笔记"},
            prompt_path=_PROMPT,
        )


@pytest.mark.parametrize(
    ("thresholds", "expected_error"),
    [
        ({"unknown": 3}, "unknown dimension 'unknown'"),
        ({"structure": "3"}, "structure must be an integer"),
        ({"structure": 5}, "structure must be from 0 to 4"),
    ],
)
def test_learning_note_invalid_threshold_is_reported_without_raising(
    thresholds: dict, expected_error: str
):
    """Invalid quality threshold configuration makes qualification false."""
    semantic = LearningNoteSemanticResult(_GATES, dict(_DIMENSIONS), _semantic_evidence())

    result = score_note(
        _case(quality_thresholds=thresholds),
        proposed=True,
        tools=[],
        action="create",
        file_name="Python.md",
        content="笔记",
        semantic_result=semantic,
    )

    assert result.qualified is False
    assert result.semantic_completed is True
    assert any(expected_error in item for item in result.behavior_evidence)
