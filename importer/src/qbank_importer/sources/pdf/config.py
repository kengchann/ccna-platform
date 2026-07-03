"""Tunable layout conventions for the PDF parser.

Every heuristic the parser applies lives here, so adapting the parser to the
canonical question-bank PDF (or any other document) means adjusting this
configuration — not the extraction code. The defaults encode common
question-bank conventions and MUST be verified against the real document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


@dataclass(frozen=True)
class PdfParserConfig:
    # --- segmentation -----------------------------------------------------
    #: A line matching any of these starts a new question. The full match is
    #: kept verbatim as the question's printed label.
    question_label_patterns: list[str] = field(
        default_factory=lambda: [
            r"^question\s+\d+\s*[:.)]?",
            r"^\d{1,4}[.)]",
        ]
    )
    #: A line matching any of these starts a scenario/case-study group whose
    #: context runs until the next question label.
    group_header_patterns: list[str] = field(
        default_factory=lambda: [
            r"^case\s+study\b.*",
            r"^scenario\b.*",
        ]
    )

    # --- classification within a question ---------------------------------
    #: Option marker; group 1 = option letter, group 2 = first content text.
    option_pattern: str = r"^([A-H])[.)]\s+(.*)$"
    #: Answer-key marker; group 1 = the raw answer text.
    answer_pattern: str = r"^(?:correct\s+)?answers?\s*[:.]\s*(.*)$"
    #: Explanation marker; group 1 = text following the marker on that line.
    explanation_pattern: str = r"^explanation\s*[:.]?\s*(.*)$"
    #: Stems containing this indicate a multi-answer question.
    choose_hint_pattern: str = r"\(choose\s+(two|three|four|\d+)\b"

    #: Font-name fragments (lowercased) treated as monospace, in addition to
    #: the PDF's own monospace flag. CLI/config content is detected this way.
    mono_font_hints: tuple[str, ...] = ("courier", "mono", "consolas")

    # --- figures and images ------------------------------------------------
    #: DPI used when cropping vector figures from the page.
    crop_dpi: int = 200
    #: Vector drawing clusters smaller than this (in PDF points²) are treated
    #: as decoration (rules, underlines), not figures.
    min_figure_area: float = 1500.0
    #: Clusters covering more than this fraction of the page are treated as
    #: page furniture (borders), not figures.
    max_figure_page_fraction: float = 0.85
    #: Two drawing rectangles closer than this (points) merge into one figure.
    figure_cluster_gap: float = 12.0

    # --- verbatim reconstruction -------------------------------------------
    #: Vertical gap between consecutive monospace lines, as a multiple of the
    #: line height, above which a blank line is inserted.
    verbatim_blank_line_gap: float = 1.8

    def label_regexes(self) -> list[re.Pattern[str]]:
        return _compile(self.question_label_patterns)

    def group_regexes(self) -> list[re.Pattern[str]]:
        return _compile(self.group_header_patterns)

    def option_regex(self) -> re.Pattern[str]:
        return re.compile(self.option_pattern, re.IGNORECASE)

    def answer_regex(self) -> re.Pattern[str]:
        return re.compile(self.answer_pattern, re.IGNORECASE)

    def explanation_regex(self) -> re.Pattern[str]:
        return re.compile(self.explanation_pattern, re.IGNORECASE)

    def choose_hint_regex(self) -> re.Pattern[str]:
        return re.compile(self.choose_hint_pattern, re.IGNORECASE)
