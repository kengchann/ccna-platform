"""Structural tests for the canonical model: serialization round-trips and
integrity validators. Fixture strings are deliberately synthetic — these
tests exercise the schema, not question content."""

import pytest
from pydantic import ValidationError

from qbank_importer.model import (
    Blank,
    ChoiceInteraction,
    DragAndDropInteraction,
    FillInBlankInteraction,
    Item,
    MatchingInteraction,
    MatchPair,
    OrderingInteraction,
    Placement,
    Question,
    QuestionType,
    SourceRef,
    TextBlock,
    VerbatimBlock,
)


def _item(item_id: str) -> Item:
    return Item(id=item_id, label=None, content=[TextBlock(text=f"item {item_id}")])


def _question(qtype: QuestionType, interaction) -> Question:
    return Question(
        id="q-1",
        source=SourceRef(ordinal=1, label="1.", pages=[1]),
        type=qtype,
        stem=[TextBlock(text="stem text")],
        interaction=interaction,
    )


INTERACTIONS = [
    (
        QuestionType.SINGLE_CHOICE,
        ChoiceInteraction(options=[_item("a"), _item("b")], correct_option_ids=["a"]),
    ),
    (
        QuestionType.ORDERING,
        OrderingInteraction(items=[_item("x"), _item("y")], correct_order=["y", "x"]),
    ),
    (
        QuestionType.MATCHING,
        MatchingInteraction(
            left=[_item("l1")],
            right=[_item("r1"), _item("r2")],
            pairs=[MatchPair(left_id="l1", right_id="r2")],
        ),
    ),
    (
        QuestionType.DRAG_AND_DROP,
        DragAndDropInteraction(
            tokens=[_item("t1"), _item("t2")],
            targets=[_item("z1")],
            placements=[Placement(token_id="t1", target_id="z1")],
        ),
    ),
    (
        QuestionType.FILL_IN_BLANK,
        FillInBlankInteraction(blanks=[Blank(id="b1", accepted=["answer text"])]),
    ),
]


@pytest.mark.parametrize("qtype,interaction", INTERACTIONS, ids=lambda v: getattr(v, "value", ""))
def test_question_json_round_trip(qtype, interaction):
    original = _question(qtype, interaction)
    restored = Question.model_validate_json(original.model_dump_json())
    assert restored == original
    assert restored.interaction.kind == interaction.kind


def test_verbatim_text_survives_round_trip_exactly():
    cli_text = "Router#show ip route\r\n   O    10.0.0.0/8 [110/2]\n\tvia 192.0.2.1\n\n"
    block = VerbatimBlock(text=cli_text, language_hint="cisco-cli")
    restored = VerbatimBlock.model_validate_json(block.model_dump_json())
    assert restored.text == cli_text


def test_broken_answer_key_is_constructible():
    # Referential problems must NOT be rejected at the model level: a question
    # with a broken answer key is imported and flagged by the validation
    # rules ("flag, don't fix"), so the model has to accept it.
    inter = ChoiceInteraction(options=[_item("a")], correct_option_ids=["zz"])
    restored = Question.model_validate_json(
        _question(QuestionType.SINGLE_CHOICE, inter).model_dump_json()
    )
    assert restored.interaction.correct_option_ids == ["zz"]


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        TextBlock(text="stem text", surprise="field")
