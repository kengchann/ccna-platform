"""Bundle manifest: what a bundle contains and where it came from."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .content import _StrictModel

#: Version of the bundle directory layout + JSON shapes. Bump on breaking
#: changes; ingestion code checks it before loading.
BUNDLE_FORMAT_VERSION = "1.0"


class SourceInfo(_StrictModel):
    """Identity of the source document an import was produced from."""

    format: str = Field(description='Source format name, e.g. "pdf"')
    filename: str = Field(description="Original filename (no directory components)")
    sha256: str = Field(description="Hex digest of the source file")
    size_bytes: int = Field(ge=0)
    page_count: int | None = Field(
        default=None, description="Pages in the source, when the format has pages"
    )


class BundleManifest(_StrictModel):
    bundle_format_version: str = BUNDLE_FORMAT_VERSION
    importer_version: str
    created_at: datetime
    source: SourceInfo
    question_count: int = Field(ge=0)
    group_count: int = Field(ge=0)
    asset_count: int = Field(ge=0)
