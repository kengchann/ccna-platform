"""Stage 2 — segmentation: split the page stream into question/group slices.

A slice is everything between one question label (or group header) and the
next. Slices may span pages. Images and tables are assigned to the slice
whose vertical extent contains them on their page.

The segmenter is fed one page at a time and yields the slices that were
*completed* by that page; the still-open slice carries over, so memory is
bounded by one slice plus one page regardless of document size.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...model import GroupKind, Issue, Severity
from .config import PdfParserConfig
from .layout import Line, PageContent, PageImage, PageTable


@dataclass
class Slice:
    """One segmented unit of the document, before classification."""

    kind: str  # "question" | "group" | "preamble"
    ordinal: int | None = None  # questions only, 1-based
    label: str | None = None  # question label / group header, exactly as printed
    label_char_len: int = 0  # chars of the label to strip from the first line's text
    group_kind: GroupKind | None = None
    lines: list[Line] = field(default_factory=list)
    images: list[PageImage] = field(default_factory=list)
    tables: list[PageTable] = field(default_factory=list)
    pages: list[int] = field(default_factory=list)

    def touch_page(self, number: int) -> None:
        if number not in self.pages:
            self.pages.append(number)


class Segmenter:
    def __init__(self, cfg: PdfParserConfig) -> None:
        self._cfg = cfg
        self._label_res = cfg.label_regexes()
        self._group_res = cfg.group_regexes()
        self._open: Slice = Slice(kind="preamble")
        self._ordinal = 0
        self._preamble_lines = 0
        self._preamble_pages: list[int] = []

    def feed(self, page: PageContent) -> list[Slice]:
        """Consume one page; return the slices this page completed."""
        completed: list[Slice] = []
        # Vertical start of each slice active on this page; the carried-over
        # slice is active from the top.
        boundaries: list[tuple[float, Slice]] = [(float("-inf"), self._open)]

        for line in page.lines:
            new_slice = self._boundary_for(line)
            if new_slice is not None:
                completed.extend(self._close(self._open))
                self._open = new_slice
                boundaries.append((line.y0, new_slice))
            self._open.touch_page(page.number)
            # The boundary line itself belongs to the new slice: it carries
            # the label plus (usually) the first stem text after it, which
            # classification separates via label_char_len.
            self._open.lines.append(line)

        for image in page.images:
            self._owner_at(boundaries, image.y_center).images.append(image)
        for table in page.tables:
            self._owner_at(boundaries, table.y_center).tables.append(table)

        return completed

    def flush(self) -> list[Slice]:
        """Close the final slice at end of document."""
        return self._close(self._open)

    def preamble_note(self) -> Issue | None:
        """Audit note when content preceded the first question/group."""
        if self._preamble_lines == 0:
            return None
        pages = ", ".join(str(p) for p in self._preamble_pages)
        return Issue(
            severity=Severity.INFO,
            code="preamble_skipped",
            message=(
                f"{self._preamble_lines} line(s) before the first question "
                f"(page(s) {pages}) were not part of any question and were not imported"
            ),
        )

    def _boundary_for(self, line: Line) -> Slice | None:
        """A new slice if this line starts one, else None."""
        if line.mono:
            return None  # CLI output never starts a question/group
        text = line.text.strip()
        for regex in self._group_res:
            if match := regex.match(text):
                kind = (
                    GroupKind.CASE_STUDY if "case" in match.group(0).lower() else GroupKind.SCENARIO
                )
                return Slice(
                    kind="group",
                    label=text,
                    label_char_len=len(line.text),  # header line is all label
                    group_kind=kind,
                )
        for regex in self._label_res:
            if match := regex.match(text):
                self._ordinal += 1
                leading_ws = len(line.text) - len(line.text.lstrip())
                return Slice(
                    kind="question",
                    ordinal=self._ordinal,
                    label=match.group(0),
                    label_char_len=leading_ws + match.end(),
                )
        return None

    def _close(self, done: Slice) -> list[Slice]:
        if done.kind == "preamble":
            self._preamble_lines += len(done.lines)
            self._preamble_pages.extend(p for p in done.pages if p not in self._preamble_pages)
            return []
        return [done]

    @staticmethod
    def _owner_at(boundaries: list[tuple[float, Slice]], y: float) -> Slice:
        owner = boundaries[0][1]
        for start_y, candidate in boundaries:
            if start_y <= y:
                owner = candidate
        return owner
