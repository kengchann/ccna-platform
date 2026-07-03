"""Stage 1 — page extraction: raw, lossless reading of one PDF page.

Produces plain dataclasses (no PyMuPDF objects escape this module except the
open document itself) so the later stages are testable without a PDF. One
page is read at a time; nothing here accumulates document-wide state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pymupdf

from ...model import Issue, PageRegion, Severity
from .config import PdfParserConfig

BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Span:
    text: str
    bbox: BBox
    font: str
    size: float
    mono: bool


@dataclass(frozen=True)
class Line:
    """One text line as laid out on the page."""

    spans: tuple[Span, ...]
    page: int  # 1-based
    bbox: BBox

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.spans)

    @property
    def x0(self) -> float:
        return self.bbox[0]

    @property
    def y0(self) -> float:
        return self.bbox[1]

    @property
    def y1(self) -> float:
        return self.bbox[3]

    @property
    def mono(self) -> bool:
        visible = [s for s in self.spans if s.text.strip()]
        return bool(visible) and all(s.mono for s in visible)


@dataclass(frozen=True)
class PageImage:
    """An image placement on a page: either an embedded image (xref set) or a
    vector-figure region to crop (xref None)."""

    page: int  # 1-based
    bbox: BBox
    xref: int | None

    @property
    def y_center(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


@dataclass(frozen=True)
class PageTable:
    page: int  # 1-based
    bbox: BBox
    rows: list[list[str]]

    @property
    def y_center(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


@dataclass
class PageContent:
    number: int  # 1-based
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    images: list[PageImage] = field(default_factory=list)
    tables: list[PageTable] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)


_MONO_FLAG = 8  # PyMuPDF span flag bit for monospaced fonts


def _is_mono(span: dict, cfg: PdfParserConfig) -> bool:
    if span["flags"] & _MONO_FLAG:
        return True
    font = span["font"].lower()
    return any(hint in font for hint in cfg.mono_font_hints)


def _inside(inner: BBox, outer: BBox, slack: float = 2.0) -> bool:
    return (
        inner[0] >= outer[0] - slack
        and inner[1] >= outer[1] - slack
        and inner[2] <= outer[2] + slack
        and inner[3] <= outer[3] + slack
    )


def _center_inside(bbox: BBox, outer: BBox) -> bool:
    cx, cy = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return outer[0] <= cx <= outer[2] and outer[1] <= cy <= outer[3]


def _read_tables(page: pymupdf.Page, number: int, issues: list[Issue]) -> list[PageTable]:
    try:
        finder = page.find_tables()
    except Exception as exc:  # table detection must never sink the page
        issues.append(
            Issue(
                severity=Severity.WARNING,
                code="table_detection_failed",
                message=f"table detection failed on page {number}: {exc}",
                origin=PageRegion(page=number),
            )
        )
        return []
    tables = []
    for table in finder.tables:
        rows = [[cell if cell is not None else "" for cell in row] for row in table.extract()]
        if rows:
            tables.append(PageTable(page=number, bbox=tuple(table.bbox), rows=rows))
    return tables


def _cluster_rects(rects: list[pymupdf.Rect], gap: float) -> list[pymupdf.Rect]:
    """Merge rectangles that touch or sit within ``gap`` of each other."""
    clusters: list[pymupdf.Rect] = []
    for rect in rects:
        grown = pymupdf.Rect(rect.x0 - gap, rect.y0 - gap, rect.x1 + gap, rect.y1 + gap)
        merged = pymupdf.Rect(rect)
        remaining = []
        for cluster in clusters:
            if grown.intersects(cluster):
                merged |= cluster
            else:
                remaining.append(cluster)
        remaining.append(merged)
        clusters = remaining
    return clusters


def _figure_regions(
    page: pymupdf.Page, number: int, tables: list[PageTable], cfg: PdfParserConfig
) -> list[PageImage]:
    """Vector-drawing clusters large enough to be figures (topology diagrams
    drawn with strokes rather than embedded as images). These get cropped
    from the page later, never redrawn."""
    rects = [
        pymupdf.Rect(d["rect"])
        for d in page.get_drawings()
        if not pymupdf.Rect(d["rect"]).is_empty
    ]
    page_area = page.rect.get_area()
    regions = []
    for cluster in _cluster_rects(rects, cfg.figure_cluster_gap):
        if cluster.get_area() < cfg.min_figure_area:
            continue  # decoration: underlines, rules
        if cluster.get_area() > cfg.max_figure_page_fraction * page_area:
            continue  # page furniture: borders, backgrounds
        bbox = tuple(cluster & page.rect)
        if any(_center_inside(bbox, t.bbox) for t in tables):
            continue  # a table grid is handled as a table, not a figure
        regions.append(PageImage(page=number, bbox=bbox, xref=None))
    return regions


def read_page(doc: pymupdf.Document, index: int, cfg: PdfParserConfig) -> PageContent:
    """Read page ``index`` (0-based) into a :class:`PageContent`."""
    page = doc.load_page(index)
    number = index + 1
    content = PageContent(number=number, width=page.rect.width, height=page.rect.height)

    content.tables = _read_tables(page, number, content.issues)
    table_boxes = [t.bbox for t in content.tables]

    for block in page.get_text("dict")["blocks"]:
        if block["type"] != 0:
            continue  # image placements are read via get_images below
        for raw_line in block["lines"]:
            spans = tuple(
                Span(
                    text=s["text"],
                    bbox=tuple(s["bbox"]),
                    font=s["font"],
                    size=s["size"],
                    mono=_is_mono(s, cfg),
                )
                for s in raw_line["spans"]
                if s["text"]
            )
            if not spans or not "".join(s.text for s in spans).strip():
                continue
            line = Line(spans=spans, page=number, bbox=tuple(raw_line["bbox"]))
            if any(_inside(line.bbox, tb) for tb in table_boxes):
                continue  # cell text is carried by the TableBlock, exactly
            content.lines.append(line)
    content.lines.sort(key=lambda ln: (ln.y0, ln.x0))

    for entry in page.get_images(full=True):
        xref = entry[0]
        for rect in page.get_image_rects(xref):
            content.images.append(PageImage(page=number, bbox=tuple(rect), xref=xref))

    content.images.extend(_figure_regions(page, number, content.tables, cfg))
    content.images.sort(key=lambda im: im.y_center)
    return content
