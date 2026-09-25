"""Load and validate the frozen RAG evaluation corpus and query set.

Everything here is read-only. Bad annotations must fail loudly: a silently
skipped or guessed offset would turn into a fake metric later.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from noteagent.rag_eval.metrics import Interval

_logger = logging.getLogger(__name__)

CATEGORIES = ("fact", "paraphrase", "mixed_language", "multi_evidence", "unanswerable")
SPLITS = ("dev", "holdout")
SOURCE_STATUSES = ("available", "missing", "synthetic")
REVIEW_STATUSES = ("reviewed", "provisional")

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_LATIN_TERM_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.+-]{2,}")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
_CJK_NGRAM = 3

Split = Literal["dev", "holdout"]
Category = Literal["fact", "paraphrase", "mixed_language", "multi_evidence", "unanswerable"]


class DatasetError(ValueError):
    """A corpus or query annotation that cannot be trusted."""


@dataclass(frozen=True, slots=True)
class NoteRecord:
    """One manifest row: identity, provenance and review state of a corpus note."""

    note_id: str
    file: str
    sha256: str
    origin_path: str
    source_file: str | None
    source_status: str
    review_status: str
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Heading:
    """One Markdown heading, with its joined path and its own char range."""

    level: int
    text: str
    path: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class EvidenceLocation:
    """One acceptable place for an evidence unit, quoting the frozen text exactly."""

    note_id: str
    heading_path: str
    start_char: int
    end_char: int
    quote: str


@dataclass(frozen=True, slots=True)
class EvidenceUnit:
    """One fact that must be recovered, with every location that may support it."""

    id: str
    fact: str
    alternatives: tuple[EvidenceLocation, ...]


@dataclass(frozen=True, slots=True)
class QueryCase:
    """One annotated retrieval query."""

    id: str
    group_id: str
    split: Split
    query: str
    category: Category
    answerable: bool
    evidence_units: tuple[EvidenceUnit, ...]


@dataclass(frozen=True, slots=True)
class Corpus:
    """Frozen note texts plus the manifest that explains where they came from."""

    root: Path
    notes: dict[str, NoteRecord]
    texts: dict[str, str]
    headings: dict[str, tuple[Heading, ...]]

    def required_units(self, query: QueryCase) -> dict[str, list[Interval]]:
        """Map every unit id to its acceptable evidence intervals in this corpus."""
        units: dict[str, list[Interval]] = {}
        for unit in query.evidence_units:
            units[unit.id] = [
                Interval(loc.note_id, loc.start_char, loc.end_char)
                for loc in unit.alternatives
            ]
        return units


@dataclass(frozen=True, slots=True)
class AgentCase:
    """One end-to-end Agent scenario, scored against the annotated query set."""

    id: str
    group_id: str
    split: Split
    scenario: str
    user: str
    pre_dialogue: tuple[tuple[str, str], ...]
    expect_search: bool
    expect_action: str | None
    target_file: str | None
    new_content: str | None
    evidence_refs: tuple[str, ...]
    must_preserve_refs: tuple[str, ...]
    must_not_contain_refs: tuple[str, ...]
    expect_flags_conflict: bool
    conflict_markers: tuple[str, ...]
    expect_no_write: bool
    notes: str


def note_headings(text: str) -> tuple[Heading, ...]:
    """Parse ATX headings, ignoring ``#`` lines inside fenced code blocks."""
    headings: list[Heading] = []
    stack: list[tuple[int, str]] = []
    offset = 0
    in_fence = False
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n").rstrip("\r")
        if _FENCE_RE.match(stripped):
            in_fence = not in_fence
        elif not in_fence:
            match = _HEADING_RE.match(stripped)
            if match and match.group(2):
                level = len(match.group(1))
                label = match.group(2)
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, label))
                headings.append(
                    Heading(
                        level=level,
                        text=label,
                        path=" > ".join(item[1] for item in stack),
                        start=offset,
                        end=offset + len(line),
                    )
                )
        offset += len(line)
    if in_fence:
        _logger.warning("note ends inside an unclosed code fence")
    return tuple(headings)


def heading_path_at(headings: tuple[Heading, ...], offset: int) -> str:
    """Path of the innermost heading whose section contains ``offset``.

    Returns an empty string when the offset sits before the first heading.
    """
    path = ""
    for heading in headings:
        if heading.start <= offset:
            path = heading.path
        else:
            break
    return path


