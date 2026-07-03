"""Tests for the PDF import source, using fixture PDFs generated in-test.

The fixtures use deliberately synthetic content and exercise the layout
conventions encoded in PdfParserConfig: question labels, option markers,
answer keys, explanation markers, monospace CLI blocks, embedded images,
vector figures, and scenario groups.
"""

import base64

import pymupdf
import pytest

from qbank_importer.model import AssetKind, GroupKind, QuestionStatus, QuestionType
from qbank_importer.pipeline import run_import
from qbank_importer.sources import ExtractedGroup, ExtractedQuestion, FailedQuestion
from qbank_importer.sources.pdf import PdfImportSource

# 1x1 red pixel
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

MARGIN = 72
CLI_CHAR_W = pymupdf.get_text_length("0", fontname="cour", fontsize=10)


class PdfBuilder:
    """Minimal fixture-PDF writer with a moving cursor."""

    def __init__(self) -> None:
        self.doc = pymupdf.open()
        self.page = self.doc.new_page(width=595, height=842)
        self.y = 72.0

    def line(self, text: str, *, font: str = "helv", size: float = 11, indent_px: float = 0):
        self.page.insert_text((MARGIN + indent_px, self.y), text, fontname=font, fontsize=size)
        self.y += size * 1.5
        return self

    def cli(self, text: str, indent_cols: int = 0):
        return self.line(text, font="cour", size=10, indent_px=indent_cols * CLI_CHAR_W)

    def gap(self, dy: float):
        self.y += dy
        return self

    def image(self, height: float = 40.0):
        rect = pymupdf.Rect(MARGIN, self.y, MARGIN + 60, self.y + height)
        self.page.insert_image(rect, stream=PNG_1PX)
        self.y += height + 12
        return self

    def figure(self, width: float = 160.0, height: float = 70.0):
        """A vector 'topology diagram': circles joined by a line."""
        top = self.y
        shape = self.page.new_shape()
        shape.draw_circle(pymupdf.Point(MARGIN + 20, top + height / 2), 14)
        shape.draw_circle(pymupdf.Point(MARGIN + width - 20, top + height / 2), 14)
        shape.draw_line(
            pymupdf.Point(MARGIN + 34, top + height / 2),
            pymupdf.Point(MARGIN + width - 34, top + height / 2),
        )
        shape.finish(width=1.5)
        shape.commit()
        self.y += height + 12
        return self

    def new_page(self):
        self.page = self.doc.new_page(width=595, height=842)
        self.y = 72.0
        return self

    def save(self, path):
        self.doc.save(str(path))
        self.doc.close()
        return path


def extract_all(path):
    return list(PdfImportSource(path).extract())


def questions_of(items):
    return [i for i in items if isinstance(i, ExtractedQuestion)]


def stem_text(question):
    return "\n".join(b.text for b in question.stem if b.kind in ("text", "verbatim"))


@pytest.fixture()
def basic_pdf(tmp_path):
    b = PdfBuilder()
    b.line("Practice Exam Fixture")  # preamble, not a question
    b.gap(10)
    b.line("1. What is the stem of question one?")
    b.line("A. Alpha option")
    b.line("B. Beta option")
    b.line("C. Gamma option")
    b.line("Answer: B")
    b.line("Explanation: Synthetic explanation text.")
    b.gap(14)
    b.line("2. Which two items apply? (Choose two)")
    b.line("A. First")
    b.line("B. Second")
    b.line("C. Third")
    b.line("D. Fourth")
    b.line("Answer: A, C")
    return b.save(tmp_path / "basic.pdf")


def test_describe(basic_pdf):
    info = PdfImportSource(basic_pdf).describe()
    assert info.format == "pdf"
    assert info.page_count == 1
    assert info.filename == "basic.pdf"


def test_two_questions_sequential(basic_pdf):
    items = extract_all(basic_pdf)
    questions = questions_of(items)
    assert len(questions) == 2
    assert not [i for i in items if isinstance(i, FailedQuestion)]

    q1, q2 = questions[0].question, questions[1].question
    assert (q1.source.ordinal, q2.source.ordinal) == (1, 2)
    assert q1.source.label == "1."
    assert q1.source.pages == [1]
    assert stem_text(q1) == "What is the stem of question one?"


def test_options_and_answer_key(basic_pdf):
    q1 = questions_of(extract_all(basic_pdf))[0].question
    inter = q1.interaction
    assert [o.id for o in inter.options] == ["a", "b", "c"]
    assert [o.label for o in inter.options] == ["A.", "B.", "C."]
    assert inter.options[0].content[0].text == "Alpha option"
    assert inter.correct_option_ids == ["b"]
    assert q1.type is QuestionType.SINGLE_CHOICE
    assert q1.explanation[0].text == "Synthetic explanation text."


def test_multiple_choice_detected(basic_pdf):
    q2 = questions_of(extract_all(basic_pdf))[1].question
    assert q2.type is QuestionType.MULTIPLE_CHOICE
    assert q2.interaction.correct_option_ids == ["a", "c"]


def test_preamble_recorded(basic_pdf):
    first = questions_of(extract_all(basic_pdf))[0]
    assert any(i.code == "preamble_skipped" for i in first.issues)


def test_cli_block_exact(tmp_path):
    expected = (
        "Router#show ip route\n"
        "  O    10.0.0.0/8 [110/2] via 10.1.1.1\n"
        "      via 10.2.2.2"
    )
    b = PdfBuilder()
    b.line("1. Refer to the output below.")
    b.cli("Router#show ip route")
    b.cli("O    10.0.0.0/8 [110/2] via 10.1.1.1", indent_cols=2)
    b.cli("via 10.2.2.2", indent_cols=6)
    b.line("A. Alpha")
    b.line("B. Beta")
    b.line("Answer: A")
    path = b.save(tmp_path / "cli.pdf")

    q = questions_of(extract_all(path))[0].question
    verbatims = [blk for blk in q.stem if blk.kind == "verbatim"]
    assert len(verbatims) == 1
    assert verbatims[0].text == expected


