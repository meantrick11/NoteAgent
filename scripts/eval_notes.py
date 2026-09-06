"""Offline prompt eval. In-process ChatAgent; never writes the user's notes/."""

from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

from noteagent.bootstrap.settings import Settings, project_root
from noteagent.llm.factory import create_chat_model
from noteagent.observability.logging import setup_logging
from noteagent.prompt_eval.cases import load_cases
from noteagent.prompt_eval.report import result_dest
from noteagent.prompt_eval.run import run_eval

DEFAULT_CASES = Path("evals/prompt/cases.jsonl")
DEFAULT_PROMPT = Path("src/noteagent/chat/prompts/system.txt")
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
    if not settings.deepseek_api_key.get_secret_value().strip():
        print("DEEPSEEK_API_KEY is not set", file=sys.stderr)
        return 1

    level = getattr(logging, settings.log_level.upper(), logging.DEBUG)
    setup_logging(settings.log_dir, level=level)
    logger = logging.getLogger("noteagent.prompt_eval")
    cases = load_cases(cases_path, ids)
    logger.info(
        "eval start dest=%s cases=%d dataset=%s filter=%s prompt=%s model=%s",
        dest,
        len(cases),
        cases_path,
        ids or "all",
        prompt_path,
        settings.chat_model,
    )
    prompt_display = _display_path(root, prompt_path)
    cases_display = _display_path(root, cases_path)
    model = create_chat_model(settings)
    asyncio.run(
        run_eval(
            cases,
            dest=dest,
            prompt_path=prompt_path,
            settings=settings,
            model=model,
            prompt_display=prompt_display,
            cases_display=cases_display,
            case_filter=ids,
            label=label,
        )
    )
    logger.info("eval done dest=%s", dest)
    print(dest)
    return 0


def _display_path(root: Path, path: Path) -> str:
    """Store a repo-relative path in config.json when possible."""
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
