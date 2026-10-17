"""Database queries for source metadata; callers own their write transactions."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from NoteAgent.BusinessModules.SourceFiles.SourceFileModels import SourceFile


class SourceFileRepository:
    def __init__(self, sessions: sessionmaker[Session]):
        self.sessions = sessions

    def get(self, source_id: str) -> SourceFile | None:
        with self.sessions() as session:
            source = session.get(SourceFile, uuid.UUID(source_id))
            if source is not None:
                session.expunge(source)
            return source

    def list(self) -> list[SourceFile]:
        with self.sessions() as session:
            sources = list(session.scalars(select(SourceFile).order_by(SourceFile.created_at.desc())))
            for source in sources:
                session.expunge(source)
            return sources
