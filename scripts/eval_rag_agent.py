"""Run the real-Agent RAG evaluation. See docs/evaluations/rag-quality.md."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from noteagent.bootstrap.settings import Settings
from noteagent.observability.logging import setup_logging
from noteagent.rag_eval.agent_run import run_agent_eval

DEFAULT_PROMPT = Path("src/noteagent/chat/prompts/system.txt")


def main() -> int:
    """Parse arguments and run the Agent scenarios through the real ChatAgent."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("evals/rag/corpus/v1"))
    parser.add_argument("--cases", type=Path, default=Path("evals/agent/rag_cases.v1.json"))
    parser.add_argument("--queries", type=Path, default=Path("evals/rag/queries.v1.jsonl"))
    parser.add_argument("--split", choices=("dev", "holdout"), required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repeat", type=int, default=3, help="每个场景真实运行的次数")
    parser.add_argument(
        "--model",
        default="",
        help="向量模型完整 id（默认取 EMBEDDING_MODEL）；用于与检索层同一配置对比",
    )
    parser.add_argument("--ids", default="", help="逗号分隔的 case id，用于小范围冒烟")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--var-root", type=Path, default=Path("var/evals/rag"))
    parser.add_argument("--results-root", type=Path, default=Path("evals/agent/results"))
    args = parser.parse_args()

    settings = Settings()
    setup_logging(settings.log_dir, level=logging.DEBUG)
    only_ids = [item.strip() for item in args.ids.split(",") if item.strip()] or None
    summary = run_agent_eval(
        corpus_dir=args.corpus,
        cases_path=args.cases,
        queries_path=args.queries,
        split=args.split,
        variant=args.variant,
        run_id=args.run_id,
        var_root=args.var_root,
        results_root=args.results_root,
        prompt_path=args.prompt,
        repeats=args.repeat,
        only_ids=only_ids,
        embedding_model=args.model or None,
    )
    success = summary["agent_task_success"]
    print(
        f"agent success {success['passed']}/{success['total']} "
        f"search-call {summary['history_search_call_rate']['passed']}/"
        f"{summary['history_search_call_rate']['total']} "
        f"plain-search {summary['plain_chat_search_call_rate']['passed']}/"
        f"{summary['plain_chat_search_call_rate']['total']} "
        f"errors {len(summary['errors'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
