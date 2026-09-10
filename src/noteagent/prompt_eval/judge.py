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
    ReviewQuestionAssessment,
    SemanticEvidence,
)

_logger = logging.getLogger(__name__)

JUDGE_PROMPT_PATH = Path(__file__).with_name("prompts") / "learning_note_judge.txt"
JUDGE_MAX_ATTEMPTS = 3
_JSON_FENCE = re.compile(r"^\s*```json\s*(.*?)\s*```\s*$", re.IGNORECASE | re.DOTALL)
_RESULT_KEYS = frozenset(
    {"hard_gates", "dimensions", "evidence", "review_questions"}
)
_EVIDENCE_KEYS = frozenset((*HARD_GATE_ORDER, *SEMANTIC_DIMENSION_ORDER))
_EVIDENCE_ITEM_KEYS = frozenset({"source", "draft", "reason"})
_REVIEW_QUESTION_KEYS = frozenset(
    {"question", "answerable", "answer", "draft_evidence", "reason"}
)


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
    _reject_unexpected_keys(data, _RESULT_KEYS, "result")

    gates = _required_mapping(data, "hard_gates")
    dimensions = _required_mapping(data, "dimensions")
    evidence = _required_mapping(data, "evidence")
    _reject_unexpected_keys(gates, frozenset(HARD_GATE_ORDER), "hard_gates")
    _reject_unexpected_keys(
        dimensions, frozenset(SEMANTIC_DIMENSION_ORDER), "dimensions"
    )
    _reject_unexpected_keys(evidence, _EVIDENCE_KEYS, "evidence")
    review_questions = _required_value(data, "review_questions", "result")
    if not isinstance(review_questions, list):
        raise JudgeResultError("review_questions must be an array")

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

    parsed_evidence: dict[str, SemanticEvidence] = {}
    for name in (*HARD_GATE_ORDER, *SEMANTIC_DIMENSION_ORDER):
        item = _required_value(evidence, name, "evidence")
        if not isinstance(item, dict):
            raise JudgeResultError(f"evidence.{name} must be an object")
        _reject_unexpected_keys(
            item, _EVIDENCE_ITEM_KEYS, f"evidence.{name}"
        )
        parsed_evidence[name] = SemanticEvidence(
            source=_evidence_list(item, name, "source"),
            draft=_evidence_list(item, name, "draft"),
            reason=_evidence_reason(item, name),
        )
    parsed_review_questions = [
        _review_question(item, index)
        for index, item in enumerate(review_questions)
    ]
    return LearningNoteSemanticResult(
        hard_gates=parsed_gates,
        dimensions=parsed_dimensions,
        evidence=parsed_evidence,
        review_questions=parsed_review_questions,
    )


async def judge_learning_note(
    model,
    *,
    model_name: str,
    case: EvalCase,
    draft: dict,
    prompt_path: Path = JUDGE_PROMPT_PATH,
) -> LearningNoteSemanticResult:
    """Call the Judge and parse its response, retrying contract errors only."""
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
    last_contract_error: JudgeResultError | None = None
    for attempt in range(1, JUDGE_MAX_ATTEMPTS + 1):
        try:
            response = await model.ainvoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(
                        content=json.dumps(
                            request, ensure_ascii=False, separators=(",", ":")
                        )
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
                file_name=str(draft.get("file_name") or ""),
            )
            _validate_review_questions(
                result,
                expected=case.review_questions,
                draft=str(draft.get("content") or ""),
            )
        except JudgeResultError as exc:
            last_contract_error = exc
            _logger.warning(
                "Judge contract failed model=%s case_id=%s attempt=%s/%s error=%s",
                model_name,
                case.id,
                attempt,
                JUDGE_MAX_ATTEMPTS,
                exc,
            )
            if attempt < JUDGE_MAX_ATTEMPTS:
                continue
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            _logger.exception(
                "Judge failed model=%s case_id=%s elapsed_ms=%s",
                model_name,
                case.id,
                elapsed_ms,
            )
            raise
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
            "Judge end model=%s case_id=%s attempt=%s elapsed_ms=%s success=true",
            model_name,
            case.id,
            attempt,
            elapsed_ms,
        )
        return result
    raise last_contract_error or JudgeResultError("Judge returned no result")


