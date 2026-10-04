"""Import legacy conversations into the checkpoint backend.

Read-only unless ``--apply`` is passed. Output is aggregate counts only: it never
prints message bodies or connection credentials.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from noteagent.bootstrap.settings import Settings
from noteagent.conversations.checkpoints import CheckpointRuntime, postgres_uri
from noteagent.conversations.migration import ConversationMigrator
from noteagent.conversations.service import ConversationService
from noteagent.db import create_engine_from_url, create_session_factory

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
_logger = logging.getLogger("migrate_conversations")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="count without writing")
    mode.add_argument("--apply", action="store_true", help="perform the import")
    parser.add_argument("--conversation-id", default=None, help="import a single conversation")
    return parser.parse_args(argv)


async def run(argv: list[str], *, settings: Settings | None = None) -> dict:
    """Execute the CLI; returns aggregate counts (no message content)."""
    args = parse_args(argv)
    settings = settings or Settings()
    if not settings.database_url.strip():
        raise SystemExit("DATABASE_URL is required")

    engine = create_engine_from_url(settings.database_url)
    runtime = CheckpointRuntime.from_conn_string(postgres_uri(settings.database_url))
    await runtime.open()
    try:
        service = ConversationService(create_session_factory(engine), runtime)
        migrator = ConversationMigrator(create_session_factory(engine), service)

        if args.apply:
            report = await migrator.import_all(conversation_id=args.conversation_id)
            result = {
                "mode": "apply",
                "scanned": report.scanned,
                "imported": report.imported,
                "already_imported": report.already_imported,
                "failed": report.failed,
                "skipped": report.skipped,
                "messages": report.messages,
            }
        else:
            report = migrator.dry_run(conversation_id=args.conversation_id)
            result = {
                "mode": "dry-run",
                "scanned": report.scanned,
                "importable": report.importable,
                "skipped": report.skipped,
                "messages": report.messages,
            }

        for conversation_id, reason in report.errors:
            result.setdefault("errors", []).append(
                {"conversation_id": conversation_id, "reason": reason}
            )
        _logger.info("migration %s", result)
        return result
    finally:
        await runtime.close()
        engine.dispose()


def main(argv: list[str] | None = None) -> int:
    asyncio.run(run(list(argv if argv is not None else sys.argv[1:])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
