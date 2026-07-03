"""Streaming bundle reader.

Used by importer tests today and by ingestion tooling later. Iterates
questions/groups line-by-line so large bundles never load whole into memory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from ..errors import BundleError
from ..model import Asset, BundleManifest, ImportReport, Question, QuestionGroup
from .writer import read_manifest


class BundleReader:
    def __init__(self, bundle_dir: Path) -> None:
        self._dir = bundle_dir
        self.manifest: BundleManifest = read_manifest(bundle_dir)

    def questions(self) -> Iterator[Question]:
        yield from _read_jsonl(self._dir / "questions.jsonl", Question)

    def groups(self) -> Iterator[QuestionGroup]:
        path = self._dir / "groups.jsonl"
        if path.is_file():
            yield from _read_jsonl(path, QuestionGroup)

    def assets(self) -> Iterator[Asset]:
        path = self._dir / "assets.jsonl"
        if path.is_file():
            yield from _read_jsonl(path, Asset)

    def report(self) -> ImportReport:
        path = self._dir / "report.json"
        if not path.is_file():
            raise BundleError(f"{self._dir} has no report.json")
        return ImportReport.model_validate_json(path.read_text(encoding="utf-8"))

    def asset_path(self, filename: str) -> Path:
        path = (self._dir / "assets" / filename).resolve()
        assets_root = (self._dir / "assets").resolve()
        if assets_root not in path.parents:
            raise BundleError(f"asset filename {filename!r} escapes the assets directory")
        return path


def _read_jsonl(path: Path, model):
    if not path.is_file():
        raise BundleError(f"missing bundle file: {path}")
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                yield model.model_validate_json(line)
            except ValueError as exc:
                raise BundleError(f"{path.name}:{line_no}: invalid {model.__name__}: {exc}") from exc
