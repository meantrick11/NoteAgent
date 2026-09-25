"""Offline tests for embedding instructions and the index configuration fingerprint.

No model is loaded here: the instruction table and the pure helpers are what matter,
and the fingerprint is checked through a stub embedder.
"""

from pathlib import Path

from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import MODEL_INSTRUCTIONS, SentenceTransformerEmbedder
from noteagent.retrieval.service import index_config_fingerprint


class _StubEmbedder:
    def __init__(self, model_name: str, instructions: str = ""):
        self.model_name = model_name
        self._instructions = instructions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        return [0.0]

    def instruction_fingerprint(self) -> str:
        return self._instructions


def test_evaluated_candidates_declare_their_instructions():
    # e5 系列两侧都必须加前缀；bge-zh-v1.5 只在查询侧加。
    assert MODEL_INSTRUCTIONS["intfloat/multilingual-e5-small"] == ("query: ", "passage: ")
    query_prefix, document_prefix = MODEL_INSTRUCTIONS["BAAI/bge-small-zh-v1.5"]
    assert query_prefix.startswith("为这个句子生成表示")
    assert document_prefix == ""


def test_document_text_applies_the_document_prefix():
    embedder = object.__new__(SentenceTransformerEmbedder)
    embedder.document_prefix = "passage: "
    embedder.query_prefix = "query: "
    assert embedder.document_text("正文") == "passage: 正文"
    assert embedder.instruction_fingerprint() == "query: |passage: "


def test_fingerprint_changes_with_model_strategy_and_instructions():
    char = MarkdownChunker(500, 50, strategy="char")
    heading = MarkdownChunker(500, 50, strategy="heading")
    plain = _StubEmbedder("all-MiniLM-L6-v2")
    instructed = _StubEmbedder("intfloat/multilingual-e5-small", "query: |passage: ")

    base = index_config_fingerprint(char, plain, False)
    assert base == "char:500/50|all-MiniLM-L6-v2|content"
    assert index_config_fingerprint(heading, plain, False) != base
    assert index_config_fingerprint(char, plain, True) != base
    assert index_config_fingerprint(char, instructed, False) != base
    assert index_config_fingerprint(char, plain, False) == base


def test_legacy_fingerprint_still_matches_an_unchanged_deployment():
    """旧索引没有指纹时按 legacy 默认处理，配置没变就不该被要求重建。"""
    from noteagent.retrieval.vector_store import LEGACY_FINGERPRINT

    assert LEGACY_FINGERPRINT == "char:500/50|all-MiniLM-L6-v2|content"
    assert (
        index_config_fingerprint(MarkdownChunker(500, 50, strategy="char"), _StubEmbedder("all-MiniLM-L6-v2"), False)
        == LEGACY_FINGERPRINT
    )


def test_download_script_skips_weights_it_does_not_need():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "download_models", Path(__file__).resolve().parents[2] / "scripts" / "download_models.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._wanted("model.safetensors") is True
    assert module._wanted("1_Pooling/config.json") is True
    assert module._wanted("tokenizer.json") is True
    assert module._wanted("pytorch_model.bin") is False
    assert module._wanted("onnx/model.onnx") is False
    assert module._wanted("openvino/openvino_model.bin") is False
    assert module._wanted("README.md") is False
    assert module._wanted(".eval_results/BrightRetrieval.yaml") is False
