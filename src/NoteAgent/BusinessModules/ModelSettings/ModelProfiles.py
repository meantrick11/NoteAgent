"""Rules for merging submitted model settings with existing stored credentials."""

from pydantic import SecretStr, ValidationError
from NoteAgent.BusinessModules.ModelSettings.ModelContracts import ChatProfile, ChatProfileIn
from NoteAgent.BusinessModules.ModelSettings.ModelErrors import InvalidProfileError

def merge_candidate(
    candidate: ChatProfileIn,
    existing: ChatProfile | None,
    *,
    profile_id: str,
) -> ChatProfile:
    """Combine a submitted form with the stored profile it edits.

    An omitted key means "keep what is stored"; an explicit clear wins over
    everything. The mask shown in the UI is never accepted as a real key because the
    stored value is what we keep, not the submitted placeholder. ``profile_id`` is
    decided by the caller (server-minted on create, the URL id on update), so the
    body can never choose an identity of its own.
    """
    provided = candidate.provided_api_key()
    moved_off_env = (
        existing is not None
        and existing.credential_source == "env"
        and existing.provider == "deepseek"
        and candidate.provider != "deepseek"
    )
    if candidate.clear_api_key:
        api_key, source = SecretStr(""), "ui"
    elif provided is not None:
        api_key, source = SecretStr(provided), "ui"
    elif moved_off_env:
        # .env 里的 Key 属于 DeepSeek 默认配置，不能跟着换到别的供应商；
        # 那种情况下它会指向一个根本无法认证的端点。
        api_key, source = SecretStr(""), "ui"
    elif existing is not None:
        api_key, source = existing.api_key, existing.credential_source
    else:
        api_key, source = SecretStr(""), "ui"

    if candidate.auth_mode == "api_key" and not api_key.get_secret_value().strip():
        if moved_off_env:
            raise InvalidProfileError(
                "环境变量里的 Key 只属于原来的 DeepSeek 配置；换用其它供应商请填写 API Key，"
                "或明确勾选「该服务无需 API Key」"
            )
        raise InvalidProfileError("该配置要求 API Key，但当前没有可用凭据")

    try:
        return ChatProfile(
            id=profile_id,
            label=candidate.label,
            provider=candidate.provider,
            model=candidate.model,
            base_url=candidate.base_url,
            api_key=api_key,
            auth_mode=candidate.auth_mode,
            context_window=candidate.context_window,
            credential_source=source,
        )
    except ValidationError as exc:
        raise InvalidProfileError(f"配置内容不合法：{exc.error_count()} 处问题") from exc
