"""各嵌入模型要求的编码指令。

单独成模块是有意的：索引指纹必须能**在不加载权重**的前提下算出来（重建前要先给目标
collection 命名），所以这张表不能放在会 import sentence-transformers 的模块里。
"""

# 各模型要求的编码指令；不按官方用法加，检索质量会明显下降。
# bge-zh-v1.5：query 侧指令（官方表 "query instruction for retrieval"）。
# e5 系列：query 与 passage 两侧都必须加，非英文也一样。
MODEL_INSTRUCTIONS: dict[str, tuple[str, str]] = {
    "BAAI/bge-small-zh-v1.5": ("为这个句子生成表示以用于检索相关文章：", ""),
    "intfloat/multilingual-e5-small": ("query: ", "passage: "),
}


def instructions_for(model_id: str) -> tuple[str, str]:
    """``(query_prefix, document_prefix)`` for a model id; empty when it needs none."""
    return MODEL_INSTRUCTIONS.get(model_id, ("", ""))


def instruction_fingerprint_for(model_id: str) -> str:
    """Compact description of a model's instructions, for the index fingerprint."""
    query_prefix, document_prefix = instructions_for(model_id)
    if not query_prefix and not document_prefix:
        return ""
    return f"{query_prefix}|{document_prefix}"
