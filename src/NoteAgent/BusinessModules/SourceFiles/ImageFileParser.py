"""Image size validation followed by a tagged vision model call."""
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from NoteAgent.BusinessModules.SourceFiles.SourceFileContracts import MAX_PIXELS, ParseError, Vision


def parse_image(data: bytes, media_type: str, vision: Vision | None, max_pixels: int = MAX_PIXELS) -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > max_pixels:
                raise ParseError("图片超过 1600 万像素")
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ParseError("图片损坏或格式错误") from exc
    if vision is None:
        raise ParseError("需要已标记 vision 的模型配置")
    try:
        result = vision(data, media_type).strip()
    except Exception as exc:
        raise ParseError("视觉解析调用失败") from exc
    if not result:
        raise ParseError("视觉解析没有返回内容")
    return result
