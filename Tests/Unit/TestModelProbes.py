"""Capability failures must remain reportable when a model lacks required features."""

from types import SimpleNamespace

import pytest

from NoteAgent.BusinessModules.ModelSettings.ModelProbes import probe_model


class UnsupportedModel:
    """A client that accepts requests but emits neither text nor tool calls."""

    def bind_tools(self, tools):
        return self

    async def astream(self, messages):
        yield SimpleNamespace(content="", tool_calls=[], tool_call_chunks=[])


@pytest.mark.asyncio
async def test_unsupported_capabilities_return_a_diagnostic():
    result = await probe_model(UnsupportedModel())
    assert result.verified is False
    assert result.streaming is False
    assert result.tool_calling is False
    assert result.message