def load_corpus(corpus_dir: Path) -> Corpus:
    """Read the manifest and every note it lists, verifying sha256 byte for byte."""
    manifest_path = corpus_dir / "manifest.jsonl"
    if not manifest_path.is_file():
        raise DatasetError(f"missing corpus manifest: {manifest_path}")
    notes: dict[str, NoteRecord] = {}
    texts: dict[str, str] = {}
    headings: dict[str, tuple[Heading, ...]] = {}
    for row in _read_jsonl(manifest_path):
        record = _note_record(row, manifest_path)
        if record.note_id in notes:
            raise DatasetError(f"duplicate note_id {record.note_id} in {manifest_path}")
        raw_path = corpus_dir / "notes" / record.file
        if not raw_path.is_file():
            raise DatasetError(f"{record.note_id}: note file not found: {raw_path}")
        raw = raw_path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != record.sha256:
            raise DatasetError(
                f"{record.note_id}: sha256 mismatch ({actual} != {record.sha256}); "
                "the corpus copy was edited after freezing"
            )
        notes[record.note_id] = record
        # 用应用实际读到的文本：FileNoteRepository 走 Path.read_text，会把 CRLF 规范化成 LF。
        # 证据偏移必须建立在这份文本上，否则与生产切块对不上。
        texts[record.note_id] = raw_path.read_text(encoding="utf-8")
        headings[record.note_id] = note_headings(texts[record.note_id])
    listed = set(notes)
    present = {path.stem for path in (corpus_dir / "notes").glob("*.md")}
    if listed != present:
        raise DatasetError(
            f"manifest and notes/ disagree: only in manifest {sorted(listed - present)}, "
            f"only on disk {sorted(present - listed)}"
        )
    _logger.info("corpus loaded notes=%d root=%s", len(notes), corpus_dir)
    return Corpus(root=corpus_dir, notes=notes, texts=texts, headings=headings)


def load_queries(path: Path, corpus: Corpus) -> list[QueryCase]:
    """Read and fully validate a query set against a loaded corpus."""
    queries: list[QueryCase] = []
    for row in _read_jsonl(path):
        queries.append(_query_case(row, corpus, path))
    _validate_composition(queries, corpus, path)
    _logger.info("queries loaded count=%d path=%s", len(queries), path)
    return queries


def load_agent_cases(path: Path, queries: list[QueryCase]) -> list[AgentCase]:
    """Read Agent scenarios and check every reference against the query set."""
    known = {query.id: query for query in queries}
    cases: list[AgentCase] = []
    for row in _read_jsonl(path):
        cases.append(_agent_case(row, known, path))
    _logger.info("agent cases loaded count=%d path=%s", len(cases), path)
    return cases


AGENT_SCENARIOS = (
    "history_answer",
    "history_append",
    "history_unanswerable",
    "plain_chat",
)


def _agent_case(row: dict, known: dict[str, QueryCase], path: Path) -> AgentCase:
    """Validate one Agent scenario, including cross-references and consistency."""
    where = f"{path}:{row.get('id', '<no id>')}"
    case_id = str(_require(row, "id", where))
    scenario = str(_require(row, "scenario", where))
    if scenario not in AGENT_SCENARIOS:
        raise DatasetError(f"{where}: scenario must be one of {AGENT_SCENARIOS}")
    split = str(_require(row, "split", where))
    if split not in SPLITS:
        raise DatasetError(f"{where}: split must be one of {SPLITS}")
    user = str(_require(row, "user", where))
    if not user.strip():
        raise DatasetError(f"{where}: user must not be empty")

    def _refs(key: str) -> tuple[str, ...]:
        raw = row.get(key) or []
        if not isinstance(raw, list):
            raise DatasetError(f"{where}: {key} must be a list")
        missing = [item for item in raw if item not in known]
        if missing:
            raise DatasetError(f"{where}: {key} references unknown queries {missing}")
        wrong_split = [item for item in raw if known[item].split != split]
        if wrong_split:
            raise DatasetError(
                f"{where}: {key} crosses splits (case={split}, refs={wrong_split})"
            )
        return tuple(str(item) for item in raw)

    evidence_refs = _refs("evidence_refs")
    must_preserve = _refs("must_preserve_refs")
    must_not_contain = _refs("must_not_contain_refs")
    expect_search = bool(_require(row, "expect_search", where))
    expect_action = row.get("expect_action")
    target_file = row.get("target_file")
    new_content = row.get("new_content")
    expect_no_write = bool(row.get("expect_no_write", False))
    expect_flags_conflict = bool(row.get("expect_flags_conflict", False))
    markers = tuple(str(item) for item in row.get("conflict_markers") or [])
    dialogue = tuple(
        (str(item["role"]), str(item["content"]))
        for item in row.get("pre_dialogue") or []
    )

    if scenario == "plain_chat":
        if expect_search:
            raise DatasetError(f"{where}: plain_chat must not expect a search call")
        if not expect_no_write:
            raise DatasetError(f"{where}: plain_chat must expect no write")
    else:
        if not expect_search:
            raise DatasetError(f"{where}: history scenarios must expect a search call")
    if scenario == "history_answer" and not evidence_refs:
        raise DatasetError(f"{where}: history_answer needs evidence_refs to cite")
    if scenario == "history_append":
        if not target_file or not new_content:
            raise DatasetError(f"{where}: history_append needs target_file and new_content")
        # 冲突场景允许「先澄清不写」和「有依据的更正草稿」两种结果，因此不锁死 action。
        if expect_action is None and not expect_flags_conflict:
            raise DatasetError(
                f"{where}: history_append needs expect_action unless it is a conflict case"
            )
    elif expect_action is not None:
        raise DatasetError(f"{where}: only history_append may expect an action")
    if expect_flags_conflict and not markers:
        raise DatasetError(f"{where}: expect_flags_conflict needs conflict_markers")
    if scenario == "history_unanswerable" and evidence_refs:
        raise DatasetError(f"{where}: history_unanswerable must not carry evidence refs")
    return AgentCase(
        id=case_id,
        group_id=str(_require(row, "group_id", where)),
        split=split,
        scenario=scenario,
        user=user,
        pre_dialogue=dialogue,
        expect_search=expect_search,
        expect_action=None if expect_action is None else str(expect_action),
        target_file=None if target_file is None else str(target_file),
        new_content=None if new_content is None else str(new_content),
        evidence_refs=evidence_refs,
        must_preserve_refs=must_preserve,
        must_not_contain_refs=must_not_contain,
        expect_flags_conflict=expect_flags_conflict,
        conflict_markers=markers,
        expect_no_write=expect_no_write,
        notes=str(row.get("notes") or ""),
    )


