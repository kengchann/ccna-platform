"""Stage 4 — assembly: build canonical model objects from classified slices.

Asset handling follows the fidelity rules exactly:

- Embedded images are extracted by xref (``Document.extract_image``), which
  returns the *original* stored bytes — no re-encoding.
- Vector figures (topology diagrams drawn from strokes) are cropped by
  rendering the exact source page region at high DPI. Each crop is recorded
  with an INFO issue for the audit trail.
- Nothing is ever redrawn, recreated, or substituted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf

from ...model import (
    Asset,
    AssetKind,
    ChoiceInteraction,
    ContentBlock,
    Issue,
    PageRegion,
    Question,
    QuestionGroup,
    Severity,
    SourceRef,
)
from ...sources.base import AssetPayload, ExtractedGroup, ExtractedQuestion
from .blocks import BlockBuilder, FlowImage, FlowItem, FlowTable, FlowText
from .classify import QuestionClassifier
from .config import PdfParserConfig
from .segment import Slice

_MEDIA_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "jpx": "image/jpx",
    "jb2": "image/x-jbig2",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
}


@dataclass
class _SliceAssets:
    payloads: list[AssetPayload] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    flow_images: list[FlowImage] = field(default_factory=list)


def _extract_assets(
    doc: pymupdf.Document, sl: Slice, owner_id: str, cfg: PdfParserConfig
) -> _SliceAssets:
    out = _SliceAssets()
    for index, image in enumerate(sl.images, start=1):
        asset_id = f"{owner_id}-img{index}"
        origin = PageRegion(page=image.page, bbox=image.bbox)
        kind, data, media_type = AssetKind.PAGE_CROP, None, "image/png"

        if image.xref is not None:
            try:
                info = doc.extract_image(image.xref)
                data = info["image"]
                media_type = _MEDIA_TYPES.get(info["ext"].lower(), f"image/{info['ext'].lower()}")
                kind = AssetKind.EMBEDDED
            except Exception as exc:
                out.issues.append(
                    Issue(
                        severity=Severity.WARNING,
                        code="image_extraction_failed",
                        message=(
                            f"embedded image xref {image.xref} on page {image.page} "
                            f"could not be extracted ({exc}); cropped the page region instead"
                        ),
                        origin=origin,
                    )
                )
        if data is None:
            page = doc.load_page(image.page - 1)
            pix = page.get_pixmap(clip=pymupdf.Rect(image.bbox), dpi=cfg.crop_dpi)
            data = pix.tobytes("png")
            if kind is AssetKind.PAGE_CROP and image.xref is None:
                out.issues.append(
                    Issue(
                        severity=Severity.INFO,
                        code="figure_cropped",
                        message=(
                            f"vector figure on page {image.page} cropped from the "
                            f"original page region at {cfg.crop_dpi} DPI"
                        ),
                        origin=origin,
                    )
                )

        out.payloads.append(
            AssetPayload(
                asset=Asset(
                    id=asset_id,
                    kind=kind,
                    media_type=media_type,
                    filename="",  # filled in by the bundle writer
                    origin=origin,
                    sha256="",  # filled in by the bundle writer
                ),
                data=data,
            )
        )
        out.flow_images.append(FlowImage(asset_id=asset_id, page=image.page, y=image.y_center))
    return out


def _build_flow(sl: Slice, flow_images: list[FlowImage]) -> list[FlowItem]:
    items: list[FlowItem] = []
    for position, line in enumerate(sl.lines):
        items.append(FlowText(line=line, strip_prefix=sl.label_char_len if position == 0 else 0))
    items.extend(flow_images)
    items.extend(FlowTable(table=t) for t in sl.tables)
    items.sort(key=lambda i: i.sort_key)
    return items


def assemble_question(
    doc: pymupdf.Document,
    sl: Slice,
    cfg: PdfParserConfig,
    classifier: QuestionClassifier,
    group_id: str | None,
) -> ExtractedQuestion:
    assert sl.kind == "question" and sl.ordinal is not None
    question_id = f"q{sl.ordinal}"
    assets = _extract_assets(doc, sl, question_id, cfg)
    flow = _build_flow(sl, assets.flow_images)
    classified = classifier.classify(flow, page_hint=sl.pages[0] if sl.pages else 1)

    question = Question(
        id=question_id,
        source=SourceRef(ordinal=sl.ordinal, label=sl.label, pages=list(sl.pages)),
        type=classified.qtype,
        group_id=group_id,
        stem=classified.stem,
        interaction=ChoiceInteraction(
            options=classified.options,
            correct_option_ids=classified.correct_ids,
        ),
        explanation=classified.explanation,
    )
    return ExtractedQuestion(
        question=question,
        assets=assets.payloads,
        issues=assets.issues + classified.issues,
    )


def assemble_group_context(
    doc: pymupdf.Document, sl: Slice, group_id: str, cfg: PdfParserConfig
) -> tuple[list[ContentBlock], list[AssetPayload], list[Issue]]:
    """Group context is plain content (no options/answer key): build its
    blocks directly."""
    assert sl.kind == "group"
    assets = _extract_assets(doc, sl, group_id, cfg)
    builder = BlockBuilder(cfg)
    for item in _build_flow(sl, assets.flow_images):
        if isinstance(item, FlowText):
            builder.add_text(item)
        elif isinstance(item, FlowImage):
            builder.add_image(item.asset_id)
        else:
            builder.add_table(item.table)
    return builder.build(), assets.payloads, assets.issues


def make_group(sl: Slice, group_id: str, context: list[ContentBlock]) -> QuestionGroup:
    assert sl.group_kind is not None
    return QuestionGroup(
        id=group_id,
        kind=sl.group_kind,
        title=sl.label,
        context=context,
        question_ids=[],  # filled once the group's members are known
    )


def finalize_group(
    group: QuestionGroup, member_ids: list[str], assets: list[AssetPayload], issues: list[Issue]
) -> ExtractedGroup:
    return ExtractedGroup(
        group=group.model_copy(update={"question_ids": member_ids}),
        assets=assets,
        issues=issues,
    )
