"""Executable learning-note Judge calibration contracts without network access."""

import json
from pathlib import Path

from langchain_core.messages import AIMessage

from noteagent.prompt_eval.calibration import calibrate_learning_note


_ROOT = Path(__file__).resolve().parents[2]
_CASES = _ROOT / "evals" / "prompt" / "learning_notes.jsonl"
_FIXTURES = _ROOT / "evals" / "prompt" / "fixtures" / "learning_notes"
_PROMPT = (
    _ROOT
    / "src"
    / "noteagent"
    / "prompt_eval"
    / "prompts"
    / "learning_note_judge.txt"
)
_NAMES = ("good", "literal", "omitted", "hallucinated")


def _payload(
    *,
    gates: dict[str, bool] | None = None,
    dimensions: dict[str, int] | None = None,
    draft_evidence: str,
) -> dict:
    """Build one strict result whose evidence occurs in the fixed inputs."""
    hard_gates = gates or {
        "task_alignment": True,
        "faithful": True,
        "complete": True,
    }
    scores = dimensions or {
        "structure": 3,
        "fluent": 3,
        "form": 3,
        "retrievable": 3,
        "processing": 3,
    }
    evidence = {
        name: {"source": ["Python"], "draft": [draft_evidence]}
        for name in (*hard_gates, *scores)
    }
    return {"hard_gates": hard_gates, "dimensions": scores, "evidence": evidence}


def _passing_payloads() -> dict[str, dict]:
    """Return four distinct semantic outcomes satisfying the calibration contract."""
    return {
        "good": _payload(
            dimensions={
                "structure": 4,
                "fluent": 4,
                "form": 4,
                "retrievable": 4,
                "processing": 4,
            },
            draft_evidence="Python",
        ),
        "literal": _payload(
            dimensions={
                "structure": 3,
                "fluent": 3,
                "form": 3,
                "retrievable": 3,
                "processing": 1,
            },
            draft_evidence="Python",
        ),
        "omitted": _payload(
            gates={"task_alignment": True, "faithful": True, "complete": False},
            draft_evidence="Python",
        ),
        "hallucinated": _payload(
            gates={"task_alignment": True, "faithful": False, "complete": True},
            draft_evidence="Python",
        ),
    }


class ScriptedJudge:
    """Return a candidate-specific reply while recording every Judge request."""

    def __init__(self, payloads: dict[str, dict | str]):
        self.payloads = payloads
        self.calls: list[str] = []

    async def ainvoke(self, messages):
        request = json.loads(messages[-1].content)
        content = request["draft"]["content"]
        name = next(
            fixture_name
            for fixture_name in _NAMES
            if content == (_FIXTURES / f"{fixture_name}.md").read_text(encoding="utf-8")
        )
        self.calls.append(name)
        reply = self.payloads[name]
        return AIMessage(content=reply if isinstance(reply, str) else json.dumps(reply))


async def test_calibration_calls_all_candidates_and_passes_contract():
    """All four fixed candidates reach Judge and satisfy the expected distinctions."""
    model = ScriptedJudge(_passing_payloads())

    result = await calibrate_learning_note(
        case_path=_CASES,
        case_id="l01",
        fixtures_dir=_FIXTURES,
        judge_model=model,
        judge_model_name="judge-scripted",
        judge_prompt_path=_PROMPT,
    )

    assert model.calls == list(_NAMES)
    assert result["pass"] is True
    assert result["errors"] == []
    assert result["contracts"] == {
        "good_qualified": True,
        "literal_hard_gates": True,
        "literal_unqualified": True,
        "literal_processing_below_threshold": True,
        "omitted_incomplete": True,
        "hallucinated_unfaithful": True,
        "good_dimension_sum_gt_literal": True,
    }


async def test_calibration_reports_bad_order_and_hard_gate():
    """Contract violations fail calibration with explicit errors."""
    payloads = _passing_payloads()
    payloads["good"] = _payload(
        gates={"task_alignment": True, "faithful": False, "complete": True},
        dimensions={name: 1 for name in ("structure", "fluent", "form", "retrievable", "processing")},
        draft_evidence="Python",
    )
    model = ScriptedJudge(payloads)

    result = await calibrate_learning_note(
        case_path=_CASES,
        case_id="l01",
        fixtures_dir=_FIXTURES,
        judge_model=model,
        judge_model_name="judge-scripted",
        judge_prompt_path=_PROMPT,
    )

    assert model.calls == list(_NAMES)
    assert result["pass"] is False
    assert result["contracts"]["good_qualified"] is False
    assert result["contracts"]["good_dimension_sum_gt_literal"] is False
    assert result["errors"]


async def test_calibration_continues_after_one_judge_parse_failure():
    """One malformed Judge reply is attached to its candidate without stopping later calls."""
    payloads: dict[str, dict | str] = _passing_payloads()
    payloads["literal"] = "not-json"
    model = ScriptedJudge(payloads)

    result = await calibrate_learning_note(
        case_path=_CASES,
        case_id="l01",
        fixtures_dir=_FIXTURES,
        judge_model=model,
        judge_model_name="judge-scripted",
        judge_prompt_path=_PROMPT,
    )

    assert model.calls == list(_NAMES)
    assert result["pass"] is False
    assert "invalid Judge JSON" in result["candidates"]["literal"]["error"]
    assert result["candidates"]["hallucinated"]["error"] is None