def _read_jsonl(path: Path) -> list[dict]:
    """Parse a record file that is either a JSON array or JSONL of objects."""
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("["):
        rows = json.loads(text)
        if not isinstance(rows, list):
            raise DatasetError(f"{path}: expected a JSON array of objects")
        return rows
    parsed: list[dict] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"{path}:{number}: invalid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise DatasetError(f"{path}:{number}: expected a JSON object")
        parsed.append(row)
    return parsed


def _require(row: dict, key: str, where: str) -> object:
    """Fetch a required field or fail with the offending record named."""
    if key not in row:
        raise DatasetError(f"{where}: missing field {key!r}")
    return row[key]


def _note_record(row: dict, path: Path) -> NoteRecord:
    """Validate one manifest row."""
    where = f"{path}:{row.get('note_id', '<no note_id>')}"
    source_status = str(_require(row, "source_status", where))
    review_status = str(_require(row, "review_status", where))
    if source_status not in SOURCE_STATUSES:
        raise DatasetError(f"{where}: source_status must be one of {SOURCE_STATUSES}")
    if review_status not in REVIEW_STATUSES:
        raise DatasetError(f"{where}: review_status must be one of {REVIEW_STATUSES}")
    source_file = row.get("source_file")
    if source_file is not None and not isinstance(source_file, str):
        raise DatasetError(f"{where}: source_file must be a string or null")
    issues = row.get("issues") or []
    if not isinstance(issues, list):
        raise DatasetError(f"{where}: issues must be a list")
    return NoteRecord(
        note_id=str(_require(row, "note_id", where)),
        file=str(_require(row, "file", where)),
        sha256=str(_require(row, "sha256", where)),
        origin_path=str(_require(row, "origin_path", where)),
        source_file=source_file,
        source_status=source_status,
        review_status=review_status,
        issues=tuple(str(item) for item in issues),
    )


