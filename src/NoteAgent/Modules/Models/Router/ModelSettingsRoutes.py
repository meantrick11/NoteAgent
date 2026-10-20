"""Model settings HTTP layer: configuration, providers, activation and status.

No credential is ever echoed; every write uses the model row's own revision.
"""

import logging

from fastapi import APIRouter, Depends, Request, Response

from NoteAgent.Common.Http.RequestDependencies import (
    get_model_activation,
    get_model_configs,
    get_model_runtime,
    get_providers,
    require_same_origin,
)
from NoteAgent.Modules.Models.Domain.Dto.ModelSettingsSchemas import (
    CapabilityChangeIn,
    ModelActivateIn,
    ModelConfigIn,
    ModelConfigOut,
    ModelConfigWriteIn,
    ModelSettingsStatusOut,
    ModelTestOut,
    ProviderSpecOut,
    merge_model_input,
    to_model_out,
    to_provider_out,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelContracts import (
    EmbeddingCandidateOut,
    EmbeddingJobRecord,
    EmbeddingSwitchIn,
    EmbeddingSwitchOut,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import (
    ActiveModelProtectedError,
    ProtocolUnsupportedError,
)

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model-settings", tags=["model-settings"])


@router.get("", response_model=ModelSettingsStatusOut)
async def get_model_settings(request: Request) -> ModelSettingsStatusOut:
    """Model list, active model and the independent retrieval state."""
    return get_model_runtime(request).status()


@router.get("/providers", response_model=list[ProviderSpecOut])
async def list_providers(request: Request) -> list[ProviderSpecOut]:
    """Provider specs used to render the settings form."""
    return [to_provider_out(spec) for spec in get_providers(request).list_specs()]


@router.post(
    "/models",
    response_model=ModelConfigOut,
    status_code=201,
    dependencies=[Depends(require_same_origin)],
)
async def create_model(body: ModelConfigIn, request: Request) -> ModelConfigOut:
    """Save a new model configuration; saving never activates it."""
    config = merge_model_input(body, None, model_id="")
    created = get_model_configs(request).create(config)
    return to_model_out(created)


@router.put(
    "/models/{model_id}",
    response_model=ModelConfigOut,
    dependencies=[Depends(require_same_origin)],
)
async def update_model(
    model_id: str, body: ModelConfigWriteIn, request: Request
) -> ModelConfigOut:
    """Update a non-active model; the active one must use the activation flow."""
    configs = get_model_configs(request)
    existing = configs.get_model(model_id)
    if existing.is_active:
        raise ActiveModelProtectedError("当前启用的模型不能直接编辑，请使用「保存并启用」")
    config = merge_model_input(body, existing, model_id=model_id)
    updated = configs.update(model_id, body.expected_revision, config)
    return to_model_out(updated)


@router.delete(
    "/models/{model_id}",
    status_code=204,
    dependencies=[Depends(require_same_origin)],
)
async def delete_model(
    model_id: str, expected_revision: int, request: Request
) -> Response:
    """Delete a non-active model and its capability rows."""
    get_model_configs(request).delete(model_id, expected_revision)
    return Response(status_code=204)


@router.post(
    "/models/{model_id}/test",
    response_model=ModelTestOut,
    dependencies=[Depends(require_same_origin)],
)
async def test_model(
    model_id: str, request: Request, body: ModelConfigIn | None = None
) -> ModelTestOut:
    """Probe a stored model, or an edited form payload, without saving."""
    configs = get_model_configs(request)
    existing = configs.get_model(model_id)
    config = merge_model_input(body, existing, model_id=model_id) if body else existing
    result = await configs.test(config)
    return ModelTestOut(
        verified=result.verified,
        streaming=result.streaming,
        tool_calling=result.tool_calling,
        message=result.message,
    )


@router.post(
    "/models/{model_id}/activate",
    response_model=ModelConfigOut,
    dependencies=[Depends(require_same_origin)],
)
async def activate_model(
    model_id: str, body: ModelActivateIn, request: Request
) -> ModelConfigOut:
    """Verify, optionally save, atomically switch active, then publish the snapshot."""
    configs = get_model_configs(request)
    existing = configs.get_model(model_id)
    config = merge_model_input(body.config, existing, model_id=model_id) if body.config else None
    saved = await get_model_activation(request).activate(
        model_id, body.expected_revision, config
    )
    return to_model_out(saved)


@router.post(
    "/models/{model_id}/capabilities/{capability}/verify",
    response_model=ModelConfigOut,
    dependencies=[Depends(require_same_origin)],
)
async def verify_capability(
    model_id: str, capability: str, body: CapabilityChangeIn, request: Request
) -> ModelConfigOut:
    """Probe and persist capability evidence."""
    configs = get_model_configs(request)
    runtime = get_model_runtime(request)
    try:
        saved = await configs.verify_capability(model_id, capability, body.expected_revision)
    except ProtocolUnsupportedError:
        runtime.sync_model(configs.get_model(model_id))
        raise
    runtime.sync_model(saved)
    return to_model_out(saved)


@router.delete(
    "/models/{model_id}/capabilities/{capability}",
    response_model=ModelConfigOut,
    dependencies=[Depends(require_same_origin)],
)
async def disable_capability(
    model_id: str, capability: str, expected_revision: int, request: Request
) -> ModelConfigOut:
    """Pause text or vision; vision evidence is cleared and must be reprobed."""
    saved = get_model_configs(request).disable_capability(
        model_id, capability, expected_revision
    )
    get_model_runtime(request).sync_model(saved)
    return to_model_out(saved)


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
