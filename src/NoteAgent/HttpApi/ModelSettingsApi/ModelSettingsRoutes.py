"""模型设置 HTTP 层：参数校验、调用 service、映射状态码。

不装配模型、不扫描文件；凭据只在请求体内出现过一次，响应与日志都不得回显。本模块同时
导出请求级租约依赖（chat_lease / write_lease），供 chat 与 notes 路由统一接入门禁。
"""

from NoteAgent.HttpApi.RequestDependencies import get_model_runtime, require_same_origin

import logging

from fastapi import APIRouter, Depends, Request, Response

from NoteAgent.HttpApi.ModelSettingsApi.ModelSettingsSchemas import ChatActivateIn, ChatProfileIn, ChatProfileOut, ChatProfileWriteIn, ChatTestOut, EmbeddingCandidateOut, EmbeddingSwitchIn, EmbeddingSwitchOut, EmbeddingJobRecord, ModelSettingsStatusOut

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model-settings", tags=["model-settings"])


@router.get("", response_model=ModelSettingsStatusOut)
async def get_model_settings(request: Request) -> ModelSettingsStatusOut:
    """Current revision, profiles, active choices, and any running job."""
    return get_model_runtime(request).status()


@router.post(
    "/chat/test",
    response_model=ChatTestOut,
    dependencies=[Depends(require_same_origin)],
)
async def test_chat_profile(body: ChatProfileIn, request: Request) -> ChatTestOut:
    """Probe a candidate's streaming and tool-calling support. Saves nothing."""
    return await get_model_runtime(request).test_chat_profile(body)


@router.post(
    "/chat/profiles",
    response_model=ChatProfileOut,
    status_code=201,
    dependencies=[Depends(require_same_origin)],
)
async def create_chat_profile(body: ChatProfileWriteIn, request: Request) -> ChatProfileOut:
    """Store a new profile. Saving never activates it."""
    return get_model_runtime(request).save_chat_profile(body, profile_id=None)


@router.put(
    "/chat/profiles/{profile_id}",
    response_model=ChatProfileOut,
    dependencies=[Depends(require_same_origin)],
)
async def update_chat_profile(
    profile_id: str, body: ChatProfileWriteIn, request: Request
) -> ChatProfileOut:
    """Update a stored profile. The active profile must go through activate instead."""
    return get_model_runtime(request).save_chat_profile(body, profile_id=profile_id)


@router.delete(
    "/chat/profiles/{profile_id}",
    status_code=204,
    dependencies=[Depends(require_same_origin)],
)
async def delete_chat_profile(
    profile_id: str, expected_revision: int, request: Request
) -> Response:
    """Delete a stored profile (and its credential). The active one is protected."""
    get_model_runtime(request).delete_chat_profile(
        profile_id=profile_id, expected_revision=expected_revision
    )
    return Response(status_code=204)


@router.post(
    "/chat/activate",
    response_model=ChatProfileOut,
    dependencies=[Depends(require_same_origin)],
)
async def activate_chat_profile(body: ChatActivateIn, request: Request) -> ChatProfileOut:
    """Verify, save, and enable one profile as a single transaction."""
    return await get_model_runtime(request).activate_chat(body)


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
        for candidate in get_model_runtime(request).list_embedding_candidates()
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
    unchanged, job = get_model_runtime(request).switch_embedding(
        model_id=body.model_id, expected_revision=body.expected_revision
    )
    if unchanged:
        response.status_code = 200
        return EmbeddingSwitchOut(unchanged=True)
    return EmbeddingSwitchOut(unchanged=False, job=job)


@router.get("/jobs/{job_id}", response_model=EmbeddingJobRecord)
async def get_job(job_id: str, request: Request) -> EmbeddingJobRecord:
    """Progress of one rebuild job, live or restored after a restart."""
    return get_model_runtime(request).get_job(job_id)
