"""Content-block building from laid-out flow items.

Turns an ordered mix of text lines, image placements, and tables into
ContentBlocks. Prose lines keep their exact text and line breaks; monospace
runs are reconstructed into VerbatimBlocks with indentation and intra-line
gaps rebuilt from glyph coordinates, because PDFs store positions, not the
spaces the author typed.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Union

from ...model import ContentBlock, ImageBlock, TableBlock, TextBlock, VerbatimBlock
from .config import PdfParserConfig
from .layout import Line, PageTable


@dataclass(frozen=True)
class FlowText:
    line: Line
    #: chars to strip from the start of the text (question label prefix).
    strip_prefix: int = 0

    @property
    def text(self) -> str:
        return self.line.text[self.strip_prefix :].lstrip() if self.strip_prefix else self.line.text

    @property
    def sort_key(self) -> tuple[int, float]:
        return (self.line.page, self.line.y0)


@dataclass(frozen=True)
class FlowImage:
    asset_id: str
    page: int
    y: float

    @property
    def sort_key(self) -> tuple[int, float]:
        return (self.page, self.y)


@dataclass(frozen=True)
class FlowTable:
    table: PageTable

    @property
    def sort_key(self) -> tuple[int, float]:
        return (self.table.page, self.table.y_center)


FlowItem = Union[FlowText, FlowImage, FlowTable]


def _char_width(lines: list[Line]) -> float:
    widths = [
        (s.bbox[2] - s.bbox[0]) / len(s.text)
        for line in lines
        for s in line.spans
        if s.text
    ]
    return statistics.median(widths) if widths else 1.0


def reconstruct_verbatim(lines: list[Line], cfg: PdfParserConfig) -> str:
    """Rebuild the exact text of a monospace run.

    Leading indentation and gaps between spans are recovered from x
    coordinates in units of the (monospace) character width, relative to the
    leftmost line of the run. Vertical gaps larger than
    ``verbatim_blank_line_gap`` line-heights become blank lines.
    """
    char_w = _char_width(lines)
    base_x = min(line.x0 for line in lines)
    heights = [line.y1 - line.y0 for line in lines]
    line_h = statistics.median(heights) if heights else 10.0

    out: list[str] = []
    prev_y0: float | None = None
    prev_page: int | None = None
    for line in lines:
        if prev_y0 is not None and line.page == prev_page:
            if (line.y0 - prev_y0) > cfg.verbatim_blank_line_gap * line_h:
                out.append("")
        text = " " * max(0, round((line.x0 - base_x) / char_w))
        cursor = line.x0
        for span in line.spans:
            gap = max(0, round((span.bbox[0] - cursor) / char_w))
            text += " " * gap + span.text
            cursor = span.bbox[2]
        out.append(text)
        prev_y0, prev_page = line.y0, line.page
    return "\n".join(out)


class BlockBuilder:
    """Accumulates flow items into a ContentBlock list, merging consecutive
    prose lines into one TextBlock and monospace runs into one VerbatimBlock."""

    def __init__(self, cfg: PdfParserConfig) -> None:
        self._cfg = cfg
        self._blocks: list[ContentBlock] = []
        self._prose: list[str] = []
        self._mono: list[Line] = []

    def add_text(self, item: FlowText) -> None:
        if item.line.mono:
            self._flush_prose()
            self._mono.append(item.line)
        else:
            self._flush_mono()
            text = item.text
            if text.strip():
                self._prose.append(text)

    def add_image(self, asset_id: str) -> None:
        self._flush_all()
        self._blocks.append(ImageBlock(asset_id=asset_id))

    def add_table(self, table: PageTable) -> None:
        self._flush_all()
        self._blocks.append(TableBlock(rows=table.rows))

    def build(self) -> list[ContentBlock]:
        self._flush_all()
        blocks, self._blocks = self._blocks, []
        return blocks

    def _flush_prose(self) -> None:
        if self._prose:
            self._blocks.append(TextBlock(text="\n".join(self._prose)))
            self._prose = []

    def _flush_mono(self) -> None:
        if self._mono:
            self._blocks.append(
                VerbatimBlock(text=reconstruct_verbatim(self._mono, self._cfg))
            )
            self._mono = []

    def _flush_all(self) -> None:
        self._flush_prose()
        self._flush_mono()
