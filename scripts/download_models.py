"""Fetch sentence-transformers models into the local cache through a mirror.

Why not ``snapshot_download``: huggingface_hub 1.x insists that the response carry
the ``x-repo-commit`` header and raises ``FileMetadataError`` ("Distant resource does
not seem to be on huggingface.co") when a mirror does not send it. The mirror's plain
HTTP API works fine, so this script builds the cache layout by hand — ``refs/main``
plus ``snapshots/<revision>/<file>`` — which is exactly what
``SentenceTransformer(..., cache_folder=...)`` expects.

It downloads only the files sentence-transformers needs: duplicate ``.bin`` weights,
ONNX and OpenVINO exports are skipped. Weights come with an LFS sha256 in the API
response, and each one is verified before the file is kept.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from noteagent.bootstrap.settings import Settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
_logger = logging.getLogger("download_models")

SKIP_SUFFIXES = (".bin", ".h5", ".msgpack", ".ot", ".tflite", ".onnx", ".onnx_data")
SKIP_PREFIXES = ("onnx/", "openvino/", "coreml/", "saved_model/", "tf_model", "flax_model")
# 加载用不到、只是仓库元数据的文件，别把 500KB 的 README 和评测结果拉下来。
SKIP_EXACT = ("README.md", ".gitattributes", "LICENSE", "LICENSE.txt")
SKIP_DOT_PREFIX = "."
KEEP_ALWAYS = ("1_Pooling/config.json", "modules.json")
DEFAULT_MODELS = ("BAAI/bge-small-zh-v1.5", "intfloat/multilingual-e5-small")


def _cache_folder(cache_dir: Path, repo_id: str) -> Path:
    """HF cache directory name for one repository."""
    return cache_dir / f"models--{repo_id.replace('/', '--')}"


def _wanted(name: str) -> bool:
    """True for the files sentence-transformers needs on CPU/torch."""
    if name in SKIP_EXACT or name.startswith(SKIP_DOT_PREFIX):
        return False
    if name.startswith(SKIP_PREFIXES) or name.endswith(SKIP_SUFFIXES):
        return False
    return True


def download(
    repo_id: str, cache_dir: Path, endpoint: str, *, dry_run: bool = False
) -> tuple[str, list[str]]:
    """Fetch one repository into the cache layout; returns the revision and files."""
    api = f"{endpoint.rstrip('/')}/api/models/{repo_id}?blobs=true"
    info = requests.get(api, timeout=60).json()
    revision = info["sha"]
    keep = [item for item in info.get("siblings", []) if _wanted(item["rfilename"])]
    folder = _cache_folder(cache_dir, repo_id)
    snapshot = folder / "snapshots" / revision
    _logger.info(
        "%s revision=%s files=%d -> %s", repo_id, revision[:12], len(keep), snapshot
    )
    if dry_run:
        for item in keep:
            print(f"  would fetch {item['rfilename']} ({item.get('size') or '?'} bytes)")
        return revision, [item["rfilename"] for item in keep]

    snapshot.mkdir(parents=True, exist_ok=True)
    (folder / "refs").mkdir(parents=True, exist_ok=True)
    for item in keep:
        name = item["rfilename"]
        target = snapshot / name
        url = f"{endpoint.rstrip('/')}/{repo_id}/resolve/{revision}/{name}"
        expected = (item.get("lfs") or {}).get("sha256")
        if target.is_file() and expected is not None and _sha256(target) == expected:
            _logger.info("skip %s (already present and verified)", name)
            continue
        _logger.info("fetch %s", name)
        _transfer(url, target)
        if expected is not None and _sha256(target) != expected:
            # 断点续传接上了残缺内容时只可能在这里暴露：删掉重下一次。
            _logger.warning("%s: sha256 mismatch, retrying from scratch", name)
            target.unlink()
            _transfer(url, target)
            if _sha256(target) != expected:
                target.unlink()
                raise RuntimeError(f"{name}: sha256 mismatch after a clean download")
    (folder / "refs" / "main").write_text(revision, encoding="utf-8")
    return revision, [item["rfilename"] for item in keep]


def _transfer(url: str, target: Path) -> None:
    """Download one file with the system curl.

    Measured here at ~1.7 MB/s against the mirror, while a Python stream loop managed
    ~68 KB/s; curl also resumes (``-C -``), which matters for the 470 MB weights.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "curl", "-L", "--fail", "--silent", "--show-error",
            "--retry", "3", "--retry-delay", "2",
            "-C", "-", "-o", str(target), url,
        ],
        check=True,
    )


def _sha256(path: Path) -> str:
    """Hash an existing file in one pass."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    """Download the requested models, or report what would be fetched."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="*", default=list(DEFAULT_MODELS))
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="默认取 Settings 的 EMBEDDING_CACHE_DIR",
    )
    parser.add_argument("--endpoint", default="https://hf-mirror.com")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    cache_dir = args.cache_dir or Settings().embedding_cache_dir
    print(f"endpoint={args.endpoint} cache={cache_dir}")
    for repo_id in args.models:
        revision, files = download(repo_id, cache_dir, args.endpoint, dry_run=args.dry_run)
        print(f"{repo_id}: revision={revision} files={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
