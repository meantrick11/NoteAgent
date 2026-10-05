"""Recovery HTTP layer: preview, start, job status and retry.

Writes carry the same-origin dependency like every other credential-bearing write; the
client never supplies paths or commits as recovery authority — the server's persisted
preview plan is the only source of truth.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from NoteAgent.HttpApi.RequestDependencies import require_same_origin
from NoteAgent.HttpApi.ConversationRecoveryApi.ConversationRecoverySchemas import JobOut, PreviewIn, PreviewOut, RecoveryRetryIn, RecoveryStartIn

_logger = logging.getLogger(__name__)

router = APIRouter()


def _coordinator(request: Request):
    coordinator = getattr(request.app.state.container, "recovery", None)
    if coordinator is None:
        raise HTTPException(status_code=503, detail="recovery is unavailable")
    return coordinator




@router.post(
    "/conversations/{conversation_id}/recoveries/preview",
    response_model=PreviewOut,
    dependencies=[Depends(require_same_origin)],
)
async def preview_recovery(
    conversation_id: str,
    body: Annotated[PreviewIn, Body()],
    request: Request,
) -> PreviewOut:
    """Build a pure preview of what a rollback of one edited message would change."""
    preview_id, plan = await _coordinator(request).preview(
        conversation_id, body.message_id, body.edited_content,
        expected_revision=body.expected_revision,
    )
    return PreviewOut(
        preview_id=preview_id,
        conversation_id=conversation_id,
        can_apply=plan.can_apply,
        requires_confirmation=plan.requires_confirmation,
        file_changes=[c for c in plan.as_dict()["file_changes"]],
        folder_changes=list(plan.as_dict()["folder_changes"]),
        conflicts=list(plan.as_dict()["conflicts"]),
        affected_messages=list(plan.affected_messages),
        state_revision=plan.state_revision,
        workspace_seq=plan.workspace_seq,
        content_digest=plan.content_digest,
        expires_at=plan.expires_at,
    )


@router.post(
    "/conversations/{conversation_id}/recoveries",
    response_model=JobOut,
    dependencies=[Depends(require_same_origin)],
)
async def start_recovery(
    conversation_id: str,
    body: Annotated[RecoveryStartIn, Body()],
    request: Request,
) -> JobOut:
    """Start (or reuse) a recovery for a confirmed preview."""
    job = await _coordinator(request).start(
        body.preview_id, body.edited_content,
        body.confirmed_file_changes, body.operation_id,
        conversation_id=conversation_id,
    )
    if job.get("conversation_id") not in (None, conversation_id):
        raise HTTPException(status_code=404, detail="recovery not found")
    return JobOut(**job)


@router.get("/recoveries/{job_id}", response_model=JobOut)
async def get_recovery(job_id: str, request: Request) -> JobOut:
    """Job progress; available during maintenance so a client can keep polling."""
    return JobOut(**_coordinator(request).get(job_id))


@router.post(
    "/recoveries/{job_id}/retry",
    response_model=JobOut,
    dependencies=[Depends(require_same_origin)],
)
async def retry_recovery(
    job_id: str,
    body: Annotated[RecoveryRetryIn, Body()],
    request: Request,
) -> JobOut:
    """Continue the same persisted plan after a failure."""
    return JobOut(**await _coordinator(request).retry(job_id, body.operation_id))
