"""Ports used by model configuration and activation services.

They keep the Models module independent from bootstrap, Chat internals and Retrieval
internals while still expressing the collaboration points explicitly.
"""

from typing import Protocol

from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig


class AgentAssemblerPort(Protocol):
    """Build the chat agent for one model and the current retrieval object."""

    def build_agent(self, *, model: ModelConfig, retrieval: object | None) -> object: ...


class RetrievalProviderPort(Protocol):
    """Return the current retrieval object without exposing its concrete type."""

    def __call__(self) -> object | None: ...


class RuntimePublisherPort(Protocol):
    """Publish a committed activation into the live snapshot."""

    def publish(
        self, *, model: ModelConfig, agent: object, retrieval: object | None
    ) -> None: ...
