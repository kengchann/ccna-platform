"""PDF import source.

Implements the four stages described in docs/import-engine.md:

1. :mod:`.layout` — lossless page reading (text spans with fonts and
   coordinates, embedded image placements, vector-figure regions, tables).
2. :mod:`.segment` — split the page stream into question/group slices by the
   document's printed labels.
3. :mod:`.classify` — route each slice's flow into stem, options, answer key,
   and explanation; monospace runs become exact VerbatimBlocks.
4. :mod:`.assemble` — build Questions and original-image AssetPayloads
   (embedded bytes by xref, or exact page-region crops for vector figures).

Every layout heuristic lives in :class:`.config.PdfParserConfig`; the
defaults encode common question-bank conventions and are meant to be tuned
against the canonical source document. Anything the parser is unsure about is
imported anyway and flagged with an Issue — content is never dropped or
repaired, and one bad question never stops the run.

Streaming: one page plus the currently open question slice is in memory at a
time. The one exception is a scenario/case-study group, whose members are
buffered until the group closes so the ExtractedGroup (which lists its member
ids) can be yielded before them, as the source contract requires; memory is
bounded by the size of one group.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterator

import pymupdf

from ...errors import SourceError
from ...model import Issue, PageRegion, Severity, SourceInfo
from ..base import ExtractedItem, FailedQuestion, ImportSource
from .assemble import assemble_group_context, assemble_question, finalize_group, make_group
from .classify import QuestionClassifier
from .config import PdfParserConfig
from .layout import read_page
from .segment import Segmenter, Slice


class PdfImportSource(ImportSource):
    format_name = "pdf"

    def __init__(self, path: Path, config: PdfParserConfig | None = None) -> None:
        self._path = path
        self._config = config or PdfParserConfig()

    def describe(self) -> SourceInfo:
        try:
            data = self._path.read_bytes()
        except OSError as exc:
            raise SourceError(f"cannot read {self._path}: {exc}") from exc

        try:
            with pymupdf.open(stream=data, filetype="pdf") as doc:
                page_count = doc.page_count
        except Exception as exc:
            raise SourceError(f"{self._path} is not a readable PDF: {exc}") from exc

        return SourceInfo(
            format=self.format_name,
            filename=self._path.name,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            page_count=page_count,
        )

    def extract(self) -> Iterator[ExtractedItem]:
        try:
            doc = pymupdf.open(self._path)
        except Exception as exc:
            raise SourceError(f"{self._path} is not a readable PDF: {exc}") from exc

        try:
            yield from self._extract(doc)
        finally:
            doc.close()

    def _extract(self, doc: pymupdf.Document) -> Iterator[ExtractedItem]:
        cfg = self._config
        segmenter = Segmenter(cfg)
        classifier = QuestionClassifier(cfg)
        emitter = _Emitter(doc, cfg, classifier)

        preamble_noted = False

        def note_preamble() -> None:
            # The preamble is final as soon as the first slice exists; record
            # it then so the note reaches the report via an early item.
            nonlocal preamble_noted
            if not preamble_noted and (note := segmenter.preamble_note()):
                emitter.document_notes.append(note)
                preamble_noted = True

        for index in range(doc.page_count):
            page = read_page(doc, index, cfg)
            emitter.document_notes.extend(page.issues)
            for sl in segmenter.feed(page):
                note_preamble()
                yield from emitter.handle(sl)
        for sl in segmenter.flush():
            note_preamble()
            yield from emitter.handle(sl)
        note_preamble()
        yield from emitter.flush()


class _Emitter:
    """Turns slices into extracted items, managing group buffering and
    attaching document-level notes to the first emitted item."""

    def __init__(
        self, doc: pymupdf.Document, cfg: PdfParserConfig, classifier: QuestionClassifier
    ) -> None:
        self._doc = doc
        self._cfg = cfg
        self._classifier = classifier
        self._group_counter = 0
        self._pending_group: dict | None = None
        self._emitted_any = False
        self.document_notes: list[Issue] = []

    def handle(self, sl: Slice) -> Iterator[ExtractedItem]:
        if sl.kind == "group":
            yield from self._close_group()
            self._open_group(sl)
        else:
            item = self._question_item(sl)
            if self._pending_group is not None:
                self._pending_group["members"].append(item)
            else:
                yield self._with_notes(item)

    def flush(self) -> Iterator[ExtractedItem]:
        yield from self._close_group()
        if not self._emitted_any:
            # Document produced nothing at all: surface why as a failure.
            yield FailedQuestion(
                ordinal=1,
                issues=[
                    Issue(
                        severity=Severity.ERROR,
                        code="no_questions_found",
                        message="no question labels were recognized in this document",
                    ),
                    *self.document_notes,
                ],
            )
            self.document_notes = []

    def _open_group(self, sl: Slice) -> None:
        self._group_counter += 1
        group_id = f"g{self._group_counter}"
        try:
            context, assets, issues = assemble_group_context(self._doc, sl, group_id, self._cfg)
        except Exception as exc:
            # The group context is lost, but the member questions that follow
            # still import (ungrouped); the failure reaches the report as a
            # document note on the next item.
            self._pending_group = None
            self.document_notes.append(_extraction_error(exc, sl, what=f"group {sl.label!r}"))
            return
        self._pending_group = {
            "slice": sl,
            "group": make_group(sl, group_id, context),
            "assets": assets,
            "issues": issues,
            "members": [],
        }

    def _close_group(self) -> Iterator[ExtractedItem]:
        if self._pending_group is None:
            return
        pending, self._pending_group = self._pending_group, None
        member_ids = [
            m.question.id for m in pending["members"] if not isinstance(m, FailedQuestion)
        ]
        yield self._with_notes(
            finalize_group(pending["group"], member_ids, pending["assets"], pending["issues"])
        )
        for member in pending["members"]:
            yield member

    def _question_item(self, sl: Slice) -> ExtractedItem:
        group_id = self._pending_group["group"].id if self._pending_group else None
        try:
            return assemble_question(self._doc, sl, self._cfg, self._classifier, group_id)
        except Exception as exc:
            return FailedQuestion(
                ordinal=sl.ordinal or 1,
                issues=[_extraction_error(exc, sl, what=f"question {sl.label!r}")],
            )

    def _with_notes(self, item: ExtractedItem) -> ExtractedItem:
        """Attach accumulated document-level notes to the first real item so
        they reach the import report."""
        self._emitted_any = True
        if self.document_notes and not isinstance(item, FailedQuestion):
            item.issues.extend(self.document_notes)
            self.document_notes = []
        return item


def _extraction_error(exc: Exception, sl: Slice, what: str) -> Issue:
    page = sl.pages[0] if sl.pages else 1
    return Issue(
        severity=Severity.ERROR,
        code="extraction_error",
        message=f"failed to extract {what}: {type(exc).__name__}: {exc}",
        origin=PageRegion(page=page),
    )
