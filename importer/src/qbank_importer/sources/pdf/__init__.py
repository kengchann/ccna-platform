"""PDF import source (scaffold).

``describe()`` is implemented; ``extract()`` is deliberately not — its
segmentation and classification heuristics must be developed against the
real canonical PDF, and guessing them in advance would violate the fidelity
rules. The planned decomposition (see docs/import-engine.md, "PDF source —
planned decomposition"):

1. Page extraction (PyMuPDF): text spans with coordinates and font info,
   embedded image xrefs, vector drawing regions. Raw and lossless.
2. Question segmentation: split the page stream into per-question slices via
   the document's question labels/layout; handle multi-page questions and
   scenario/case-study headers.
3. Block classification: prose vs verbatim (monospace/layout cues) vs figure
   region vs table, per slice.
4. Assembly: build Question objects and AssetPayloads. Embedded images are
   extracted by xref (original bytes); vector figures are cropped from the
   exact page region at high DPI. Anything uncertain becomes an Issue, never
   a silent guess.

Each stage should land as its own module in this package with its own tests.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator

from ...errors import SourceError
from ...model import SourceInfo
from ..base import ExtractedItem, ImportSource


class PdfImportSource(ImportSource):
    format_name = "pdf"

    def __init__(self, path: Path) -> None:
        self._path = path

    def describe(self) -> SourceInfo:
        import fitz  # PyMuPDF; imported lazily so model/bundle code never needs it

        try:
            data = self._path.read_bytes()
        except OSError as exc:
            raise SourceError(f"cannot read {self._path}: {exc}") from exc

        try:
            with fitz.open(stream=data, filetype="pdf") as doc:
                page_count = doc.page_count
        except Exception as exc:  # fitz raises format-specific exceptions
            raise SourceError(f"{self._path} is not a readable PDF: {exc}") from exc

        return SourceInfo(
            format=self.format_name,
            filename=self._path.name,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            page_count=page_count,
        )

    def extract(self) -> Iterator[ExtractedItem]:
        # TODO(pdf-parser): implement stages 1-4 from the module docstring
        # against the canonical question-bank PDF. This method will yield
        # ExtractedGroup items (scenario/case-study context, before their
        # members), ExtractedQuestion items with original image bytes as
        # AssetPayloads, and FailedQuestion for unparseable positions. It
        # must stream (no whole-document accumulation) and must never raise
        # for a single bad question.
        raise NotImplementedError(
            "PDF question extraction is not implemented yet. The segmentation "
            "and classification heuristics are developed against the canonical "
            "question-bank PDF; see this module's docstring for the plan."
        )
