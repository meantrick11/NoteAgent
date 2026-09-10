"""Load golden-set rows from evals/prompt/cases.jsonl."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

_logger = logging.getLogger(__name__)

LEGACY_RUBRIC_VERSION = "v0.1"
LEARNING_RUBRIC_VERSION = "v0.2"


@dataclass
class EvalCase:
    """One JSONL exam row. seed_files are relative notes written before the turn."""

    id: str
    kind: str
    user: str
    expect_propose: bool
    expect_tools_prefix: list[str] = field(default_factory=list)
    must_headings: list[str] = field(default_factory=list)
    forbidden_headings: list[str] = field(default_factory=list)
    must_anchors: list[str] = field(default_factory=list)
    must_substrings: list[str] = field(default_factory=list)
    style: str = "faithful_paragraphs"
    expect_action: str | None = None
    seed_files: dict[str, str] = field(default_factory=dict)
    task_mode: str = ""
    output_language: str = ""
    must_concepts: list[str] = field(default_factory=list)
    must_relations: list[str] = field(default_factory=list)
    must_preserve: list[str] = field(default_factory=list)
    forbidden_claims: list[str] = field(default_factory=list)
    review_questions: list[str] = field(default_factory=list)
    quality_thresholds: dict[str, int] = field(default_factory=dict)


def case_rubric_version(case: EvalCase) -> str:
    """Return the scoring rubric assigned to one eval case."""
    if case.task_mode == "learning_note":
        return LEARNING_RUBRIC_VERSION
    return LEGACY_RUBRIC_VERSION


def load_cases(path: Path, ids: list[str] | None = None) -> list[EvalCase]:
    """Parse JSONL. If ids is set, keep that order and error on missing ids."""
    rows: list[EvalCase] = []
    by_id: dict[str, EvalCase] = {}
    with path.open(encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            data = json.loads(text)
            case = _from_dict(data)
            rows.append(case)
            by_id[case.id] = case
            _logger.info("eval case loaded id=%s line=%d kind=%s", case.id, line_no, case.kind)
    if ids is None:
        return rows
    missing = [case_id for case_id in ids if case_id not in by_id]
    if missing:
        raise KeyError(f"unknown case ids: {missing}")
    return [by_id[case_id] for case_id in ids]


def _from_dict(data: dict) -> EvalCase:
    """Map a JSON object onto EvalCase. Unknown keys are ignored."""
    return EvalCase(
        id=str(data["id"]),
        kind=str(data.get("kind") or "quality"),
        user=str(data["user"]),
        expect_propose=bool(data.get("expect_propose", False)),
        expect_tools_prefix=list(data.get("expect_tools_prefix") or []),
        must_headings=list(data.get("must_headings") or []),
        forbidden_headings=list(data.get("forbidden_headings") or []),
        must_anchors=list(data.get("must_anchors") or []),
        must_substrings=list(data.get("must_substrings") or []),
        style=str(data.get("style") or "faithful_paragraphs"),
        expect_action=data.get("expect_action"),
        seed_files=dict(data.get("seed_files") or {}),
        task_mode=str(data.get("task_mode") or ""),
        output_language=str(data.get("output_language") or ""),
        must_concepts=list(data.get("must_concepts") or []),
        must_relations=list(data.get("must_relations") or []),
        must_preserve=list(data.get("must_preserve") or []),
        forbidden_claims=list(data.get("forbidden_claims") or []),
        review_questions=list(data.get("review_questions") or []),
        quality_thresholds=dict(data.get("quality_thresholds") or {}),
    )
