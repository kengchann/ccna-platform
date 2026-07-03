"""Tests for the Normalizer stage: id assignment, deduplication, and
reference remapping. Content must never change."""

from qbank_importer.model import (
    Asset,
    AssetKind,
    ChoiceInteraction,
    GroupKind,
    ImageBlock,
    Item,
    PageRegion,
    Question,
    QuestionGroup,
    QuestionType,
    SourceRef,
    TextBlock,
)
from qbank_importer.pipeline import Normalizer
from qbank_importer.sources import AssetPayload, ExtractedGroup, ExtractedQuestion, FailedQuestion


def _asset(asset_id: str) -> AssetPayload:
    return AssetPayload(
        asset=Asset(
            id=asset_id,
            kind=AssetKind.EMBEDDED,
            media_type="image/png",
            filename="",
            origin=PageRegion(page=1),
            sha256="",
        ),
        data=b"fake-bytes",
    )


def _question(qid: str, ordinal: int, stem=None) -> ExtractedQuestion:
    return ExtractedQuestion(
        question=Question(
            id=qid,
            source=SourceRef(ordinal=ordinal, label=f"{ordinal}.", pages=[1]),
            type=QuestionType.SINGLE_CHOICE,
            stem=stem if stem is not None else [TextBlock(text="stem text")],
            interaction=ChoiceInteraction(
                options=[
                    Item(id="a", label="A.", content=[TextBlock(text="option a")]),
                    Item(id="b", label="B.", content=[TextBlock(text="option b")]),
                ],
                correct_option_ids=["a"],
            ),
        )
    )


def test_missing_question_id_is_assigned_from_ordinal():
    normalizer = Normalizer()
    item = normalizer.apply(_question("", 7))
    assert item.question.id == "q7"
    assert [i.code for i in item.issues] == ["assigned_id"]


def test_duplicate_question_id_is_remapped_and_flagged():
    normalizer = Normalizer()
    first = normalizer.apply(_question("q-1", 1))
    second = normalizer.apply(_question("q-1", 2))
    assert first.question.id == "q-1"
    assert second.question.id == "q-1-dup2"
    assert [i.code for i in second.issues] == ["duplicate_question_id_remapped"]


def test_duplicate_asset_id_remap_updates_image_blocks():
    normalizer = Normalizer()
    q1 = _question("q-1", 1)
    q1.assets = [_asset("img-1")]
    q2 = _question("q-2", 2, stem=[TextBlock(text="stem text"), ImageBlock(asset_id="img-1")])
    q2.assets = [_asset("img-1")]  # collides with q1's asset

    normalizer.apply(q1)
    normalized = normalizer.apply(q2)

    new_id = normalized.assets[0].asset.id
    assert new_id != "img-1"
    # The ImageBlock inside q2 follows its own asset to the new id.
    assert normalized.question.stem[1].asset_id == new_id
    assert any(i.code == "duplicate_asset_id_remapped" for i in normalized.issues)


def test_content_is_never_modified():
    normalizer = Normalizer()
    original = _question("", 3)
    original_stem_text = original.question.stem[0].text
    normalized = normalizer.apply(original)
    assert normalized.question.stem[0].text == original_stem_text
    assert normalized.question.interaction == original.question.interaction


def test_group_and_failed_items_pass_through():
    normalizer = Normalizer()
    group = ExtractedGroup(
        group=QuestionGroup(
            id="",
            kind=GroupKind.CASE_STUDY,
            title=None,
            context=[TextBlock(text="shared context")],
            question_ids=["q-1"],
        )
    )
    normalized = normalizer.apply(group)
    assert normalized.group.id == "g1"
    assert normalized.group.context[0].text == "shared context"

    failed = FailedQuestion(ordinal=9, issues=[])
    assert normalizer.apply(failed) is failed
