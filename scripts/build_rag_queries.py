"""Build a frozen query set from a hand-written draft.

The draft carries the verbatim quote for each evidence location; this script
locates every quote in the frozen corpus, infers the containing heading path and
the character offsets, then reloads the result through the formal validator. A
quote that cannot be located uniquely is reported, never guessed.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from noteagent.rag_eval.dataset import DatasetError, heading_path_at, load_corpus

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
_logger = logging.getLogger("build_rag_queries")


def dominant_newline(text: str) -> str:
    """The line ending the note actually uses; drafts are written with LF."""
    return "\r\n" if text.count("\r\n") >= text.count("\n") else "\n"


def locate(text: str, quote: str, occurrence: int, after: str | None) -> int | None:
    """Return the start offset of the requested occurrence of quote, or None."""
    starts: list[int] = []
    cursor = text.find(quote)
    while cursor != -1:
        starts.append(cursor)
        cursor = text.find(quote, cursor + 1)
    if not starts:
        return None
    if after is not None:
        anchor = text.find(after)
        if anchor == -1:
            return None
        starts = [start for start in starts if start > anchor]
    if len(starts) < occurrence:
        return None
    return starts[occurrence - 1]


def _closest_line(text: str, quote: str) -> str:
    """Best-effort hint for a failed quote: the line sharing the longest prefix."""
    probe = quote[:12]
    for number, line in enumerate(text.splitlines(), 1):
        if probe and probe in line:
            return f"line {number}: {line[:120]}"
    lines = text.splitlines()
    return f"no line matches {probe!r}; file has {len(lines)} lines"


def read_drafts(path: Path) -> list[dict]:
    """Read drafts from a JSON array or a JSONL file."""
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("["):
        return list(json.loads(text))
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def build(corpus_dir: Path, draft_path: Path, output_path: Path) -> int:
    """Write the annotated query set and report every unresolvable quote."""
    corpus = load_corpus(corpus_dir)
    drafts = read_drafts(draft_path)
    problems: list[str] = []
    rows: list[dict] = []
    for draft in drafts:
        case_id = draft.get("id", "<no id>")
        units = []
        for unit in draft.get("units", []):
            locations = []
            for location in unit["locations"]:
                note_id = location["note_id"]
                text = corpus.texts.get(note_id)
                if text is None:
                    problems.append(f"{case_id}: unknown note_id {note_id!r}")
                    continue
                newline = dominant_newline(text)
                probe = location["quote"].replace("\n", newline)
                start = locate(
                    text,
                    probe,
                    int(location.get("occurrence", 1)),
                    location.get("after"),
                )
                if start is None:
                    problems.append(
                        f"{case_id}: quote not located in {note_id} "
                        f"({_closest_line(text, location['quote'])})"
                    )
                    continue
                end = start + len(probe)
                locations.append(
                    {
                        "note_id": note_id,
                        "heading_path": heading_path_at(corpus.headings[note_id], start),
                        "start_char": start,
                        "end_char": end,
                        "quote": text[start:end],
                    }
                )
            if locations:
                units.append({"id": unit["id"], "fact": unit["fact"], "alternatives": locations})
        if len(units) != len(draft.get("units", [])):
            continue
        rows.append(
            {
                "id": case_id,
                "group_id": draft["group_id"],
                "split": draft["split"],
                "query": draft["query"],
                "category": draft["category"],
                "answerable": draft["answerable"],
                "evidence_units": units,
            }
        )
    if problems:
        print(f"\n{len(problems)} unresolved quote(s):")
        for problem in problems:
            print("  -", problem)
        return 1
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    try:
        from noteagent.rag_eval.dataset import load_queries

        loaded = load_queries(output_path, corpus)
    except DatasetError as exc:
        print(f"validation failed: {exc}")
        return 1
    answerable = sum(1 for item in loaded if item.answerable)
    _logger.info(
        "wrote %d queries -> %s (answerable=%d unanswerable=%d)",
        len(loaded),
        output_path,
        answerable,
        len(loaded) - answerable,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=Path("evals/rag/corpus/v1"))
    parser.add_argument("--draft", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    return build(args.corpus, args.draft, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
