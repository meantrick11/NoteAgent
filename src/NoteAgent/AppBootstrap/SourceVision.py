"""Vision extraction through a model configuration pinned at upload time."""
import base64

from langchain_core.messages import HumanMessage

from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import (
    ProtocolUnsupportedError,
    RevisionConflictError,
)
from NoteAgent.Modules.Models.Service.ModelConfigService import ModelConfigService
from NoteAgent.Modules.Sources.Domain.Po.SourceFileModels import SourceFile
from NoteAgent.Modules.Sources.Parser.SourceFileParsers import ParseError, Vision


def vision_factory(source: SourceFile, config_service: ModelConfigService) -> Vision | None:
    """Resolve the pinned model id/revision and return an image describer.

    The model does not have to be active anymore: the source keeps the identity it was
    uploaded with so parsing remains reproducible. A PDF without verified vision falls
    back to text extraction; an image without it fails.
    """
    if not source.parse_profile_id or source.parse_profile_revision is None:
        if source.media_type == "application/pdf":
            return None
        raise ParseError("需要已验证 vision 的模型配置")
    try:
        model = config_service.build_client_for_parse(
            source.parse_profile_id,
            source.parse_profile_revision,
            vision=True,
        )
    except ProtocolUnsupportedError as exc:
        if source.media_type == "application/pdf":
            return None
        raise ParseError(str(exc)) from exc
    except RevisionConflictError as exc:
        raise ParseError("模型配置已变化，请重试解析") from exc

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
