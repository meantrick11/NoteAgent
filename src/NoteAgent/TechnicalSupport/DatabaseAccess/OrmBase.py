"""Shared SQLAlchemy declarative base; table definitions belong to their modules."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Registry shared by all application ORM tables."""
