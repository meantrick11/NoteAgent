"""Offline tests for embedding instructions and the index configuration fingerprint.

No model is loaded here: the instruction table and the pure helpers are what matter,
and the fingerprint is checked through a stub embedder.
"""

import json
from pathlib import Path

from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import MODEL_INSTRUCTIONS, SentenceTransformerEmbedder
from noteagent.retrieval.instructions import instruction_fingerprint_for
from noteagent.retrieval.service import (
    DOC_NORMALIZATION_VERSION,
    INDEX_CONFIG_SCHEMA,
    canonical_index_config,
    fingerprint_of,
    index_config_fingerprint,
    index_fingerprint_for_model,
)


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


def test_fingerprint_is_a_sha256_of_the_canonical_configuration():
    """The identity is the hash of the fields, so any of them changing changes it."""
    chunker = MarkdownChunker(500, 50, strategy="char")
    embedder = _StubEmbedder("all-MiniLM-L6-v2")

    fingerprint = index_config_fingerprint(chunker, embedder, False)

    assert len(fingerprint) == 64
    canonical = canonical_index_config(
        model_id="all-MiniLM-L6-v2",
        chunker=chunker,
        embed_heading_prefix=False,
        instructions="",
    )
    assert canonical["schema"] == INDEX_CONFIG_SCHEMA
    assert canonical["normalization"] == DOC_NORMALIZATION_VERSION
    assert json.dumps(canonical, sort_keys=True)
    assert fingerprint == fingerprint_of(canonical)


def test_fingerprint_changes_with_model_strategy_heading_and_instructions():
    char = MarkdownChunker(500, 50, strategy="char")
    heading = MarkdownChunker(500, 50, strategy="heading")
    smaller = MarkdownChunker(300, 30, strategy="char")
    plain = _StubEmbedder("all-MiniLM-L6-v2")
    instructed = _StubEmbedder("intfloat/multilingual-e5-small", "query: |passage: ")

    base = index_config_fingerprint(char, plain, False)
    assert index_config_fingerprint(char, plain, False) == base
    assert index_config_fingerprint(heading, plain, False) != base
    assert index_config_fingerprint(smaller, plain, False) != base
    assert index_config_fingerprint(char, plain, True) != base
    assert index_config_fingerprint(char, instructed, False) != base


def test_fingerprint_changes_with_the_model_revision():
    """同样的模型换了权重快照就是另一个索引，不能沿用旧向量。"""
    chunker = MarkdownChunker(500, 50, strategy="char")
    embedder = _StubEmbedder("all-MiniLM-L6-v2")

    first = index_config_fingerprint(chunker, embedder, False, "rev-a")
    second = index_config_fingerprint(chunker, embedder, False, "rev-b")

    assert first != second
    assert first != index_config_fingerprint(chunker, embedder, False)


def test_a_model_level_fingerprint_matches_the_assembled_one():
    """预计算（不加载权重）与装配后的结果必须一致，否则目标 collection 会被写错内容。"""
    for model_id in ("all-MiniLM-L6-v2", "intfloat/multilingual-e5-small"):
        embedder = _StubEmbedder(model_id, instruction_fingerprint_for(model_id))
        assert index_fingerprint_for_model(
            model_id,
            strategy="heading",
            embed_heading_prefix=True,
            resolved_revision="rev-1",
        ) == index_config_fingerprint(
            MarkdownChunker(strategy="heading"), embedder, True, "rev-1"
        )


def test_a_collection_from_before_fingerprints_is_not_adopted():
    """旧格式 collection 的身份无法核验，只能报告需要重建，绝不伪造匹配。"""
    from noteagent.retrieval.vector_store import LEGACY_FINGERPRINT

    assert LEGACY_FINGERPRINT != index_config_fingerprint(
        MarkdownChunker(500, 50, strategy="char"), _StubEmbedder("all-MiniLM-L6-v2"), False
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
