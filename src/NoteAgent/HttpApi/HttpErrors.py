"""Convert business errors into the existing HTTP response contracts."""

import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from NoteAgent.BusinessModules.ModelSettings.ModelErrors import ModelManagementError
from NoteAgent.ApplicationFlows.ConversationRecovery.RecoveryCoordinator import RecoveryError
from NoteAgent.TechnicalSupport.NoteAccessControl.NoteAccessGate import WorkspaceBusy

_logger = logging.getLogger(__name__)

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


def recovery_error_handler(request: Request, exc: RecoveryError) -> JSONResponse:
    """Unified error envelope: code / message / retryable."""
    _logger.warning(
        "recovery error path=%s code=%s message=%s",
        request.url.path, exc.code, exc.message,
    )
    return JSONResponse(
        status_code=exc.status,
        content={"code": exc.code, "message": exc.message, "retryable": exc.retryable},
    )

async def workspace_busy_handler(request: Request, exc: WorkspaceBusy) -> JSONResponse:
    """Return the existing retryable conflict response for a busy workspace."""
    return JSONResponse(status_code=409, content={"code": "workspace_busy", "message": str(exc), "retryable": True})


def register_exception_handlers(app: FastAPI) -> None:
    """Register all public exception translations in one place."""
    app.add_exception_handler(ModelManagementError, model_management_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(RecoveryError, recovery_error_handler)
    app.add_exception_handler(WorkspaceBusy, workspace_busy_handler)
