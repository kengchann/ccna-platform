"""Source format registry.

To add a new format: implement :class:`~qbank_importer.sources.base.ImportSource`
in a subpackage, then register it in ``_SOURCES`` below. Nothing else in the
importer changes.
"""

from __future__ import annotations

from pathlib import Path

from ..errors import UnsupportedFormatError
from .base import (
    AssetPayload,
    ExtractedGroup,
    ExtractedItem,
    ExtractedQuestion,
    FailedQuestion,
    ImportSource,
)
from .json import JsonImportSource
from .pdf import PdfImportSource

#: format_name -> (file suffixes, source class)
_SOURCES: dict[str, tuple[tuple[str, ...], type[ImportSource]]] = {
    PdfImportSource.format_name: ((".pdf",), PdfImportSource),
    JsonImportSource.format_name: ((".json",), JsonImportSource),
}


def open_source(path: Path, format_name: str | None = None) -> ImportSource:
    """Create the ImportSource for ``path``.

    The format is chosen explicitly via ``format_name`` or inferred from the
    file suffix. Raises :class:`UnsupportedFormatError` if neither matches.
    """
    if format_name is not None:
        try:
            _, cls = _SOURCES[format_name]
        except KeyError:
            raise UnsupportedFormatError(
                f"unknown format {format_name!r}; supported: {sorted(_SOURCES)}"
            ) from None
        return cls(path)

    suffix = path.suffix.lower()
    for suffixes, cls in _SOURCES.values():
        if suffix in suffixes:
            return cls(path)
    raise UnsupportedFormatError(
        f"no import source handles {suffix!r} files; supported formats: {sorted(_SOURCES)}"
    )


__all__ = [
    "AssetPayload",
    "ExtractedGroup",
    "ExtractedItem",
    "ExtractedQuestion",
    "FailedQuestion",
    "ImportSource",
    "JsonImportSource",
    "PdfImportSource",
    "open_source",
]
