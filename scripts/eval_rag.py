"""Run the direct retrieval evaluation. See docs/evaluations/rag-quality.md."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from noteagent.rag_eval.run import run_retrieval_eval

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")


def main() -> int:
    """Parse arguments and run one retrieval evaluation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("evals/rag/corpus/v1"))
    parser.add_argument("--queries", type=Path, default=Path("evals/rag/queries.v1.jsonl"))
    parser.add_argument("--split", choices=("dev", "holdout"), required=True)
    parser.add_argument("--variant", required=True, help="配置名，用于 collection 命名")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--probe-k", type=int, default=20, help="诊断用的更深候选数")
    parser.add_argument("--repeats", type=int, default=3, help="每条查询的热延迟重复次数")
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--var-root", type=Path, default=Path("var/evals/rag"))
    parser.add_argument("--results-root", type=Path, default=Path("evals/rag/results"))
    args = parser.parse_args()

    summary = run_retrieval_eval(
        corpus_dir=args.corpus,
        queries_path=args.queries,
        split=args.split,
        variant=args.variant,
        run_id=args.run_id,
        var_root=args.var_root,
        results_root=args.results_root,
        top_k=args.top_k,
        probe_k=args.probe_k,
        repeats=args.repeats,
        warmup=args.warmup,
    )
    answerable = summary["answerable"]
    print(
        f"recall@{summary['top_k']} {answerable['full_recall_at_k']['passed']}/"
        f"{answerable['full_recall_at_k']['total']} "
        f"hit@3 {answerable['hit_at_3']['passed']}/{answerable['hit_at_3']['total']} "
        f"probe@{summary['probe_k']} {answerable['full_recall_at_probe_k']['passed']}/"
        f"{answerable['full_recall_at_probe_k']['total']} "
        f"min {summary['latency']['min_ms']}ms p95 {summary['latency']['p95_ms']}ms"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
