"""The format-specific boundary of the importer.

An :class:`ImportSource` is the only thing a new input format (Word, JSON,
CSV, Markdown, ...) needs to implement. It streams extracted items one at a
time so that arbitrarily large documents import in bounded memory; everything
downstream (pipeline, validation, bundle writing) is format-agnostic.

Every implementation is bound by the fidelity rules in docs/import-engine.md:
exact text, verbatim CLI blocks, original images only, source order preserved,
flag-don't-fix.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator, Union

from ..model import Asset, Issue, Question, QuestionGroup, SourceInfo


@dataclass
class AssetPayload:
    """An asset's metadata together with the original bytes.

    ``asset.sha256`` and ``asset.filename`` may be placeholders at extraction
    time; the bundle writer fills them in when it persists the bytes.
    """

    asset: Asset
    data: bytes


@dataclass
class ExtractedQuestion:
    """One question as it came out of the source, with its assets and any
    issues the extraction raised (OCR corrections, ambiguities, ...)."""

    question: Question
    assets: list[AssetPayload] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


@dataclass
class ExtractedGroup:
    """A scenario/case-study group. Emitted before its member questions."""

    group: QuestionGroup
    assets: list[AssetPayload] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


@dataclass
class FailedQuestion:
    """A source position that could not be extracted as a question. The run
    continues; the failure lands in the import report with its location."""

    ordinal: int
    issues: list[Issue]


ExtractedItem = Union[ExtractedQuestion, ExtractedGroup, FailedQuestion]


class ImportSource(ABC):
    """A parsable source document of a specific format."""

    #: Registry key and manifest value, e.g. "pdf". Set by each subclass.
    format_name: str

    @abstractmethod
    def describe(self) -> SourceInfo:
        """Identify the source document (filename, hash, size, pages)."""

    @abstractmethod
    def extract(self) -> Iterator[ExtractedItem]:
        """Stream extracted items in source order.

        Groups are yielded before their member questions. Implementations
        must not accumulate the whole document in memory and must not raise
        for per-question problems — yield :class:`FailedQuestion` instead.
        """
