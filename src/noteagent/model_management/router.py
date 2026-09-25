"""模型设置 HTTP 层：参数校验、调用 service、映射状态码。

不装配模型、不扫描文件；凭据只在请求体内出现过一次，响应与日志都不得回显。本模块同时
导出请求级租约依赖（chat_lease / write_lease），供 chat 与 notes 路由统一接入门禁。
"""

import logging
from collections.abc import Iterator
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from noteagent.model_management.schemas import (
    ChatActivateIn,
    ChatProfileIn,
    ChatProfileOut,
    ChatProfileWriteIn,
    ChatTestOut,
    EmbeddingCandidateOut,
    EmbeddingSwitchIn,
    EmbeddingSwitchOut,
    EmbeddingJobRecord,
    ModelSettingsStatusOut,
)
from noteagent.model_management.service import (
    ModelManagementError,
    ModelRuntimeService,
    RuntimeSnapshot,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model-settings", tags=["model-settings"])


def _runtime(request: Request) -> ModelRuntimeService:
    """The model runtime service owned by the app container."""
    return request.app.state.container.model_runtime


def chat_lease(request: Request) -> Iterator[RuntimeSnapshot]:
    """Hold a chat lease for the whole SSE response.

    Released when the response finishes, including a client disconnect. Used as a
    dependency so a maintenance window is refused before anything is written.
    """
    with _runtime(request).chat() as snapshot:
        yield snapshot


def write_lease(request: Request) -> Iterator[RuntimeSnapshot]:
    """Hold a write lease for the whole request."""
    with _runtime(request).write() as snapshot:
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


def model_management_error_handler(
    request: Request, exc: ModelManagementError
) -> JSONResponse:
    """Unified error envelope: code / message / retryable."""
    _logger.warning(
        "model settings error path=%s code=%s message=%s",
        request.url.path,
        exc.code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status,
        content={"code": exc.code, "message": exc.message, "retryable": exc.retryable},
    )


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Rebuild 422 details without echoing the submitted values.

    Pydantic's errors include the offending ``input``, and a rejected profile body may
    contain an API key; only the location and the message are safe to return.
    """
    fields = [
        {
            "loc": [str(part) for part in error.get("loc", ())],
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        for error in exc.errors()
    ]
    first = fields[0] if fields else {"loc": [], "msg": "请求参数不合法"}
    return JSONResponse(
        status_code=422,
        content={
            "code": "invalid_request",
            "message": f"{'.'.join(first['loc']) or '请求体'}：{first['msg']}",
            "retryable": False,
            "fields": fields,
        },
    )


@router.get("", response_model=ModelSettingsStatusOut)
async def get_model_settings(request: Request) -> ModelSettingsStatusOut:
    """Current revision, profiles, active choices, and any running job."""
    return _runtime(request).status()


@router.post(
    "/chat/test",
    response_model=ChatTestOut,
    dependencies=[Depends(require_same_origin)],
)
async def test_chat_profile(body: ChatProfileIn, request: Request) -> ChatTestOut:
    """Probe a candidate's streaming and tool-calling support. Saves nothing."""
    return await _runtime(request).test_chat_profile(body)


@router.post(
    "/chat/profiles",
    response_model=ChatProfileOut,
    status_code=201,
    dependencies=[Depends(require_same_origin)],
)
async def create_chat_profile(body: ChatProfileWriteIn, request: Request) -> ChatProfileOut:
    """Store a new profile. Saving never activates it."""
    return _runtime(request).save_chat_profile(body, profile_id=None)


@router.put(
    "/chat/profiles/{profile_id}",
    response_model=ChatProfileOut,
    dependencies=[Depends(require_same_origin)],
)
async def update_chat_profile(
    profile_id: str, body: ChatProfileWriteIn, request: Request
) -> ChatProfileOut:
    """Update a stored profile. The active profile must go through activate instead."""
    return _runtime(request).save_chat_profile(body, profile_id=profile_id)


@router.post(
    "/chat/activate",
    response_model=ChatProfileOut,
    dependencies=[Depends(require_same_origin)],
)
async def activate_chat_profile(body: ChatActivateIn, request: Request) -> ChatProfileOut:
    """Verify, save, and enable one profile as a single transaction."""
    return await _runtime(request).activate_chat(body)


@router.get("/embeddings", response_model=list[EmbeddingCandidateOut])
async def list_embeddings(request: Request) -> list[EmbeddingCandidateOut]:
    """Supported local embedding models with their real availability."""
    return [
        EmbeddingCandidateOut(
            model_id=candidate.model_id,
            label=candidate.label,
            availability=candidate.availability,
            reason=candidate.reason,
            active=candidate.active,
        )
        for candidate in _runtime(request).list_embedding_candidates()
    ]


@router.post(
    "/embedding/switch",
    response_model=EmbeddingSwitchOut,
    status_code=202,
    dependencies=[Depends(require_same_origin)],
)
async def switch_embedding(
    body: EmbeddingSwitchIn, request: Request, response: Response
) -> EmbeddingSwitchOut:
    """Start a rebuild into a new collection. 202 means started, not switched."""
    unchanged, job = _runtime(request).switch_embedding(
        model_id=body.model_id, expected_revision=body.expected_revision
    )
    if unchanged:
        response.status_code = 200
        return EmbeddingSwitchOut(unchanged=True)
    return EmbeddingSwitchOut(unchanged=False, job=job)


@router.get("/jobs/{job_id}", response_model=EmbeddingJobRecord)
async def get_job(job_id: str, request: Request) -> EmbeddingJobRecord:
    """Progress of one rebuild job, live or restored after a restart."""
    return _runtime(request).get_job(job_id)
