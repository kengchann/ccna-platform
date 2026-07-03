"""Streaming bundle writer.

Writes the bundle incrementally — one question/asset at a time — so imports
of arbitrarily large documents run in bounded memory. Layout is documented
in docs/import-engine.md ("Import bundle format v1").

Usage:

    with BundleWriter(out_dir, source_info) as writer:
        for item in source.extract():
            ...
            writer.add_question(question)
    # manifest + report are written on successful close
"""

from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import IO

from .. import __version__
from ..errors import BundleError
from ..model import (
    Asset,
    BundleManifest,
    ImportReport,
    Question,
    QuestionGroup,
    SourceInfo,
)

_EXT_BY_MEDIA_TYPE = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}


def _extension_for(media_type: str) -> str:
    ext = _EXT_BY_MEDIA_TYPE.get(media_type) or mimetypes.guess_extension(media_type)
    return ext or ".bin"


class BundleWriter:
    """Writes one import bundle. Not thread-safe; one writer per import run."""

    def __init__(self, out_dir: Path, source: SourceInfo) -> None:
        self._dir = out_dir
        self._source = source
        self._assets_dir = out_dir / "assets"
        self._questions_file: IO[str] | None = None
        self._groups_file: IO[str] | None = None
        self._assets_file: IO[str] | None = None
        self._question_count = 0
        self._group_count = 0
        self._asset_count = 0
        self._seen_asset_ids: set[str] = set()

        if out_dir.exists() and any(out_dir.iterdir()):
            raise BundleError(f"output directory {out_dir} exists and is not empty")
        self._assets_dir.mkdir(parents=True, exist_ok=True)

    def __enter__(self) -> "BundleWriter":
        self._questions_file = (self._dir / "questions.jsonl").open("w", encoding="utf-8")
        return self

    def add_question(self, question: Question) -> None:
        assert self._questions_file is not None, "writer used outside its context"
        self._questions_file.write(question.model_dump_json() + "\n")
        self._question_count += 1

    def add_group(self, group: QuestionGroup) -> None:
        if self._groups_file is None:
            self._groups_file = (self._dir / "groups.jsonl").open("w", encoding="utf-8")
        self._groups_file.write(group.model_dump_json() + "\n")
        self._group_count += 1

    def add_asset(self, asset: Asset, data: bytes) -> Asset:
        """Persist original asset bytes; returns the Asset with its final
        filename and sha256 filled in."""
        if asset.id in self._seen_asset_ids:
            raise BundleError(f"duplicate asset id {asset.id!r}")
        self._seen_asset_ids.add(asset.id)

        stored = asset.model_copy(
            update={
                "filename": f"{asset.id}{_extension_for(asset.media_type)}",
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        (self._assets_dir / stored.filename).write_bytes(data)
        if self._assets_file is None:
            self._assets_file = (self._dir / "assets.jsonl").open("w", encoding="utf-8")
        self._assets_file.write(stored.model_dump_json() + "\n")
        self._asset_count += 1
        return stored

    def finalize(self, report: ImportReport) -> BundleManifest:
        """Write report.json and manifest.json. Call after all content is added."""
        manifest = BundleManifest(
            importer_version=__version__,
            created_at=datetime.now(timezone.utc),
            source=self._source,
            question_count=self._question_count,
            group_count=self._group_count,
            asset_count=self._asset_count,
        )
        self._close_streams()
        (self._dir / "report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        (self._dir / "manifest.json").write_text(
            manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        return manifest

    def _close_streams(self) -> None:
        if self._questions_file is not None:
            self._questions_file.close()
            self._questions_file = None
        if self._groups_file is not None:
            self._groups_file.close()
            self._groups_file = None
        if self._assets_file is not None:
            self._assets_file.close()
            self._assets_file = None

    def __exit__(self, exc_type, exc, tb) -> None:
        self._close_streams()


def read_manifest(bundle_dir: Path) -> BundleManifest:
    path = bundle_dir / "manifest.json"
    if not path.is_file():
        raise BundleError(f"{bundle_dir} is not a bundle (missing manifest.json)")
    return BundleManifest.model_validate_json(path.read_text(encoding="utf-8"))
