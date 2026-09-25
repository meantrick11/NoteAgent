"""Index notes from NOTES_DIR into Chroma, one file or all of them.

Rebuild is the supported recovery path: the index is derived data, and a configuration
change (embedding model or chunking strategy) makes every stored vector incomparable,
so the collection must be rebuilt rather than mixed.

目标模型与 collection 以界面持久化的 active 为准（与运行时同一套解析），否则界面切到
新 collection 后本脚本会继续更新旧库。
"""

from __future__ import annotations

import argparse
import logging
import sys

from noteagent.bootstrap.settings import Settings
from noteagent.model_management.store import ModelSettingsCorruptError, ModelSettingsStore
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import build_embedder
from noteagent.retrieval.service import (
    RetrievalService,
    index_config_fingerprint,
    index_targets,
)
from noteagent.retrieval.vector_store import ChromaVectorStore

_logger = logging.getLogger(__name__)


def resolve_index_target(settings: Settings) -> tuple[str, str, str]:
    """Return (model_id, collection, source) for the index this script should write.

    The interface's persisted choice wins, so the CLI cannot keep updating the old
    collection after someone switched models in the browser. With no saved choice the
    values are exactly the ones from .env.
    """
    store = ModelSettingsStore(settings.model_settings_dir)
    try:
        document = store.load_effective(settings)
    except ModelSettingsCorruptError as exc:
        print(f"模型配置不可用：{exc}")
        raise SystemExit(2) from exc
    active = document.active_embedding
    if active is None:
        return settings.embedding_model, settings.chroma_collection, ".env"
    source = str(store.path) if store.path.exists() else ".env（界面尚未保存过选择）"
    return active.model_id, active.collection, source


def _build(
    settings: Settings, notes: FileNoteRepository, *, model_id: str, collection: str
) -> tuple[RetrievalService, str]:
    """Assemble the retrieval stack for one model and collection."""
    embedder = build_embedder(
        model_id,
        settings.embedding_cache_dir,
        local_files_only=settings.embedding_local_files_only,
    )
    chunker = MarkdownChunker(strategy=settings.chunk_strategy)
    fingerprint = index_config_fingerprint(chunker, embedder, settings.embed_heading_prefix)
    service = RetrievalService(
        notes=notes,
        chunker=chunker,
        embedder=embedder,
        store=ChromaVectorStore(settings.chroma_dir, collection),
        embed_heading_prefix=settings.embed_heading_prefix,
    )
    return service, fingerprint


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
    model_id, collection, source = resolve_index_target(settings)
    print(f"model: {model_id}")
    print(f"collection: {collection}")
    print(f"target from: {source}")
    if args.all:
        targets, skipped = index_targets(notes)
        if skipped:
            print("skipped: " + ", ".join(skipped))
    else:
        targets = [notes.normalize(args.file_name)]

    if args.dry_run:
        return _dry_run(settings, notes, targets, model_id=model_id, collection=collection)

    service, fingerprint = _build(
        settings, notes, model_id=model_id, collection=collection
    )
    for name in targets:
        count = service.index_note(name)
        print(f"indexed {name}: {count} chunks")
    print(f"config fingerprint: {fingerprint}")
    return 0


def _dry_run(
    settings: Settings,
    notes: FileNoteRepository,
    targets: list[str],
    *,
    model_id: str,
    collection: str,
) -> int:
    """Report the rebuild plan and whether the existing index matches the configuration."""
    chunker = MarkdownChunker(strategy=settings.chunk_strategy)
    store = ChromaVectorStore(settings.chroma_dir, collection)
    wanted = index_config_fingerprint(
        chunker,
        build_embedder(
            model_id,
            settings.embedding_cache_dir,
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
