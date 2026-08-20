"""Database package: Base, tables, engine, and session factory.

Contains no HTTP handlers and makes no LLM calls.
"""

from noteagent.db.engine import create_engine_from_url, create_session_factory
from noteagent.db.models import Base, Conversation, Message

__all__ = [
    "Base",
    "Conversation",
    "Message",
    "create_engine_from_url",
    "create_session_factory",
]
