"""Per-graph-step file authorization and actual-read evidence."""
from contextvars import ContextVar

authorized_source_ids: ContextVar[set[str]] = ContextVar("authorized_source_ids", default=set())
read_source_ids: ContextVar[set[str] | None] = ContextVar("read_source_ids", default=None)
