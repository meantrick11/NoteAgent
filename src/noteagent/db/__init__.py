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
    "load_all_models",
]


def load_all_models() -> None:
    """Import every ORM module so ``Base.metadata`` is complete.

    Imported lazily: ``conversations.models`` depends on this module, so importing it
    at package load time would create a cycle.
    """
    import noteagent.conversations.models  # noqa: F401
