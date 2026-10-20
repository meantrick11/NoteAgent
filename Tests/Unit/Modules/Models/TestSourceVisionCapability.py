"""旧的人工 vision 标签不授予图片解析权限。"""

from types import SimpleNamespace

import pytest

from NoteAgent.AppBootstrap.SourceVision import vision_factory
from NoteAgent.Modules.Models.Domain.Vo.ModelContracts import ChatProfile, StoredModelSettings
from NoteAgent.Modules.Sources.Parser.SourceFileParsers import ParseError


def test_unverified_legacy_vision_cannot_parse_image():
    profile = ChatProfile(id="p", label="旧配置", provider="deepseek", model="m",
                          capabilities=["text", "vision"])
    document = StoredModelSettings(revision=3, chat_profiles=[profile])
    store = SimpleNamespace(load_effective=lambda settings: document)
    source = SimpleNamespace(media_type="image/png", parse_profile_id="p", parse_profile_revision=3)
    with pytest.raises(ParseError, match="已验证 vision"):
        vision_factory(source, store, object())
