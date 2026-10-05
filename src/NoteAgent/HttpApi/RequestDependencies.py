"""Request-scoped runtime leases and same-origin checks shared by HTTP endpoints."""

import logging
from collections.abc import Iterator
from urllib.parse import urlsplit
from fastapi import HTTPException, Request
from NoteAgent.ApplicationFlows.ModelRuntime.ModelRuntime import ModelRuntimeService, RuntimeSnapshot

_logger = logging.getLogger(__name__)

def get_model_runtime(request: Request) -> ModelRuntimeService:
    """The model runtime service owned by the app container."""
    return request.app.state.container.model_runtime


async def chat_lease(request: Request) -> Iterator[RuntimeSnapshot]:
    """Hold a chat lease for the whole SSE response.

    Released when the response finishes, including a client disconnect. Used as a
    dependency so a maintenance window is refused before anything is written.
    """
    with get_model_runtime(request).chat() as snapshot:
        yield snapshot


async def write_lease(request: Request) -> Iterator[RuntimeSnapshot]:
    """Hold a write lease for the whole request."""
    with get_model_runtime(request).write() as snapshot:
        yield snapshot


async def read_lease(request: Request):
    with get_model_runtime(request).read() as snapshot:
        yield snapshot


def require_same_origin(request: Request) -> None:
    """Refuse a cross-site Origin on credential-bearing writes.

    This app has no login, so any website could otherwise POST to localhost. Requests
    without an Origin header (curl, the test client, server-side scripts) are allowed on
    purpose: they are not subject to browser cross-site rules in the first place.
    """
    origin = request.headers.get("origin")
    if not origin:
        return
    host = request.headers.get("host")
    if not host or urlsplit(origin).netloc != host:
        _logger.warning("refused cross-origin model settings call origin=%s host=%s", origin, host)
        raise HTTPException(status_code=403, detail="cross-origin request refused")
