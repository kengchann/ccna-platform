"""Stage 3 — classification: structure the flow of one question slice.

A state machine walks the slice's flow items (text lines, images, tables in
reading order) and routes content into stem, answer options, answer key, and
explanation. Everything ambiguous is imported anyway and flagged with an
Issue — never dropped, never repaired.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ...model import (
    ContentBlock,
    Issue,
    Item,
    PageRegion,
    QuestionType,
    Severity,
)
from .blocks import BlockBuilder, FlowImage, FlowItem, FlowTable, FlowText
from .config import PdfParserConfig

_LETTER_RE = re.compile(r"\b([A-H])\b")


def parse_answer_letters(raw: str) -> list[str]:
    """Extract option letters from an answer-key string ("B", "A, C",
    "A and C", "AC"). Returns lowercased letters in order, deduplicated;
    empty when nothing parseable."""
    letters = [m.group(1) for m in _LETTER_RE.finditer(raw.upper())]
    if not letters:
        compact = re.sub(r"[\s,;/&+.-]", "", raw.upper())
        if compact and all(c in "ABCDEFGH" for c in compact):
            letters = list(compact)
    seen: set[str] = set()
    out: list[str] = []
    for letter in letters:
        if letter.lower() not in seen:
            seen.add(letter.lower())
            out.append(letter.lower())
    return out


@dataclass
class ClassifiedQuestion:
    stem: list[ContentBlock] = field(default_factory=list)
    options: list[Item] = field(default_factory=list)
    correct_ids: list[str] = field(default_factory=list)
    explanation: list[ContentBlock] = field(default_factory=list)
    qtype: QuestionType = QuestionType.SINGLE_CHOICE
    issues: list[Issue] = field(default_factory=list)


class _OptionAccumulator:
    """Collects one option's content through its own BlockBuilder."""

    def __init__(self, letter: str, label: str, cfg: PdfParserConfig) -> None:
        self.letter = letter
        self.label = label
        self.builder = BlockBuilder(cfg)

    def to_item(self) -> Item:
        return Item(id=self.letter, label=self.label, content=self.builder.build())


class QuestionClassifier:
    _STEM, _OPTIONS, _EXPLANATION = "stem", "options", "explanation"

    def __init__(self, cfg: PdfParserConfig) -> None:
        self._cfg = cfg
        self._option_re = cfg.option_regex()
        self._answer_re = cfg.answer_regex()
        self._explanation_re = cfg.explanation_regex()
        self._choose_re = cfg.choose_hint_regex()

    def classify(self, flow: list[FlowItem], page_hint: int) -> ClassifiedQuestion:
        result = ClassifiedQuestion()
        stem = BlockBuilder(self._cfg)
        explanation = BlockBuilder(self._cfg)
        options: list[_OptionAccumulator] = []
        phase = self._STEM
        answer_seen = False
        unmarked_tail_flagged = False

        def current_builder() -> BlockBuilder:
            if phase == self._EXPLANATION:
                return explanation
            if phase == self._OPTIONS and options:
                return options[-1].builder
            return stem

        for item in flow:
            if isinstance(item, FlowImage):
                current_builder().add_image(item.asset_id)
                continue
            if isinstance(item, FlowTable):
                current_builder().add_table(item.table)
                continue

            line = item.line
            if line.mono:
                # CLI/config output is content, never a marker.
                current_builder().add_text(item)
                continue
            text = item.text.strip()

            if match := self._explanation_re.match(text):
                phase = self._EXPLANATION
                remainder = match.group(1)
                if remainder.strip():
                    explanation.add_text(_synthetic(item, remainder))
                continue

            if match := self._answer_re.match(text):
                letters = parse_answer_letters(match.group(1))
                if answer_seen:
                    result.issues.append(
                        _issue(
                            "multiple_answer_keys",
                            f"second answer key found: {text!r}",
                            line.page,
                        )
                    )
                if letters:
                    result.correct_ids.extend(
                        letter for letter in letters if letter not in result.correct_ids
                    )
                else:
                    result.issues.append(
                        _issue(
                            "unparsed_answer_key",
                            f"could not parse answer key text: {match.group(1)!r}",
                            line.page,
                        )
                    )
                answer_seen = True
                continue

            if phase != self._EXPLANATION and (match := self._option_re.match(text)):
                if answer_seen:
                    result.issues.append(
                        _issue(
                            "option_after_answer_key",
                            f"option line {match.group(0)!r} appears after the answer key",
                            line.page,
                        )
                    )
                phase = self._OPTIONS
                accumulator = _OptionAccumulator(
                    letter=match.group(1).lower(),
                    label=text[: match.start(2)].rstrip(),
                    cfg=self._cfg,
                )
                if match.group(2).strip():
                    accumulator.builder.add_text(_synthetic(item, match.group(2)))
                options.append(accumulator)
                continue

            if answer_seen and phase != self._EXPLANATION:
                # Prose after the answer key without an "Explanation" marker:
                # keep it (as explanation) and flag it rather than guessing.
                phase = self._EXPLANATION
                if not unmarked_tail_flagged:
                    result.issues.append(
                        _issue(
                            "unmarked_text_after_answer",
                            "text after the answer key without an explanation "
                            "marker was imported as explanation",
                            line.page,
                        )
                    )
                    unmarked_tail_flagged = True

            current_builder().add_text(item)

        result.stem = stem.build()
        result.options = [o.to_item() for o in options]
        result.explanation = explanation.build()
        result.qtype = self._infer_type(result, page_hint)
        return result

    def _infer_type(self, result: ClassifiedQuestion, page_hint: int) -> QuestionType:
        if not result.options:
            result.issues.append(
                _issue(
                    "no_options_detected",
                    "no answer options were detected; imported as single choice "
                    "with empty options for review",
                    page_hint,
                )
            )
            return QuestionType.SINGLE_CHOICE

        texts = {_first_text(o).strip().lower() for o in result.options}
        if len(result.options) == 2 and texts == {"true", "false"}:
            return QuestionType.TRUE_FALSE

        stem_text = " ".join(b.text for b in result.stem if b.kind == "text")
        if len(result.correct_ids) > 1 or self._choose_re.search(stem_text):
            return QuestionType.MULTIPLE_CHOICE
        return QuestionType.SINGLE_CHOICE


def _first_text(item: Item) -> str:
    for block in item.content:
        if block.kind == "text":
            return block.text
    return ""


def _issue(code: str, message: str, page: int) -> Issue:
    return Issue(
        severity=Severity.WARNING,
        code=code,
        message=message,
        origin=PageRegion(page=page),
    )


def _synthetic(item: FlowText, text: str) -> FlowText:
    """A FlowText whose visible text is ``text`` (a suffix of the original
    line, e.g. option content after its marker), same line geometry."""
    offset = item.line.text.find(text)
    return FlowText(line=item.line, strip_prefix=offset if offset >= 0 else 0)
