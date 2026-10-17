"""Vision extraction through an explicitly tagged chat model profile."""
import base64

from langchain_core.messages import HumanMessage

from NoteAgent.AppBootstrap.RuntimeAssembler import api_key_for_profile
from NoteAgent.BusinessModules.ModelSettings.ModelClients import create_chat_model_from_config
from NoteAgent.BusinessModules.ModelSettings.ModelSettingsStorage import ModelSettingsStore
from NoteAgent.BusinessModules.SourceFiles.SourceFileModels import SourceFile
from NoteAgent.BusinessModules.SourceFiles.SourceFileParsers import ParseError, Vision


def vision_factory(source: SourceFile, settings_store: ModelSettingsStore, app_settings) -> Vision | None:
    document = settings_store.load_effective(app_settings)
    profile = document.profile_by_id(source.parse_profile_id)
    if source.media_type == "application/pdf" and (profile is None or "vision" not in profile.capabilities):
        return None
    if source.parse_profile_revision != document.revision:
        raise ParseError("模型配置已变化，请重试解析")
    if profile is None or "vision" not in profile.capabilities:
        raise ParseError("需要已标记 vision 的模型配置")
    model = create_chat_model_from_config(
        provider=profile.provider, model=profile.model, base_url=profile.base_url,
        api_key=api_key_for_profile(profile),
    )

    def describe(data: bytes, media_type: str) -> str:
        encoded = base64.b64encode(data).decode("ascii")
        reply = model.invoke([HumanMessage(content=[
            {"type": "text", "text": "请准确提取图片中的文字、图表和关键视觉信息，按阅读顺序用中文描述。看不清的内容请说明，不要编造。"},
            {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{encoded}"}},
        ])])
        if isinstance(reply.content, str):
            return reply.content
        return "\n".join(str(item.get("text", "")) for item in reply.content if isinstance(item, dict))

    return describe
