"""End-to-end pipeline test with an in-memory fake source: everything written
to a bundle must read back byte-identical. No PDF involved — this pins the
format-agnostic half of the importer."""

import hashlib
from typing import Iterator

import pytest

from qbank_importer.bundle import BundleReader
from qbank_importer.errors import BundleError
from qbank_importer.model import (
    Asset,
    AssetKind,
    ChoiceInteraction,
    GroupKind,
    ImageBlock,
    Issue,
    Item,
    PageRegion,
    Question,
    QuestionGroup,
    QuestionStatus,
    QuestionType,
    Severity,
    SourceInfo,
    SourceRef,
    TextBlock,
    VerbatimBlock,
)
from qbank_importer.pipeline import run_import
from qbank_importer.sources import (
    AssetPayload,
    ExtractedGroup,
    ExtractedItem,
    ExtractedQuestion,
    FailedQuestion,
    ImportSource,
)

FAKE_IMAGE_BYTES = b"\x89PNG-not-a-real-image-just-bytes"
CLI_TEXT = "Switch#show vlan brief\n  1   default    active\n\n"


def _asset(asset_id: str) -> Asset:
    return Asset(
        id=asset_id,
        kind=AssetKind.EMBEDDED,
        media_type="image/png",
        filename="",  # filled in by the bundle writer
        origin=PageRegion(page=2, bbox=(10.0, 20.0, 110.0, 220.0)),
        sha256="",  # filled in by the bundle writer
    )


class FakeSource(ImportSource):
    format_name = "fake"

    def describe(self) -> SourceInfo:
        return SourceInfo(
            format="fake",
            filename="fake-source.bin",
            sha256="0" * 64,
            size_bytes=123,
            page_count=3,
        )

    def extract(self) -> Iterator[ExtractedItem]:
        yield ExtractedGroup(
            group=QuestionGroup(
                id="g-1",
                kind=GroupKind.SCENARIO,
                title="group title",
                context=[TextBlock(text="shared context")],
                question_ids=["q-1"],
            )
        )
        yield ExtractedQuestion(
            question=Question(
                id="q-1",
                source=SourceRef(ordinal=1, label="1.", pages=[1, 2]),
                type=QuestionType.SINGLE_CHOICE,
                group_id="g-1",
                stem=[
                    TextBlock(text="stem text"),
                    VerbatimBlock(text=CLI_TEXT, language_hint="cisco-cli"),
                    ImageBlock(asset_id="img-1", caption=None),
                ],
                interaction=ChoiceInteraction(
                    options=[
                        Item(id="a", label="A.", content=[TextBlock(text="option a")]),
                        Item(id="b", label="B.", content=[TextBlock(text="option b")]),
                    ],
                    correct_option_ids=["a"],
                ),
            ),
            assets=[AssetPayload(asset=_asset("img-1"), data=FAKE_IMAGE_BYTES)],
        )
        # Single-choice with two marked answers: must import but need review.
        yield ExtractedQuestion(
            question=Question(
                id="q-2",
                source=SourceRef(ordinal=2, label="2.", pages=[3]),
                type=QuestionType.SINGLE_CHOICE,
                stem=[TextBlock(text="stem text two")],
                interaction=ChoiceInteraction(
                    options=[
                        Item(id="a", label="A.", content=[TextBlock(text="option a")]),
                        Item(id="b", label="B.", content=[TextBlock(text="option b")]),
                    ],
                    correct_option_ids=["a", "b"],
                ),
            ),
        )
        yield FailedQuestion(
            ordinal=3,
            issues=[
                Issue(
                    severity=Severity.ERROR,
                    code="unreadable_region",
                    message="synthetic failure",
                    origin=PageRegion(page=3),
                )
            ],
        )


@pytest.fixture()
def bundle(tmp_path):
    out = tmp_path / "bundle"
    outcome = run_import(FakeSource(), out)
    return out, outcome


