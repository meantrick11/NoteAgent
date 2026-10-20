"""Capability failures must remain reportable when a model lacks required features."""

from types import SimpleNamespace
from itertools import cycle

import pytest

from NoteAgent.Modules.Models.Provider.ModelProbes import probe_model


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


@pytest.mark.asyncio
async def test_vision_probe_requires_correct_image_answer():
    from NoteAgent.Modules.Models.Provider import ModelProbes
    class ImageModel:
        async def ainvoke(self, messages):
            content = messages[0].content
            assert content[1]["type"] == "image_url"
            assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
            return SimpleNamespace(content="wrong")

    assert await ModelProbes.probe_vision(ImageModel()) is False


@pytest.mark.asyncio
async def test_vision_probe_accepts_matching_image_answer(monkeypatch):
    from NoteAgent.Modules.Models.Provider import ModelProbes

    answers = iter(("红蓝绿红蓝绿", "绿蓝红绿蓝红"))
    chosen = cycle(("红", "蓝", "绿", "红", "蓝", "绿", "绿", "蓝", "红", "绿", "蓝", "红"))
    monkeypatch.setattr(ModelProbes.secrets, "choice", lambda options: next(chosen))
    calls = 0
    class ImageModel:
        async def ainvoke(self, messages):
            nonlocal calls
            calls += 1
            return SimpleNamespace(content=next(answers))

    assert await ModelProbes.probe_vision(ImageModel()) is True
    assert calls == 2


@pytest.mark.asyncio
async def test_vision_probe_rejects_wrong_second_answer(monkeypatch):
    from NoteAgent.Modules.Models.Provider import ModelProbes

    chosen = cycle(("红", "蓝", "绿"))
    monkeypatch.setattr(ModelProbes.secrets, "choice", lambda options: next(chosen))
    answers = iter(("红蓝绿红蓝绿", "wrong"))
    class ImageModel:
        async def ainvoke(self, messages):
            return SimpleNamespace(content=next(answers))

    assert await ModelProbes.probe_vision(ImageModel()) is False
