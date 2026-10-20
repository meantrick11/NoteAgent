"""Offline prompt eval. In-process ChatAgent; never writes the user's notes/."""

from __future__ import annotations

import sys
from pathlib import Path

# Evaluation code is a development tool, outside the production application package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Tools"))

import argparse
import asyncio
import hashlib
import logging
import shutil
from datetime import datetime

from NoteAgent.AppBootstrap.AppSettings import Settings, project_root
from NoteAgent.Common.Logging.LoggingSetup import setup_logging
from NoteAgentEvals.ModelResolver import build_active_chat, build_judge
from NoteAgentEvals.Prompt.Cases import load_cases
from NoteAgentEvals.Prompt.Report import result_dest
from NoteAgentEvals.Prompt.Run import run_eval

DEFAULT_CASES = Path("evals/prompt/cases.jsonl")
DEFAULT_PROMPT = Path("src/NoteAgent/Modules/Chat/Agent/SystemPrompts/system.txt")
RESULTS_ROOT = Path("evals/prompt/results")


def main(argv: list[str] | None = None) -> int:
    """Parse CLI, refuse overwrite unless --force, run cases, write the stage folder."""
    parser = argparse.ArgumentParser(description="Run NoteAgent prompt eval (offline, no review).")
    parser.add_argument(
        "--name",
        default="",
        help="Optional label in the result folder (e.g. v8). Dataset stem and case ids are added automatically.",
    )
    parser.add_argument("--ids", default="", help="Comma-separated case ids; default is the whole set")
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT), help="Path to system.txt")
    parser.add_argument("--cases", default=str(DEFAULT_CASES), help="JSONL golden set")
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Run semantic Judge; defaults to the active model",
    )
    parser.add_argument(
        "--judge-model",
        default="",
        help="Optional upstream model name for an independent Judge (same connection as active)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing result folder")
    args = parser.parse_args(argv)

    root = project_root()
    cases_path = (root / args.cases).resolve() if not Path(args.cases).is_absolute() else Path(args.cases)
    prompt_path = (root / args.prompt).resolve() if not Path(args.prompt).is_absolute() else Path(args.prompt)
    ids = [item.strip() for item in args.ids.split(",") if item.strip()] or None
    label = args.name.strip() or None
    try:
        dest = result_dest(
            root / RESULTS_ROOT,
            cases_path=cases_path,
            ids=ids,
            label=label,
            when=datetime.now(),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if dest.exists() and any(dest.iterdir()):
        if not args.force:
            print(f"refuse overwrite {dest} (pass --force)", file=sys.stderr)
            return 1
        shutil.rmtree(dest)

    settings = Settings()
    try:
        chat = build_active_chat(settings)
        judge = build_judge(settings, args.judge_model or None) if args.judge else None
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    chat_model_name = chat.config.model
    judge_model_name = judge.config.model if judge is not None else None
    if judge is not None and judge_model_name == chat_model_name:
        print(
            f"WARNING: Judge uses the same model as chat ({judge_model_name}); "
            "judge_independent=false",
            file=sys.stderr,
        )

    level = getattr(logging, settings.log_level.upper(), logging.DEBUG)
    setup_logging(settings.log_dir, level=level)
    logger = logging.getLogger("NoteAgentEvals.Prompt")
    cases = load_cases(cases_path, ids)
    logger.info(
        "eval start dest=%s cases=%d dataset=%s filter=%s prompt=%s model=%s judge_model=%s",
        dest,
        len(cases),
        cases_path,
        ids or "all",
        prompt_path,
        chat_model_name,
        judge_model_name or "disabled",
    )
    prompt_display = _display_path(root, prompt_path)
    cases_display = _display_path(root, cases_path)
    asyncio.run(
        run_eval(
            cases,
            dest=dest,
            prompt_path=prompt_path,
            settings=settings,
            model=chat.client,
            chat_model_name=chat_model_name,
            judge_model=judge.client if judge is not None else None,
            judge_model_name=judge_model_name,
            cases_sha256=_sha256(cases_path),
            prompt_display=prompt_display,
            cases_display=cases_display,
            case_filter=ids,
            label=label,
        )
    )
    logger.info("eval done dest=%s", dest)
    print(dest)
    return 0


def _sha256(path: Path) -> str:
    """Hash the actual JSONL input archived in result metadata."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(root: Path, path: Path) -> str:
    """Store a repo-relative path in config.json when possible."""
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
