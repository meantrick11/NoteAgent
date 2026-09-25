"""本地向量模型候选。

只枚举本应用愿意使用的、且已存在于本地 HuggingFace 缓存中的模型：不联网、不下载、
不加载权重。目录名存在不代表可用，必须能看到权重与 tokenizer 文件才算 available。
"""

import logging
from pathlib import Path

from pydantic import BaseModel

from noteagent.model_management.schemas import EmbeddingAvailability

_logger = logging.getLogger(__name__)

Availability = EmbeddingAvailability

# 权重文件：不同导出方式命名不同，命中任意一个即可。
_WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")
# tokenizer 文件：不同模型用不同实现，命中任意一个即可。
_TOKENIZER_FILES = (
    "tokenizer.json",
    "vocab.txt",
    "sentencepiece.bpe.model",
    "spiece.model",
)


class KnownEmbeddingModel(BaseModel):
    """One embedding model this app is willing to load."""

    model_id: str
    label: str
    # sentence-transformers 认的短名（.env 里可能就用短名），必须一起认。
    aliases: tuple[str, ...] = ()

    def matches(self, candidate: str) -> bool:
        """True when a configured or requested name refers to this model."""
        return candidate == self.model_id or candidate in self.aliases


# 唯一受支持的模型清单。前端只能从这里选，不能传任意路径或任意仓库名。
KNOWN_EMBEDDING_MODELS: tuple[KnownEmbeddingModel, ...] = (
    KnownEmbeddingModel(
        model_id="sentence-transformers/all-MiniLM-L6-v2",
        label="all-MiniLM-L6-v2（英文，最省内存）",
        aliases=("all-MiniLM-L6-v2",),
    ),
    KnownEmbeddingModel(
        model_id="BAAI/bge-small-zh-v1.5",
        label="bge-small-zh-v1.5（中文）",
        aliases=("bge-small-zh-v1.5",),
    ),
    KnownEmbeddingModel(
        model_id="intfloat/multilingual-e5-small",
        label="multilingual-e5-small（多语言，检索评测最优）",
        aliases=("multilingual-e5-small",),
    ),
)


class UnknownEmbeddingModelError(ValueError):
    """The requested model id is not in the supported catalog."""


class EmbeddingCandidate(BaseModel):
    """One row of the embedding picker."""

    model_id: str
    label: str
    availability: Availability
    reason: str | None = None
    active: bool = False
    resolved_revision: str | None = None


def repo_dir_name(model_id: str) -> str:
    """HuggingFace cache directory name for a repo id (``org/name``)."""
    return f"models--{model_id.replace('/', '--')}"


def known_model(model_id: str) -> KnownEmbeddingModel:
    """Look up a supported model by canonical id or short alias.

    The HTTP layer passes a model id straight from the client, so this is the boundary
    that stops an arbitrary filesystem path from being used as a model name.
    """
    for model in KNOWN_EMBEDDING_MODELS:
        if model.matches(model_id):
            return model
    raise UnknownEmbeddingModelError(f"不支持的向量模型：{model_id}")


def list_candidates(
    cache_dir: Path, *, active_model_id: str | None = None
) -> list[EmbeddingCandidate]:
    """Describe every supported model plus the currently active one.

    The active model is always present even when it is no longer supported, so the UI
    can say "the running index uses something unavailable" instead of pretending a
    different model is in effect.
    """
    candidates: list[EmbeddingCandidate] = []
    active_known = False
    for model in KNOWN_EMBEDDING_MODELS:
        is_active = bool(active_model_id) and model.matches(active_model_id)
        active_known = active_known or is_active
        availability, reason, revision = _inspect_cache(cache_dir, model.model_id)
        candidates.append(
            EmbeddingCandidate(
                model_id=model.model_id,
                label=model.label,
                availability=availability,
                reason=reason,
                active=is_active,
                resolved_revision=revision,
            )
        )
    if active_model_id and not active_known:
        candidates.append(
            EmbeddingCandidate(
                model_id=active_model_id,
                label=active_model_id,
                availability="unsupported",
                reason="当前启用的模型不在受支持清单内，无法在本应用内重建；请改选受支持模型",
                active=True,
            )
        )
    return candidates


