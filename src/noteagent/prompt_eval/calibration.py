"""Executable calibration of the learning-note Judge against fixed candidates."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from noteagent.prompt_eval.cases import load_cases
from noteagent.prompt_eval.judge import JUDGE_PROMPT_PATH, judge_learning_note
from noteagent.prompt_eval.score import HARD_GATE_ORDER, SEMANTIC_DIMENSION_ORDER, score_note

_logger = logging.getLogger(__name__)

CANDIDATE_NAMES = ("good", "literal", "omitted", "hallucinated")


async def calibrate_learning_note(
    *,
    case_path: Path,
    case_id: str,
    fixtures_dir: Path,
    judge_model,
    judge_model_name: str,
    judge_prompt_path: Path = JUDGE_PROMPT_PATH,
) -> dict:
    """Judge all fixed candidates, score them, and evaluate calibration contracts."""
    case = load_cases(case_path, [case_id])[0]
    candidates: dict[str, dict] = {}
    _logger.info(
        "Judge calibration start model=%s case_id=%s candidates=%d",
        judge_model_name,
        case.id,
        len(CANDIDATE_NAMES),
    )
    for name in CANDIDATE_NAMES:
        fixture_path = fixtures_dir / f"{name}.md"
        candidate = {
            "fixture": fixture_path.name,
            "fixture_sha256": None,
            "hard_gates": {},
            "dimensions": {},
            "qualified": False,
            "evidence": {},
            "error": None,
        }
        try:
            content = fixture_path.read_text(encoding="utf-8")
            candidate["fixture_sha256"] = hashlib.sha256(
                fixture_path.read_bytes()
            ).hexdigest()
            semantic = await judge_learning_note(
                judge_model,
                model_name=judge_model_name,
                case=case,
                draft={"file_name": fixture_path.name, "content": content},
                prompt_path=judge_prompt_path,
            )
            score = score_note(
                case,
                proposed=True,
                tools=case.expect_tools_prefix,
                action=_candidate_action(case.expect_action),
                file_name=fixture_path.name,
                content=content,
                semantic_result=semantic,
            )
            candidate.update(
                hard_gates=score.hard_gates,
                dimensions=score.dimensions,
                qualified=score.qualified,
                evidence=score.semantic_evidence,
            )
        except Exception as exc:
            candidate["error"] = str(exc)
            _logger.warning(
                "Judge calibration candidate failed model=%s case_id=%s candidate=%s error=%s",
                judge_model_name,
                case.id,
                name,
                exc,
            )
        candidates[name] = candidate

    contracts = _evaluate_contracts(candidates, case.quality_thresholds)
    errors = [
        f"{name}: {candidate['error']}"
        for name, candidate in candidates.items()
        if candidate["error"] is not None
    ]
    errors.extend(
        f"contract failed: {name}" for name, passed in contracts.items() if not passed
    )
    passed = not errors
    _logger.info(
        "Judge calibration end model=%s case_id=%s pass=%s errors=%d",
        judge_model_name,
        case.id,
        passed,
        len(errors),
    )
    return {
        "case_id": case.id,
        "candidates": candidates,
        "contracts": contracts,
        "pass": passed,
        "errors": errors,
    }


def _candidate_action(expected: str | None) -> str:
    """Choose one valid non-mutating scoring action for fixture drafts."""
    if expected in ("append", "create", "replace"):
        return expected
    return "create"


def _evaluate_contracts(candidates: dict[str, dict], thresholds: dict[str, int]) -> dict:
    """Return each fixed calibration assertion as a named boolean."""
    good = candidates["good"]
    literal = candidates["literal"]
    omitted = candidates["omitted"]
    hallucinated = candidates["hallucinated"]
    processing_threshold = thresholds.get("processing")
    return {
        "good_qualified": good["error"] is None and good["qualified"] is True,
        "literal_hard_gates": literal["error"] is None
        and all(literal["hard_gates"].get(name) is True for name in HARD_GATE_ORDER),
        "literal_unqualified": literal["error"] is None
        and literal["qualified"] is False,
        "literal_processing_below_threshold": literal["error"] is None
        and type(processing_threshold) is int
        and literal["dimensions"].get("processing", 5) < processing_threshold,
        "omitted_incomplete": omitted["error"] is None
        and omitted["hard_gates"].get("complete") is False,
        "hallucinated_unfaithful": hallucinated["error"] is None
        and hallucinated["hard_gates"].get("faithful") is False,
        "good_structure_gt_literal": _dimension_gt(good, literal, "structure"),
        "good_fluent_gt_literal": _dimension_gt(good, literal, "fluent"),
        "good_processing_gt_literal": _dimension_gt(good, literal, "processing"),
        "good_dimension_sum_gt_literal": good["error"] is None
        and literal["error"] is None
        and _dimension_sum(good) > _dimension_sum(literal),
    }


def _dimension_gt(good: dict, literal: dict, name: str) -> bool:
    """Require one good-candidate dimension to strictly exceed literal."""
    return (
        good["error"] is None
        and literal["error"] is None
        and good["dimensions"].get(name, -1) > literal["dimensions"].get(name, -1)
    )


def _dimension_sum(candidate: dict) -> int:
    """Sum the five semantic dimensions for one successfully judged candidate."""
    return sum(candidate["dimensions"].get(name, 0) for name in SEMANTIC_DIMENSION_ORDER)