def test_manifest_counts(bundle):
    _, outcome = bundle
    manifest = outcome.manifest
    assert manifest.question_count == 2
    assert manifest.group_count == 1
    assert manifest.asset_count == 1
    assert manifest.source.filename == "fake-source.bin"


def test_questions_read_back_identical(bundle):
    out, _ = bundle
    reader = BundleReader(out)
    questions = {q.id: q for q in reader.questions()}
    assert set(questions) == {"q-1", "q-2"}
    stem = questions["q-1"].stem
    assert stem[1].text == CLI_TEXT  # verbatim whitespace intact
    assert stem[2].asset_id == "img-1"
    assert [g.id for g in reader.groups()] == ["g-1"]


def test_asset_bytes_and_metadata_preserved(bundle):
    out, _ = bundle
    reader = BundleReader(out)
    (asset,) = list(reader.assets())
    assert asset.id == "img-1"
    data = reader.asset_path(asset.filename).read_bytes()
    assert data == FAKE_IMAGE_BYTES
    assert asset.sha256 == hashlib.sha256(FAKE_IMAGE_BYTES).hexdigest()
    assert asset.origin.page == 2  # provenance survives


def test_report_statuses(bundle):
    out, outcome = bundle
    by_ordinal = {r.ordinal: r for r in outcome.report.results}
    assert by_ordinal[1].status is QuestionStatus.IMPORTED
    assert by_ordinal[2].status is QuestionStatus.NEEDS_REVIEW
    assert any(i.code == "answer_count_mismatch" for i in by_ordinal[2].issues)
    assert by_ordinal[3].status is QuestionStatus.FAILED
    # report.json is readable from the bundle too
    assert BundleReader(out).report().count(QuestionStatus.FAILED) == 1


def test_writer_refuses_non_empty_output(bundle, tmp_path):
    out, _ = bundle
    with pytest.raises(BundleError, match="not empty"):
        run_import(FakeSource(), out)


def test_reader_rejects_asset_path_escape(bundle):
    out, _ = bundle
    with pytest.raises(BundleError, match="escapes"):
        BundleReader(out).asset_path("..\\..\\evil.bin")


def test_import_result_summary(bundle):
    _, outcome = bundle
    result = outcome.result
    assert result.questions_imported == 2
    assert result.questions_needing_review == 1
    assert result.questions_skipped == 1
    assert result.groups_imported == 1
    assert result.images_imported == 1
    assert result.warnings >= 1  # q-2's answer_count_mismatch
    assert result.errors == 1  # ordinal 3's unreadable_region
    assert result.elapsed_seconds >= 0


def test_preview_built_during_run(bundle):
    _, outcome = bundle
    preview = outcome.preview
    assert [g.group_id for g in preview.groups] == ["g-1"]

    q1 = next(q for q in preview.questions if q.question_id == "q-1")
    assert q1.type is QuestionType.SINGLE_CHOICE
    assert q1.status is QuestionStatus.IMPORTED
    assert CLI_TEXT in q1.stem_text  # verbatim text intact in the projection
    assert [c.is_correct for c in q1.choices] == [True, False]
    (image,) = q1.images
    assert image.asset_id == "img-1"
    assert image.filename == "img-1.png"

    q2 = next(q for q in preview.questions if q.question_id == "q-2")
    assert q2.status is QuestionStatus.NEEDS_REVIEW
    assert any(i.code == "answer_count_mismatch" for i in q2.warnings)

    (failed,) = preview.failed
    assert failed.ordinal == 3


def test_preview_from_bundle_matches_run(bundle):
    out, outcome = bundle
    from qbank_importer.pipeline import preview_from_bundle

    reopened = preview_from_bundle(out)
    assert [q.question_id for q in reopened.questions] == [
        q.question_id for q in outcome.preview.questions
    ]
    assert [q.status for q in reopened.questions] == [
        q.status for q in outcome.preview.questions
    ]
    assert reopened.questions[0].stem == outcome.preview.questions[0].stem
    assert [f.ordinal for f in reopened.failed] == [3]