def inspect_model(
    cache_dir: Path, model_id: str, *, active_model_id: str | None = None
) -> EmbeddingCandidate:
    """Inspect one supported model before a switch, rejecting unknown ids."""
    model = known_model(model_id)
    availability, reason, revision = _inspect_cache(cache_dir, model.model_id)
    return EmbeddingCandidate(
        model_id=model.model_id,
        label=model.label,
        availability=availability,
        reason=reason,
        active=bool(active_model_id) and model.matches(active_model_id),
        resolved_revision=revision,
    )


def resolved_revision(cache_dir: Path, model_id: str) -> str | None:
    """Snapshot revision of a cached model, or None when the cache cannot tell.

    Part of the index identity, so it has to be readable without loading weights; an
    unknown model id is reported the same as a missing cache entry (both mean "no
    revision to record"), and callers fall back to whatever the index recorded.
    """
    try:
        model = known_model(model_id)
    except UnknownEmbeddingModelError:
        return None
    snapshot = _snapshot_dir(cache_dir / repo_dir_name(model.model_id))
    return snapshot.name if snapshot is not None else None


def _inspect_cache(
    cache_dir: Path, model_id: str
) -> tuple[Availability, str | None, str | None]:
    """Check a cached repo and report availability, reason, and snapshot revision."""
    repo_dir = cache_dir / repo_dir_name(model_id)
    if not repo_dir.is_dir():
        return "incomplete", "本地缓存中没有该模型（本应用不自动下载）", None
    snapshot = _snapshot_dir(repo_dir)
    if snapshot is None:
        return "incomplete", "缓存不完整：缺少 snapshots 快照目录", None
    missing = _missing_files(snapshot)
    if missing:
        return "incomplete", f"缓存不完整：缺少 {'、'.join(missing)}", snapshot.name
    _logger.info("向量模型候选可用 model=%s revision=%s", model_id, snapshot.name)
    return "available", None, snapshot.name


def _snapshot_dir(repo_dir: Path) -> Path | None:
    """Resolve the revision directory to use, preferring refs/main."""
    snapshots = repo_dir / "snapshots"
    if not snapshots.is_dir():
        return None
    ref_file = repo_dir / "refs" / "main"
    if ref_file.is_file():
        try:
            revision = ref_file.read_text(encoding="utf-8").strip()
        except OSError:
            revision = ""
        if revision and (snapshots / revision).is_dir():
            return snapshots / revision
    revisions = [p for p in sorted(snapshots.iterdir()) if p.is_dir()]
    if len(revisions) == 1:
        # 只有一个快照时以它为准：refs 可能缺失（手工拷贝的缓存）。
        return revisions[0]
    return None


def _missing_files(snapshot: Path) -> list[str]:
    """Names of the artifacts that must be present for sentence-transformers to load."""
    missing: list[str] = []
    if not _has_real_file(snapshot, ("config.json",)):
        missing.append("config.json")
    if not _has_real_file(snapshot, _WEIGHT_FILES):
        missing.append("权重文件")
    if not _has_real_file(snapshot, _TOKENIZER_FILES):
        missing.append("tokenizer")
    return missing


def _has_real_file(directory: Path, names: tuple[str, ...]) -> bool:
    """True when one of the names exists as a non-empty file.

    A half-downloaded HF snapshot leaves dangling symlinks or zero-byte entries, so
    existence alone is not enough to call a model usable.
    """
    for name in names:
        candidate = directory / name
        try:
            if candidate.is_file() and candidate.stat().st_size > 0:
                return True
        except OSError:
            continue
    return False
