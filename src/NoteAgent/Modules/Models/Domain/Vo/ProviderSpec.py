"""Provider adapter specification and catalog port.

The provider vocabulary is code-registered, not a domain enum tied to one vendor.
Adding a provider means installing its LangChain integration and registering a
spec; the database only stores the spec id.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

AuthMode = Literal["api_key", "none"]


@dataclass(frozen=True)
class ProviderSpec:
    """Everything the domain and client factory need to know about one provider."""

    id: str
    label: str
    langchain_provider: str
    default_base_url: str = ""
    base_url_required: bool = False
    auth_modes: tuple[AuthMode, ...] = ("api_key",)

    @property
    def supports_model_listing(self) -> bool:
        """Reserved for providers that later expose model discovery."""
        return False


class ProviderCatalogPort(Protocol):
    """Resolve provider ids and list their specs for the settings UI."""

    def resolve(self, provider_id: str) -> ProviderSpec: ...

    def list_specs(self) -> list[ProviderSpec]: ...
