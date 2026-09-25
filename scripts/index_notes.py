"""Index notes from NOTES_DIR into Chroma, one file or all of them.

Rebuild is the supported recovery path: the index is derived data, and a configuration
change (embedding model, model revision, or chunking strategy) makes every stored vector
incomparable, so a new index must be built rather than mixed into the old one.

目标模型取自界面持久化的 active（与运行时同一套解析），目标 collection 则由**当前配置
的身份指纹**推出——和运行时重建时用的是同一个名字。否则界面切到新 collection 后本脚本
会继续更新旧库。

本脚本只重建索引数据，不改持久化的 active 指针；指针仍由界面的「重建并切换」发布。两者
不能同时运行（见部署说明的单 worker 限制）。
"""

from __future__ import annotations

import argparse
import logging
import sys

from noteagent.bootstrap.settings import Settings
from noteagent.model_management import catalog
from noteagent.model_management.service import embedding_collection_name
from noteagent.model_management.store import ModelSettingsCorruptError, ModelSettingsStore
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import build_embedder
from noteagent.retrieval.service import (
    RetrievalService,
    index_config_fingerprint,
    index_fingerprint_for_model,
    index_targets,
)
from noteagent.retrieval.vector_store import ChromaVectorStore

_logger = logging.getLogger(__name__)


def _cached_revision(settings: Settings, model_id: str) -> str | None:
    """Snapshot revision of the cached model, part of the index identity."""
    return catalog.resolved_revision(settings.embedding_cache_dir, model_id)


def resolve_index_target(settings: Settings) -> tuple[str, str, str]:
    """Return (model_id, collection, source) for the index this script should write.

    The interface's persisted choice wins, so the CLI cannot rebuild for a model the
    browser no longer uses. The collection name is derived from the full identity, which
    is what makes a CLI rebuild land in exactly the collection the UI switch would build.
    """
    store = ModelSettingsStore(settings.model_settings_dir)
    try:
        document = store.load_effective(settings)
    except ModelSettingsCorruptError as exc:
        print(f"模型配置不可用：{exc}")
        raise SystemExit(2) from exc
    active = document.active_embedding
    if active is None:
        model_id, source = settings.embedding_model, ".env"
    else:
        model_id = active.model_id
        source = str(store.path) if store.path.exists() else ".env（界面尚未保存过选择）"
    fingerprint = index_fingerprint_for_model(
        model_id,
        strategy=settings.chunk_strategy,
        embed_heading_prefix=settings.embed_heading_prefix,
        resolved_revision=_cached_revision(settings, model_id),
    )
    collection = embedding_collection_name(
        settings.chroma_collection, model_id, fingerprint
    )
    return model_id, collection, source


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
    revision = _cached_revision(settings, model_id)
    fingerprint = index_config_fingerprint(
        chunker, embedder, settings.embed_heading_prefix, revision
    )
    service = RetrievalService(
        notes=notes,
        chunker=chunker,
        embedder=embedder,
        store=ChromaVectorStore(settings.chroma_dir, collection, create_if_missing=True),
        embed_heading_prefix=settings.embed_heading_prefix,
        resolved_revision=revision,
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
    """Report the rebuild plan and whether the existing index matches the configuration.

    Opens the collection without creating one: a dry run must not leave an empty
    collection behind that would then look like a valid (but empty) index.
    """
    from noteagent.retrieval.vector_store import CollectionMissingError, LEGACY_FINGERPRINT

    chunker = MarkdownChunker(strategy=settings.chunk_strategy)
    try:
        store = ChromaVectorStore(
            settings.chroma_dir, collection, create_if_missing=False
        )
    except CollectionMissingError:
        store = None
    wanted = index_config_fingerprint(
        chunker,
        build_embedder(
            model_id,
            settings.embedding_cache_dir,
            local_files_only=True,
        ),
        settings.embed_heading_prefix,
        _cached_revision(settings, model_id),
    )
    total = 0
    for name in targets:
        chunks = chunker.split_with_metadata(notes.read(name))
        total += len(chunks)
        print(f"would index {name}: {len(chunks)} chunks")
    print(f"notes={len(targets)} chunks={total}")
    if store is None:
        print("stored  fingerprint: (collection 不存在)")
        print("rebuild required: 需要从头建立该 collection（本脚本 --all 或界面「重建并切换」）")
        return 0
    stored = store.stored_config()
    print(f"stored  fingerprint: {stored or '(none)'}")
    print(f"current fingerprint: {wanted}")
    fields = store.stored_config_fields()
    if fields is not None:
        print(f"stored  config     : {fields}")
    if stored == wanted:
        print("rebuild not needed: 配置一致")
        return 0
    if stored == LEGACY_FINGERPRINT:
        print("rebuild required: 现有索引建立时还没有指纹记录，无法核验身份")
    else:
        print("rebuild required: 现有索引与当前配置不符")
    print("重建：在界面点「重建并切换」，或对每篇跑一次本脚本（--all）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