def _validate_evidence_substrings(
    result: LearningNoteSemanticResult, *, source: str, draft: str, file_name: str
) -> None:
    """Require Judge evidence in source/body; retrievability may cite file name."""
    inputs = {"source": source, "draft": draft}
    for metric, evidence in result.evidence.items():
        for side, input_text in inputs.items():
            fragments = evidence.source if side == "source" else evidence.draft
            for index, fragment in enumerate(fragments):
                file_name_match = (
                    metric == "retrievable"
                    and side == "draft"
                    and fragment in file_name
                )
                if fragment not in input_text and not file_name_match:
                    raise JudgeResultError(
                        f"evidence.{metric}.{side}[{index}] is not an input substring"
                    )


def _validate_review_questions(
    result: LearningNoteSemanticResult, *, expected: list[str], draft: str
) -> None:
    """Match preset questions exactly and verify answer evidence against the draft."""
    actual = result.review_questions
    if len(actual) != len(expected):
        raise JudgeResultError("review_questions length mismatch")
    for index, (assessment, question) in enumerate(zip(actual, expected)):
        if assessment.question != question:
            raise JudgeResultError(
                f"review_questions[{index}].question mismatch"
            )
        for evidence_index, fragment in enumerate(assessment.draft_evidence):
            if fragment not in draft:
                raise JudgeResultError(
                    "review_questions"
                    f"[{index}].draft_evidence[{evidence_index}]"
                    " is not a draft substring"
                )


def _review_question(item: object, index: int) -> ReviewQuestionAssessment:
    """Parse one complete review-question assessment with conditional requirements."""
    path = f"review_questions[{index}]"
    if not isinstance(item, dict):
        raise JudgeResultError(f"{path} must be an object")
    _reject_unexpected_keys(item, _REVIEW_QUESTION_KEYS, path)
    question = _required_value(item, "question", path)
    answerable = _required_value(item, "answerable", path)
    answer = _required_value(item, "answer", path)
    evidence = _required_value(item, "draft_evidence", path)
    reason = _required_value(item, "reason", path)
    if not isinstance(question, str) or not question:
        raise JudgeResultError(f"{path}.question must be a non-empty string")
    if type(answerable) is not bool:
        raise JudgeResultError(f"{path}.answerable must be boolean")
    if not isinstance(answer, str):
        raise JudgeResultError(f"{path}.answer must be a string")
    if (
        not isinstance(evidence, list)
        or any(not isinstance(entry, str) or not entry for entry in evidence)
    ):
        raise JudgeResultError(f"{path}.draft_evidence must be a string array")
    if not isinstance(reason, str):
        raise JudgeResultError(f"{path}.reason must be a string")
    if answerable and not answer.strip():
        raise JudgeResultError(f"{path}.answer must be non-empty when answerable=true")
    if answerable and not evidence:
        raise JudgeResultError(
            f"{path}.draft_evidence must be non-empty when answerable=true"
        )
    if not answerable and not reason.strip():
        raise JudgeResultError(f"{path}.reason must be non-empty when answerable=false")
    return ReviewQuestionAssessment(
        question=question,
        answerable=answerable,
        answer=answer,
        draft_evidence=list(evidence),
        reason=reason,
    )


def _required_mapping(data: dict, name: str) -> dict:
    """Return one required object field or fail with its path."""
    value = _required_value(data, name, "result")
    if not isinstance(value, dict):
        raise JudgeResultError(f"{name} must be an object")
    return value


def _reject_unexpected_keys(
    data: dict, expected: frozenset[str], path: str
) -> None:
    """Reject one unknown key by structural path without exposing its value."""
    unexpected = sorted(set(data) - expected)
    if unexpected:
        raise JudgeResultError(f"{path} unexpected key: {unexpected[0]}")


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


def _evidence_reason(item: dict, name: str) -> str:
    """Validate one non-empty rationale for how evidence supports the score."""
    path = f"evidence.{name}.reason"
    value = _required_value(item, "reason", f"evidence.{name}")
    if not isinstance(value, str) or not value.strip():
        raise JudgeResultError(f"{path} must be a non-empty string")
    return value
