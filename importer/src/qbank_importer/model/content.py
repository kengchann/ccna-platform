"""Content blocks and assets: the units question content is made of.

Fidelity contract (see docs/import-engine.md):

- ``text`` in every block is carried through from the source exactly as
  extracted. Nothing here trims, collapses whitespace, or fixes wording.
- ``VerbatimBlock`` holds CLI output, running configs, routing tables, etc.
  Its text preserves whitespace, indentation, prompts, and line breaks
  byte-for-byte.
- ``Asset`` always refers to an *original* image: either the embedded image
  bytes extracted from the source, or an exact crop of the source page
  region. Assets record their provenance so any admin can audit where an
  image came from.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    """Base for all bundle models: unknown keys are errors, not silence."""

    model_config = ConfigDict(extra="forbid")


class PageRegion(_StrictModel):
    """Provenance of extracted content: where in the source it came from.

    ``bbox`` is (x0, y0, x1, y1) in PDF points, top-left origin, matching
    PyMuPDF's coordinate convention. It is None when the source format has no
    geometric coordinates (e.g. a future JSON source).
    """

    page: int = Field(ge=1, description="1-based page number in the source document")
    bbox: tuple[float, float, float, float] | None = None


class AssetKind(str, Enum):
    #: Original image bytes extracted directly from the source document.
    EMBEDDED = "embedded"
    #: Exact rendering of the source page region (used when direct extraction
    #: is impossible, e.g. vector-drawn topology diagrams).
    PAGE_CROP = "page_crop"


class Asset(_StrictModel):
    """An original image/figure belonging to a question or group."""

    id: str
    kind: AssetKind
    media_type: str = Field(description='IANA media type, e.g. "image/png"')
    filename: str = Field(description="Path relative to the bundle's assets/ directory")
    origin: PageRegion
    sha256: str = Field(description="Hex digest of the asset file, set by the bundle writer")


class TextBlock(_StrictModel):
    """Prose content, exactly as extracted from the source."""

    kind: Literal["text"] = "text"
    text: str


class VerbatimBlock(_StrictModel):
    """Preformatted content (CLI output, configs, tables of the routing kind).

    Whitespace, indentation, capitalization, prompts, and line breaks are
    significant and preserved exactly. Renderers must use a monospace font
    and must not reflow.
    """

    kind: Literal["verbatim"] = "verbatim"
    text: str
    language_hint: str | None = Field(
        default=None,
        description='Optional rendering hint, e.g. "cisco-cli". Never affects content.',
    )


class ImageBlock(_StrictModel):
    """Reference to an original Asset, positioned within the content flow."""

    kind: Literal["image"] = "image"
    asset_id: str
    caption: str | None = Field(
        default=None, description="Caption exactly as printed in the source, if any"
    )


class TableBlock(_StrictModel):
    """A table whose cell text could be extracted faithfully.

    Cell strings are exact. If a source table cannot be reconstructed
    faithfully (merged cells, drawn grids, uncertain column detection), the
    source implementation must crop it as a PAGE_CROP asset and emit an
    ImageBlock instead — never a lossy TableBlock.
    """

    kind: Literal["table"] = "table"
    rows: list[list[str]]


ContentBlock = Annotated[
    Union[TextBlock, VerbatimBlock, ImageBlock, TableBlock],
    Field(discriminator="kind"),
]
