"""Built-in provider specs and a registry implementing ProviderCatalogPort.

Only adapters whose LangChain integration is installed belong here. Adding a provider
means installing its integration and adding one spec; no schema migration is needed.
"""

from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import ProviderNotFoundError
from NoteAgent.Modules.Models.Domain.Vo.ProviderSpec import ProviderSpec

BUILTIN_PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        id="deepseek",
        label="DeepSeek",
        langchain_provider="deepseek",
        auth_modes=("api_key",),
    ),
    ProviderSpec(
        id="openai",
        label="OpenAI",
        langchain_provider="openai",
        auth_modes=("api_key",),
    ),
    ProviderSpec(
        id="openai-compatible",
        label="OpenAI 兼容服务",
        langchain_provider="openai",
        base_url_required=True,
        auth_modes=("api_key", "none"),
    ),
)


class ProviderRegistry:
    """Resolve provider ids against a fixed set of specs."""

    def __init__(self, specs: tuple[ProviderSpec, ...] = BUILTIN_PROVIDER_SPECS):
        self._specs = {spec.id: spec for spec in specs}

    def resolve(self, provider_id: str) -> ProviderSpec:
        """Return the spec or raise a user-visible domain error."""
        spec = self._specs.get(provider_id)
        if spec is None:
            available = "、".join(sorted(self._specs))
            raise ProviderNotFoundError(
                f"未知的 Provider「{provider_id}」；当前支持：{available}"
            )
        return spec

    def list_specs(self) -> list[ProviderSpec]:
        """All registered specs, in registration order."""
        return list(self._specs.values())
