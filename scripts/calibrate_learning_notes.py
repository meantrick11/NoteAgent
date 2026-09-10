"""Calibrate the learning-note Judge against four versioned fixed candidates."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from noteagent.bootstrap.settings import Settings, project_root
from noteagent.llm.factory import create_judge_model
from noteagent.observability.logging import setup_logging
from noteagent.prompt_eval.calibration import CANDIDATE_NAMES, calibrate_learning_note
from noteagent.prompt_eval.judge import JUDGE_PROMPT_PATH, judge_prompt_sha256
from noteagent.prompt_eval.score import RUBRIC_VERSION

DEFAULT_CASES = Path("evals/prompt/learning_notes.jsonl")
DEFAULT_FIXTURES = Path("evals/prompt/fixtures/learning_notes")
RESULTS_ROOT = Path("evals/prompt/results/learning_notes")


def main(argv: list[str] | None = None) -> int:
    """Run fixed-candidate calibration, archive it, and return contract status."""
    parser = argparse.ArgumentParser(description="Calibrate the learning-note Judge.")
    parser.add_argument("--case-id", default="l01", help="Learning-note case id")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="JSONL case file")
    parser.add_argument(
        "--fixtures",
        default=str(DEFAULT_FIXTURES),
        help="Directory containing the four fixed Markdown candidates",
    )
    args = parser.parse_args(argv)

    root = project_root()
    case_path = _resolve(root, args.cases)
    fixtures_dir = _resolve(root, args.fixtures)
    prompt_path = JUDGE_PROMPT_PATH.resolve()
    started = datetime.now(timezone.utc)
    dest = _result_dest(root, args.case_id, started)
    if dest.exists() and any(dest.iterdir()):
        print(f"refuse overwrite non-empty directory: {dest}", file=sys.stderr)
        return 1

    settings = Settings()
    if not settings.deepseek_api_key.get_secret_value().strip():
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 1
    judge_model_name = settings.judge_model.strip() or settings.chat_model.strip()
    judge_independent = judge_model_name != settings.chat_model.strip()
    if not settings.judge_model.strip():
        print(
            f"WARNING: JUDGE_MODEL is empty; using CHAT_MODEL={judge_model_name} "
            "(judge_independent=false)",
            file=sys.stderr,
        )

    level = getattr(logging, settings.log_level.upper(), logging.DEBUG)
    setup_logging(settings.log_dir, level=level)
    logger = logging.getLogger("noteagent.prompt_eval.calibration")
    logger.info(
        "Judge calibration CLI start dest=%s case_id=%s model=%s independent=%s",
        dest,
        args.case_id,
        judge_model_name,
        judge_independent,
    )
    judge_model = create_judge_model(settings, model_name=judge_model_name)
    result = asyncio.run(
        calibrate_learning_note(
            case_path=case_path,
            case_id=args.case_id,
            fixtures_dir=fixtures_dir,
            judge_model=judge_model,
            judge_model_name=judge_model_name,
            judge_prompt_path=prompt_path,
        )
    )
    finished = datetime.now(timezone.utc)
    config = {
        "rubric_version": RUBRIC_VERSION,
        "case_id": args.case_id,
        "case_path": _display_path(root, case_path),
        "case_file_sha256": _sha256(case_path),
        "fixture_sha256": {
            f"{name}.md": result["candidates"].get(name, {}).get("fixture_sha256")
            for name in CANDIDATE_NAMES
        },
        "judge_model": judge_model_name,
        "judge_prompt_sha256": judge_prompt_sha256(prompt_path),
        "judge_independent": judge_independent,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "errors": result["errors"],
    }
    _write_result(
        dest,
        config=config,
        calibration=result,
        judge_prompt=prompt_path.read_text(encoding="utf-8"),
    )
    logger.info(
        "Judge calibration CLI end dest=%s pass=%s errors=%d",
        dest,
        result["pass"],
        len(result["errors"]),
    )
    print(dest)
    return 0 if result["pass"] else 1


def _result_dest(root: Path, case_id: str, when: datetime) -> Path:
    """Return a timestamped result directory under the learning-note ledger."""
    stamp = when.strftime("%Y%m%d-%H%M%S-%f")
    return (root / RESULTS_ROOT / f"calibration_{case_id}_{stamp}").resolve()


def _resolve(root: Path, value: str) -> Path:
    """Resolve a CLI path relative to the repository root."""
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _sha256(path: Path) -> str:
    """Hash one archived input file for reproducible calibration."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(root: Path, path: Path) -> str:
    """Prefer a repository-relative path in archived metadata."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _write_result(
    dest: Path, *, config: dict, calibration: dict, judge_prompt: str
) -> None:
    """Write calibration metadata and Judge output without touching user notes."""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (dest / "judge_prompt.txt").write_text(judge_prompt, encoding="utf-8")
    (dest / "calibration.json").write_text(
        json.dumps(calibration, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    sys.exit(main())