def _query_case(row: dict, corpus: Corpus, path: Path) -> QueryCase:
    """Validate one query row, including every evidence offset."""
    where = f"{path}:{row.get('id', '<no id>')}"
    case_id = str(_require(row, "id", where))
    group_id = str(_require(row, "group_id", where))
    split = str(_require(row, "split", where))
    category = str(_require(row, "category", where))
    query = str(_require(row, "query", where))
    answerable = _require(row, "answerable", where)
    if split not in SPLITS:
        raise DatasetError(f"{where}: split must be one of {SPLITS}")
    if category not in CATEGORIES:
        raise DatasetError(f"{where}: category must be one of {CATEGORIES}")
    if not isinstance(answerable, bool):
        raise DatasetError(f"{where}: answerable must be a boolean")
    if not query.strip():
        raise DatasetError(f"{where}: query must not be empty")
    raw_units = row.get("evidence_units") or []
    if not isinstance(raw_units, list):
        raise DatasetError(f"{where}: evidence_units must be a list")

    units: list[EvidenceUnit] = []
    seen_units: set[str] = set()
    for index, raw_unit in enumerate(raw_units):
        unit_where = f"{where}:unit[{index}]"
        if not isinstance(raw_unit, dict):
            raise DatasetError(f"{unit_where}: expected an object")
        unit_id = str(_require(raw_unit, "id", unit_where))
        if unit_id in seen_units:
            raise DatasetError(f"{unit_where}: duplicate unit id {unit_id!r}")
        seen_units.add(unit_id)
        fact = str(_require(raw_unit, "fact", unit_where))
        alternatives = raw_unit.get("alternatives") or []
        if not isinstance(alternatives, list) or not alternatives:
            raise DatasetError(f"{unit_where}: at least one alternative is required")
        locations = tuple(
            _evidence_location(raw, corpus, f"{unit_where}:alt[{alt_index}]")
            for alt_index, raw in enumerate(alternatives)
        )
        units.append(EvidenceUnit(id=unit_id, fact=fact, alternatives=locations))

    if answerable and (category == "unanswerable" or not units):
        raise DatasetError(f"{where}: an answerable query needs category evidence and units")
    if not answerable and (category != "unanswerable" or units):
        raise DatasetError(f"{where}: an unanswerable query must have no evidence units")
    return QueryCase(
        id=case_id,
        group_id=group_id,
        split=split,
        query=query,
        category=category,
        answerable=answerable,
        evidence_units=tuple(units),
    )


def _evidence_location(row: object, corpus: Corpus, where: str) -> EvidenceLocation:
    """Validate one evidence location against the frozen note text."""
    if not isinstance(row, dict):
        raise DatasetError(f"{where}: expected an object")
    note_id = str(_require(row, "note_id", where))
    if note_id not in corpus.notes:
        raise DatasetError(f"{where}: unknown note_id {note_id!r}")
    heading_path = str(_require(row, "heading_path", where))
    start = _require(row, "start_char", where)
    end = _require(row, "end_char", where)
    quote = str(_require(row, "quote", where))
    if not isinstance(start, int) or not isinstance(end, int):
        raise DatasetError(f"{where}: start_char and end_char must be integers")
    text = corpus.texts[note_id]
    if start < 0 or end > len(text):
        raise DatasetError(
            f"{where}: range [{start}, {end}) is outside {note_id} (len {len(text)})"
        )
    if start >= end:
        raise DatasetError(f"{where}: start_char must be below end_char")
    actual = text[start:end]
    if actual != quote:
        raise DatasetError(
            f"{where}: quote does not match {note_id}[{start}:{end}]; "
            f"file has {actual!r}"
        )
    paths = {heading.path for heading in corpus.headings[note_id]}
    if heading_path not in paths:
        raise DatasetError(f"{where}: {heading_path!r} is not a heading path of {note_id}")
    return EvidenceLocation(
        note_id=note_id,
        heading_path=heading_path,
        start_char=start,
        end_char=end,
        quote=quote,
    )


def _validate_composition(queries: list[QueryCase], corpus: Corpus, path: Path) -> None:
    """Check the dataset-level rules that no single record can carry."""
    counts = {split: {"answerable": 0, "unanswerable": 0} for split in SPLITS}
    groups: dict[str, set[str]] = {}
    for query in queries:
        key = "answerable" if query.answerable else "unanswerable"
        counts[query.split][key] += 1
        groups.setdefault(query.group_id, set()).add(query.split)
    for group_id, splits in groups.items():
        if len(splits) > 1:
            raise DatasetError(
                f"{path}: group {group_id!r} appears in both splits; equivalent "
                "questions must stay on one side"
            )
    unanswerable = [query for query in queries if not query.answerable]
    if unanswerable:
        overlap = sum(1 for query in unanswerable if _shares_term(query.query, corpus))
        if overlap * 2 < len(unanswerable):
            raise DatasetError(
                f"{path}: only {overlap} of {len(unanswerable)} unanswerable queries "
                "share a corpus term; at least half must be near-misses, not off-topic"
            )
    _logger.info(
        "query composition dev=%s holdout=%s unanswerable_near_miss=%d",
        counts["dev"],
        counts["holdout"],
        sum(1 for query in unanswerable if _shares_term(query.query, corpus)),
    )


def _shares_term(query: str, corpus: Corpus) -> bool:
    """True if the query uses a term the corpus also uses (a near-miss, not off-topic).

    Chinese has no spaces here and no segmenter is loaded, so runs of CJK are cut
    into overlapping n-grams; Latin identifiers are taken whole.
    """
    terms: set[str] = set(_LATIN_TERM_RE.findall(query))
    for run in _CJK_RUN_RE.findall(query):
        terms.update(
            run[index : index + _CJK_NGRAM]
            for index in range(len(run) - _CJK_NGRAM + 1)
        )
    if not terms:
        return False
    haystack = "\n".join(corpus.texts.values())
    return any(term in haystack for term in terms)
