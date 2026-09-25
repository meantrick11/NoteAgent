"""Embedding candidate discovery against a fake HuggingFace cache."""

from pathlib import Path

import pytest

from noteagent.model_management.catalog import (
    KNOWN_EMBEDDING_MODELS,
    EmbeddingCandidate,
    UnknownEmbeddingModelError,
    inspect_model,
    list_candidates,
    repo_dir_name,
)

MINILM = "sentence-transformers/all-MiniLM-L6-v2"
BGE = "BAAI/bge-small-zh-v1.5"
E5 = "intfloat/multilingual-e5-small"

COMPLETE_FILES = ("config.json", "model.safetensors", "tokenizer.json")


def write_cache(
    cache_dir: Path,
    model_id: str,
    *,
    revision: str = "abc123",
    files: tuple[str, ...] = COMPLETE_FILES,
    with_refs: bool = True,
) -> Path:
    """Create a HF-style cached repo and return its snapshot directory."""
    repo = cache_dir / repo_dir_name(model_id)
    if with_refs:
        (repo / "refs").mkdir(parents=True, exist_ok=True)
        (repo / "refs" / "main").write_text(revision, encoding="utf-8")
    snapshot = repo / "snapshots" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in files:
        (snapshot / name).write_bytes(b"weights")
    return snapshot


def by_id(candidates: list[EmbeddingCandidate]) -> dict[str, EmbeddingCandidate]:
    """Index candidates by model id for readable assertions."""
    return {candidate.model_id: candidate for candidate in candidates}


def test_empty_cache_lists_every_supported_model_as_incomplete(tmp_path):
    """Nothing cached means every known model is offered but unusable."""
    candidates = list_candidates(tmp_path / "models")

    assert len(candidates) == len(KNOWN_EMBEDDING_MODELS)
    assert {c.availability for c in candidates} == {"incomplete"}
    assert "不自动下载" in by_id(candidates)[E5].reason


def test_complete_cache_is_available_with_its_revision(tmp_path):
    """A snapshot carrying config, weights, and tokenizer is usable."""
    write_cache(tmp_path, BGE, revision="cafe42")

    candidate = by_id(list_candidates(tmp_path))[BGE]

    assert candidate.availability == "available"
    assert candidate.reason is None
    assert candidate.resolved_revision == "cafe42"


def test_directory_without_snapshot_is_not_available(tmp_path):
    """An interrupted clone leaves the repo dir behind but no usable snapshot."""
    (tmp_path / repo_dir_name(MINILM)).mkdir(parents=True)

    candidate = by_id(list_candidates(tmp_path))[MINILM]

    assert candidate.availability == "incomplete"
    assert "snapshots" in candidate.reason


@pytest.mark.parametrize(
    ("missing", "expected"),
    [
        ("config.json", "config.json"),
        ("model.safetensors", "权重文件"),
        ("tokenizer.json", "tokenizer"),
    ],
)
def test_missing_artifact_makes_the_model_incomplete(tmp_path, missing, expected):
    """Each required artifact is checked; names alone never mean available."""
    files = tuple(name for name in COMPLETE_FILES if name != missing)
    write_cache(tmp_path, E5, files=files)

    candidate = by_id(list_candidates(tmp_path))[E5]

    assert candidate.availability == "incomplete"
    assert expected in candidate.reason


def test_zero_byte_weight_is_incomplete(tmp_path):
    """A truncated download must not be reported as a usable model."""
    snapshot = write_cache(tmp_path, E5)
    (snapshot / "model.safetensors").write_bytes(b"")

    candidate = by_id(list_candidates(tmp_path))[E5]

    assert candidate.availability == "incomplete"
    assert "权重文件" in candidate.reason


def test_snapshot_without_refs_is_still_usable(tmp_path):
    """A hand-copied cache has no refs/main; a single snapshot is unambiguous."""
    write_cache(tmp_path, MINILM, revision="manual", with_refs=False)

    candidate = by_id(list_candidates(tmp_path))[MINILM]

    assert candidate.availability == "available"
    assert candidate.resolved_revision == "manual"


def test_active_model_is_marked(tmp_path):
    """The picker needs to know which candidate is in force."""
    write_cache(tmp_path, E5)

    candidate = by_id(list_candidates(tmp_path, active_model_id=E5))[E5]

    assert candidate.active is True


def test_active_model_outside_the_catalog_is_still_shown(tmp_path):
    """An unsupported active model stays visible instead of faking another as active."""
    candidates = list_candidates(tmp_path, active_model_id="acme/legacy-model")

    legacy = by_id(candidates)["acme/legacy-model"]
    assert legacy.availability == "unsupported"
    assert legacy.active is True
    assert "不在受支持清单内" in legacy.reason
    assert not any(c.active and c.model_id != "acme/legacy-model" for c in candidates)


def test_inspect_model_reports_a_single_known_model(tmp_path):
    """The switch path inspects one model rather than the whole list."""
    write_cache(tmp_path, BGE, revision="rev-9")

    candidate = inspect_model(tmp_path, BGE)

    assert candidate.availability == "available"
    assert candidate.resolved_revision == "rev-9"


@pytest.mark.parametrize(
    "bad_id",
    [
        "not-in-catalog",
        "acme/legacy-model",
        "../models--BAAI--bge-small-zh-v1.5",
        "C:\\models\\e5",
        "BAAI/bge-small-zh-v1.5/../../etc",
    ],
)
def test_unknown_or_path_like_model_ids_are_rejected(tmp_path, bad_id):
    """A client-supplied id can never be turned into a filesystem path."""
    with pytest.raises(UnknownEmbeddingModelError):
        inspect_model(tmp_path, bad_id)


def test_short_alias_resolves_to_the_cached_repo(tmp_path):
    """The .env may name a model by short alias; it maps onto the same repo cache."""
    write_cache(tmp_path, MINILM, revision="rev-alias")

    candidate = inspect_model(tmp_path, "all-MiniLM-L6-v2")

    assert candidate.model_id == MINILM
    assert candidate.availability == "available"


def test_active_marked_when_configured_by_alias(tmp_path):
    """An alias-configured active model still marks its catalog row."""
    write_cache(tmp_path, MINILM)

    candidates = list_candidates(tmp_path, active_model_id="all-MiniLM-L6-v2")

    assert by_id(candidates)[MINILM].active is True
    # 短名已被认领，不应再出现一条 unsupported 的重复行。
    assert len(candidates) == len(KNOWN_EMBEDDING_MODELS)
