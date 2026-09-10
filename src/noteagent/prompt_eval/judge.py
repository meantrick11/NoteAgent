"""Independent semantic Judge call and strict learning-note result parsing."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from noteagent.prompt_eval.cases import EvalCase
from noteagent.prompt_eval.score import (
    HARD_GATE_ORDER,
    SEMANTIC_DIMENSION_ORDER,
    LearningNoteSemanticResult,
)

_logger = logging.getLogger(__name__)

JUDGE_PROMPT_PATH = Path(__file__).with_name("prompts") / "learning_note_judge.txt"
_JSON_FENCE = re.compile(r"^\s*```json\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)


class JudgeResultError(ValueError):
    """Raised when a Judge response violates the semantic result contract."""


def judge_prompt_sha256(prompt_path: Path = JUDGE_PROMPT_PATH) -> str:
    """Return the configured Judge prompt hash for reproducible reports."""
    text = prompt_path.read_text(encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_judge_result(raw: str) -> LearningNoteSemanticResult:
    """Parse strict JSON, allowing only an optional outer ```json fence."""
    text = raw.strip()
    fenced = _JSON_FENCE.fullmatch(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise JudgeResultError(f"invalid Judge JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise JudgeResultError("Judge result must be a JSON object")

    gates = _required_mapping(data, "hard_gates")
    dimensions = _required_mapping(data, "dimensions")
    evidence = _required_mapping(data, "evidence")

    parsed_gates: dict[str, bool] = {}
    for name in HARD_GATE_ORDER:
        value = _required_value(gates, name, "hard_gates")
        if type(value) is not bool:
            raise JudgeResultError(f"hard_gates.{name} must be boolean")
        parsed_gates[name] = value

    parsed_dimensions: dict[str, int] = {}
    for name in SEMANTIC_DIMENSION_ORDER:
        value = _required_value(dimensions, name, "dimensions")
        if type(value) is not int or not 0 <= value <= 4:
            raise JudgeResultError(f"dimensions.{name} must be an integer from 0 to 4")
        parsed_dimensions[name] = value

    parsed_evidence: dict[str, dict[str, list[str]]] = {}
    for name in (*HARD_GATE_ORDER, *SEMANTIC_DIMENSION_ORDER):
        item = _required_value(evidence, name, "evidence")
        if not isinstance(item, dict):
            raise JudgeResultError(f"evidence.{name} must be an object")
        parsed_evidence[name] = {
            "source": _evidence_list(item, name, "source"),
            "draft": _evidence_list(item, name, "draft"),
        }
    return LearningNoteSemanticResult(
        hard_gates=parsed_gates,
        dimensions=parsed_dimensions,
        evidence=parsed_evidence,
    )


async def judge_learning_note(
    model,
    *,
    model_name: str,
    case: EvalCase,
    draft: dict,
    prompt_path: Path = JUDGE_PROMPT_PATH,
) -> LearningNoteSemanticResult:
    """Call the Judge once and parse its response without logging private text."""
    started = time.perf_counter()
    _logger.info("Judge start model=%s case_id=%s", model_name, case.id)
    prompt = prompt_path.read_text(encoding="utf-8")
    request = {
        "case_id": case.id,
        "task": case.user,
        "output_language": case.output_language,
        "must_concepts": case.must_concepts,
        "must_relations": case.must_relations,
        "must_preserve": case.must_preserve,
        "forbidden_claims": case.forbidden_claims,
        "review_questions": case.review_questions,
        "draft": {
            "file_name": draft.get("file_name"),
            "content": draft.get("content"),
        },
    }
    try:
        response = await model.ainvoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(
                    content=json.dumps(request, ensure_ascii=False, separators=(",", ":"))
                ),
            ]
        )
        content = getattr(response, "content", None)
        if not isinstance(content, str):
            raise JudgeResultError("Judge response content must be text")
        result = parse_judge_result(content)
        _validate_evidence_substrings(
            result,
            source=case.user,
            draft=str(draft.get("content") or ""),
        )
    except Exception:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        _logger.exception(
            "Judge failed model=%s case_id=%s elapsed_ms=%s",
            model_name,
            case.id,
            elapsed_ms,
        )
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    _logger.info(
        "Judge end model=%s case_id=%s elapsed_ms=%s success=true",
        model_name,
        case.id,
        elapsed_ms,
    )
    return result


def _validate_evidence_substrings(
    result: LearningNoteSemanticResult, *, source: str, draft: str
) -> None:
    """Require every Judge evidence fragment to occur verbatim in its input."""
    inputs = {"source": source, "draft": draft}
    for metric, evidence in result.evidence.items():
        for side, input_text in inputs.items():
            for index, fragment in enumerate(evidence[side]):
                if fragment not in input_text:
                    raise JudgeResultError(
                        f"evidence.{metric}.{side}[{index}] is not an input substring"
                    )


def _required_mapping(data: dict, name: str) -> dict:
    """Return one required object field or fail with its path."""
    value = _required_value(data, name, "result")
    if not isinstance(value, dict):
        raise JudgeResultError(f"{name} must be an object")
    return value


def _required_value(data: dict, name: str, parent: str):
    """Return one required field without inventing a default."""
    if name not in data:
        raise JudgeResultError(f"missing field: {parent}.{name}")
    return data[name]


def _evidence_list(item: dict, name: str, side: str) -> list[str]:
    """Validate concrete non-empty source or draft evidence strings."""
    value = _required_value(item, side, f"evidence.{name}")
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(entry, str) or not entry.strip() for entry in value)
    ):
        raise JudgeResultError(
            f"evidence.{name}.{side} must be a non-empty string array"
        )
    return list(value)
