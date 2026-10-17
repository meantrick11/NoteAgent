"""Durable database-backed parser worker; ready fragments publish atomically."""
from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import delete, select, update

from NoteAgent.Modules.Sources.Domain.Po.SourceFileModels import SourceFile, SourceFragment
from NoteAgent.Modules.Sources.Parser.SourceFileParsers import ParseError, Vision, parse_source
from NoteAgent.Modules.Sources.Service.SourceFileService import SourceFileService

logger = logging.getLogger(__name__)


class SourceFileWorker:
    def __init__(self, service: SourceFileService, vision_factory: Callable[[SourceFile], Vision | None] | None = None):
        self.service = service
        self.vision_factory = vision_factory

    def reset_incomplete(self) -> None:
        """At process startup, reclaim tasks left mid-parse by the prior process."""
        with self.service.sessions.begin() as session:
            session.execute(update(SourceFile).where(SourceFile.status == "parsing").values(status="queued"))

    def run_once(self) -> bool:
        with self.service.sessions.begin() as session:
            source = session.scalar(
                select(SourceFile).where(SourceFile.status == "queued")
                .order_by(SourceFile.created_at).with_for_update(skip_locked=True).limit(1)
            )
            if source is None:
                return False
            source.status = "parsing"
            source_id = source.id
            media = source.media_type
            session.flush()
            session.expunge(source)
        try:
            vision = self.vision_factory(source) if self.vision_factory else None
            parts = parse_source(media, self.service.store.read(str(source_id)), vision=vision)
        except Exception as exc:
            # Keep only an error category in logs; do not log extracted text or image data.
            category = type(exc).__name__
            with self.service.sessions.begin() as session:
                current = session.get(SourceFile, source_id)
                if current is not None and current.status != "deleted":
                    current.status = "failed"
                    current.error = str(exc) if isinstance(exc, ParseError) else category
            logger.warning("source parse failed id=%s category=%s", source_id, category)
            return True
        with self.service.sessions.begin() as session:
            current = session.get(SourceFile, source_id)
            if current is None or current.status == "deleted":
                return True
            session.execute(delete(SourceFragment).where(SourceFragment.source_file_id == source_id))
            for index, part in enumerate(parts):
                session.add(SourceFragment(source_file_id=source_id, ordinal=index, locator=part.locator, text=part.text))
            current.status = "ready"
            current.error = None
        logger.info("source parse ready id=%s fragments=%s", source_id, len(parts))
        return True
