"""Model configuration and provider errors, independent of HTTP and runtime assembly."""

from openai import APIConnectionError, APIStatusError, APITimeoutError, AuthenticationError

class ModelManagementError(RuntimeError):
    """模型管理领域错误；HTTP 层按 status/code 映射成统一错误结构。"""

    status = 400
    code = "invalid_request"
    retryable = False

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidProfileError(ModelManagementError):
    """The submitted profile cannot be used (missing key, unusable field, ...)."""

    status = 422
    code = "invalid_profile"


class RevisionConflictError(ModelManagementError):
    """The caller's expected_revision is stale."""

    status = 409
    code = "revision_conflict"
    retryable = True


class BusyError(ModelManagementError):
    """The app is inside a maintenance window, or an operation is in flight."""

    status = 409
    code = "busy"
    retryable = True


class ProfileNotFoundError(ModelManagementError):
    """Unknown chat profile id."""

    status = 404
    code = "profile_not_found"


class JobNotFoundError(ModelManagementError):
    """Unknown rebuild job id."""

    status = 404
    code = "job_not_found"


class ModelUnavailableError(ModelManagementError):
    """The requested embedding model is not usable locally."""

    status = 422
    code = "model_unavailable"


class UnknownModelError(ModelManagementError):
    """The requested embedding model id is not in the supported catalog."""

    status = 404
    code = "model_not_found"


class ModelProbeFailedError(ModelManagementError):
    """The chat service refused the request or could not be reached."""

    status = 502
    code = "probe_failed"
    retryable = True


class ModelProbeTimeoutError(ModelManagementError):
    """The chat service did not answer inside the probe timeout."""

    status = 504
    code = "probe_timeout"
    retryable = True


class ProtocolUnsupportedError(ModelManagementError):
    """The chat service answered but cannot serve this app's protocol needs."""

    status = 502
    code = "protocol_unsupported"


class RepairRequiredError(ModelManagementError):
    """The rebuild hit a condition the user has to resolve (external edit, ...)."""

    status = 409
    code = "repair_required"
    retryable = True


class RuntimeConfigurationError(RuntimeError):
    """The persisted choice cannot be turned into a running object at startup.

    Raised from :meth:`ModelRuntimeService.initialize` so the operator sees a single
    actionable line instead of an opaque traceback, and never a silent fallback to a
    different model than the one that was activated.
    """


def _public_error(exc: Exception) -> str:
    """Collapse an exception into a message safe to show and to persist in job state.

    Provider errors may quote an endpoint or a header, so they are replaced by a
    category. Local errors keep their type plus a short message, which is what makes a
    failed rebuild diagnosable.
    """
    if isinstance(exc, ModelManagementError):
        return exc.message
    if isinstance(exc, APITimeoutError):
        return "模型服务响应超时"
    if isinstance(exc, AuthenticationError):
        return "模型服务认证失败，请检查 API Key"
    if isinstance(exc, APIConnectionError):
        return "无法连接模型服务，请检查 Base URL 与网络"
    if isinstance(exc, APIStatusError):
        return f"模型服务返回 HTTP {exc.status_code}"
    message = str(exc).strip().replace("\n", " ")
    return f"{type(exc).__name__}: {message[:200]}"


def _probe_error(exc: Exception) -> ModelManagementError:
    """Classify a probe failure into a public error carrying the right status code."""
    if isinstance(exc, ModelManagementError):
        return exc
    if isinstance(exc, APITimeoutError):
        return ModelProbeTimeoutError("模型服务响应超时（20 秒内没有回复）")
    if isinstance(exc, AuthenticationError):
        return ModelProbeFailedError("模型服务认证失败，请检查 API Key")
    if isinstance(exc, APIConnectionError):
        return ModelProbeFailedError("无法连接模型服务，请检查 Base URL 与网络")
    if isinstance(exc, APIStatusError):
        return ModelProbeFailedError(f"模型服务返回 HTTP {exc.status_code}")
    return ModelProbeFailedError(f"模型调用失败（{type(exc).__name__}）")