def test_embedded_image_extracted(tmp_path):
    b = PdfBuilder()
    b.line("1. Refer to the exhibit.")
    b.image()
    b.line("A. Alpha")
    b.line("B. Beta")
    b.line("Answer: B")
    path = b.save(tmp_path / "image.pdf")

    item = questions_of(extract_all(path))[0]
    (payload,) = item.assets
    assert payload.asset.kind is AssetKind.EMBEDDED
    assert payload.asset.media_type.startswith("image/")
    assert payload.asset.id == "q1-img1"
    assert payload.asset.origin.page == 1
    assert len(payload.data) > 0

    image_blocks = [blk for blk in item.question.stem if blk.kind == "image"]
    assert [blk.asset_id for blk in image_blocks] == ["q1-img1"]
    # Image sits between the stem text and the options, i.e. in the stem.
    assert item.question.stem[0].kind == "text"


def test_vector_figure_cropped(tmp_path):
    b = PdfBuilder()
    b.line("1. Refer to the topology diagram.")
    b.figure()
    b.line("A. Alpha")
    b.line("B. Beta")
    b.line("Answer: A")
    path = b.save(tmp_path / "figure.pdf")

    item = questions_of(extract_all(path))[0]
    crops = [p for p in item.assets if p.asset.kind is AssetKind.PAGE_CROP]
    assert len(crops) == 1
    assert crops[0].asset.media_type == "image/png"
    assert crops[0].data[:8] == b"\x89PNG\r\n\x1a\n"
    assert any(i.code == "figure_cropped" for i in item.issues)
    assert any(blk.kind == "image" for blk in item.question.stem)


def test_multipage_question(tmp_path):
    b = PdfBuilder()
    b.line("1. This stem starts on page one")
    b.line("and continues before the options.")
    b.new_page()
    b.line("A. Alpha")
    b.line("B. Beta")
    b.line("Answer: B")
    path = b.save(tmp_path / "multipage.pdf")

    q = questions_of(extract_all(path))[0].question
    assert q.source.pages == [1, 2]
    assert len(q.interaction.options) == 2
    assert "continues before the options." in stem_text(q)


def test_true_false(tmp_path):
    b = PdfBuilder()
    b.line("1. The statement is accurate.")
    b.line("A. True")
    b.line("B. False")
    b.line("Answer: B")
    path = b.save(tmp_path / "tf.pdf")

    q = questions_of(extract_all(path))[0].question
    assert q.type is QuestionType.TRUE_FALSE
    assert q.interaction.correct_option_ids == ["b"]


def test_question_without_options_is_flagged_not_dropped(tmp_path):
    b = PdfBuilder()
    b.line("1. Describe the process in your own words.")
    b.line("2. What is item two?")
    b.line("A. Alpha")
    b.line("B. Beta")
    b.line("Answer: A")
    path = b.save(tmp_path / "noopts.pdf")

    items = questions_of(extract_all(path))
    assert len(items) == 2
    q1 = items[0]
    assert q1.question.interaction.options == []
    assert any(i.code == "no_options_detected" for i in q1.issues)
    assert stem_text(q1.question) == "Describe the process in your own words."


def test_scenario_group(tmp_path):
    b = PdfBuilder()
    b.line("Scenario 1: The synthetic branch office")
    b.line("Shared context line for both questions.")
    b.line("1. First grouped question?")
    b.line("A. Alpha")
    b.line("B. Beta")
    b.line("Answer: A")
    b.line("2. Second grouped question?")
    b.line("A. Alpha")
    b.line("B. Beta")
    b.line("Answer: B")
    path = b.save(tmp_path / "scenario.pdf")

    items = extract_all(path)
    assert isinstance(items[0], ExtractedGroup)
    group = items[0].group
    assert group.kind is GroupKind.SCENARIO
    assert group.title == "Scenario 1: The synthetic branch office"
    assert "Shared context line" in group.context[0].text
    assert group.question_ids == ["q1", "q2"]

    questions = questions_of(items)
    assert [q.question.group_id for q in questions] == ["g1", "g1"]


def test_unparsed_answer_key_is_flagged(tmp_path):
    b = PdfBuilder()
    b.line("1. Stem text?")
    b.line("A. Alpha")
    b.line("B. Beta")
    b.line("Answer: see appendix")
    path = b.save(tmp_path / "badkey.pdf")

    item = questions_of(extract_all(path))[0]
    assert item.question.interaction.correct_option_ids == []
    assert any(i.code == "unparsed_answer_key" for i in item.issues)


def test_no_questions_found(tmp_path):
    b = PdfBuilder()
    b.line("Just a title page with no questions at all.")
    path = b.save(tmp_path / "empty.pdf")

    items = extract_all(path)
    assert len(items) == 1
    assert isinstance(items[0], FailedQuestion)
    assert any(i.code == "no_questions_found" for i in items[0].issues)


def test_end_to_end_pipeline(basic_pdf, tmp_path):
    outcome = run_import(PdfImportSource(basic_pdf), tmp_path / "bundle")
    assert outcome.result.questions_imported == 2
    assert outcome.result.questions_skipped == 0
    assert outcome.result.errors == 0
    statuses = {p.ordinal: p.status for p in outcome.preview.questions}
    assert statuses == {1: QuestionStatus.IMPORTED, 2: QuestionStatus.IMPORTED}
