"""JSON import source: an authoring format for original question banks.

Unlike the PDF source (which reverse-engineers layout), this source reads a
hand-authored JSON document whose shape maps directly onto the canonical
model. It is the recommended way to author content the team owns.

Document shape (see docs/authoring-format.md and content/ for examples):

    {
      "bank": "Networking Fundamentals",
      "questions": [
        {
          "type": "single_choice",
          "label": "1",
          "stem": [
            {"text": "Refer to the output."},
            {"cli": "Router# show ip route\\n..."}
          ],
          "options": [
            {"id": "a", "text": "10.0.0.0/8", "correct": true},
            {"id": "b", "text": "0.0.0.0/0"}
          ],
          "explanation": [{"text": "..."}]
        }
      ],
      "groups": [
        {"id": "s1", "kind": "scenario", "title": "...",
         "context": [{"text": "..."}], "questions": ["7", "8"]}
      ]
    }

Content blocks accept exactly one of: ``text``, ``cli`` (verbatim), ``table``
(rows), or ``image`` (a path, relative to the JSON file, to an image whose
original bytes are embedded). The source validates *shape* and reports
authoring mistakes as issues; the pipeline's validator handles plausibility.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator

from ...errors import SourceError
from ...model import SourceInfo
from ..base import ExtractedItem, ImportSource
from .reader import JsonDocumentReader


class JsonImportSource(ImportSource):
    format_name = "json"

    def __init__(self, path: Path) -> None:
        self._path = path

    def describe(self) -> SourceInfo:
        try:
            data = self._path.read_bytes()
        except OSError as exc:
            raise SourceError(f"cannot read {self._path}: {exc}") from exc
        try:
            json.loads(data)
        except json.JSONDecodeError as exc:
            raise SourceError(f"{self._path} is not valid JSON: {exc}") from exc
        return SourceInfo(
            format=self.format_name,
            filename=self._path.name,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            page_count=None,
        )

    def extract(self) -> Iterator[ExtractedItem]:
        try:
            document = json.loads(self._path.read_bytes())
        except (OSError, json.JSONDecodeError) as exc:
            raise SourceError(f"cannot read {self._path}: {exc}") from exc
        reader = JsonDocumentReader(document, base_dir=self._path.parent)
        yield from reader.items()
