"""Index one Markdown note from NOTES_DIR into Chroma."""

from __future__ import annotations

import argparse
import sys

from noteagent.bootstrap.settings import Settings
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import SentenceTransformerEmbedder
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore


def main(argv: list[str] | None = None) -> int:
    """Index one notes/ file into Chroma and print the chunk count."""
    parser = argparse.ArgumentParser(description="Index a note file into Chroma")
    parser.add_argument("file_name", help="Markdown file name under notes/, e.g. Agent.md")
    args = parser.parse_args(argv)

    settings = Settings()
    print(
        "embedding",
        settings.embedding_model,
        "cache",
        settings.embedding_cache_dir,
        "local_only",
        settings.embedding_local_files_only,
    )
    notes = FileNoteRepository(settings.notes_dir)
    service = RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(),
        embedder=SentenceTransformerEmbedder(
            settings.embedding_model,
            cache_folder=settings.embedding_cache_dir,
            local_files_only=settings.embedding_local_files_only,
        ),
        store=ChromaVectorStore(settings.chroma_dir, settings.chroma_collection),
    )
    count = service.index_note(args.file_name)
    print(f"indexed {args.file_name}: {count} chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
