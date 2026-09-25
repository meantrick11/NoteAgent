"""Index notes from NOTES_DIR into Chroma, one file or all of them.

Rebuild is the supported recovery path: the index is derived data, and a configuration
change (embedding model or chunking strategy) makes every stored vector incomparable,
so the collection must be rebuilt rather than mixed.
"""

from __future__ import annotations

import argparse
import logging
import sys

from noteagent.bootstrap.settings import Settings
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import SentenceTransformerEmbedder
from noteagent.retrieval.service import RetrievalService, index_config_fingerprint
from noteagent.retrieval.vector_store import ChromaVectorStore

_logger = logging.getLogger(__name__)


def _build(settings: Settings, notes: FileNoteRepository) -> tuple[RetrievalService, str]:
    """Assemble the production retrieval stack and report its config fingerprint."""
    embedder = SentenceTransformerEmbedder(
        settings.embedding_model,
        cache_folder=settings.embedding_cache_dir,
        local_files_only=settings.embedding_local_files_only,
    )
    chunker = MarkdownChunker(strategy=settings.chunk_strategy)
    fingerprint = index_config_fingerprint(chunker, embedder, settings.embed_heading_prefix)
    service = RetrievalService(
        notes=notes,
        chunker=chunker,
        embedder=embedder,
        store=ChromaVectorStore(settings.chroma_dir, settings.chroma_collection),
        embed_heading_prefix=settings.embed_heading_prefix,
    )
    return service, fingerprint


def _rebuild_targets(notes: FileNoteRepository) -> tuple[list[str], list[str]]:
    """Every indexable note, plus the files skipped on purpose.

    ``README.md`` is the data-directory description and ``bak/`` holds backups; the
    repository already treats both as not-notes, so a bulk rebuild must not quietly
    put them into the retrieval index.
    """
    keep: list[str] = []
    skipped: list[str] = []
    for name in notes.list_notes():
        if name == "README.md" or name.split("/")[0] == "bak":
            skipped.append(name)
            continue
        keep.append(name)
    return keep, skipped


def main(argv: list[str] | None = None) -> int:
    """Reindex one note, or every note with ``--all``; ``--dry-run`` only reports."""
    parser = argparse.ArgumentParser(description="Index notes into Chroma")
    parser.add_argument("file_name", nargs="?", help="Markdown file under notes/, e.g. Agent.md")
    parser.add_argument("--all", action="store_true", help="重建 notes/ 下发现的每一篇")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只报告将要重建哪些篇、各多少块、以及现有索引是否与当前配置一致",
    )
    args = parser.parse_args(argv)
    if bool(args.file_name) == bool(args.all):
        parser.error("正好给一个：文件名或 --all")

    settings = Settings()
    notes = FileNoteRepository(settings.notes_dir)
    if args.all:
        targets, skipped = _rebuild_targets(notes)
        if skipped:
            print("skipped: " + ", ".join(skipped))
    else:
        targets = [notes.normalize(args.file_name)]

    if args.dry_run:
        return _dry_run(settings, notes, targets)

    service, fingerprint = _build(settings, notes)
    for name in targets:
        count = service.index_note(name)
        print(f"indexed {name}: {count} chunks")
    print(f"config fingerprint: {fingerprint}")
    return 0


def _dry_run(settings: Settings, notes: FileNoteRepository, targets: list[str]) -> int:
    """Report the rebuild plan and whether the existing index matches the configuration."""
    chunker = MarkdownChunker(strategy=settings.chunk_strategy)
    store = ChromaVectorStore(settings.chroma_dir, settings.chroma_collection)
    wanted = index_config_fingerprint(
        chunker,
        SentenceTransformerEmbedder(
            settings.embedding_model,
            cache_folder=settings.embedding_cache_dir,
            local_files_only=True,
        ),
        settings.embed_heading_prefix,
    )
    stored = store.stored_config()
    total = 0
    for name in targets:
        chunks = chunker.split_with_metadata(notes.read(name))
        total += len(chunks)
        print(f"would index {name}: {len(chunks)} chunks")
    print(f"notes={len(targets)} chunks={total}")
    print(f"stored  fingerprint: {stored or '(none)'}")
    print(f"current fingerprint: {wanted}")
    if stored == wanted:
        print("rebuild not needed: 配置一致")
        return 0
    print("rebuild required: 现有索引与当前配置不符，直接启动会报 IndexConfigMismatch")
    print("重建：删掉 var 下的 chroma 目录，或对每篇跑一次本脚本（--all）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
