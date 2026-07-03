"""Tests for the validation framework: each built-in rule independently,
plus the engine's cross-item state handling. Fixture strings are synthetic."""

from qbank_importer.model import (
    Asset,
    AssetKind,
    Blank,
    ChoiceInteraction,
    DragAndDropInteraction,
    FillInBlankInteraction,
    GroupKind,
    ImageBlock,
    Item,
    MatchingInteraction,
    MatchPair,
    OrderingInteraction,
    PageRegion,
    Placement,
    Question,
    QuestionGroup,
    QuestionType,
    SourceRef,
    TextBlock,
)
from qbank_importer.validation import Validator, default_rules


def _item(item_id: str) -> Item:
    return Item(id=item_id, label=None, content=[TextBlock(text=f"item {item_id}")])


def _choice(correct=("a",), options=("a", "b")) -> ChoiceInteraction:
    return ChoiceInteraction(
        options=[_item(o) for o in options], correct_option_ids=list(correct)
    )


def _question(
    qtype=QuestionType.SINGLE_CHOICE,
    interaction=None,
    *,
    qid="q-1",
    ordinal=1,
    label="1.",
    stem=None,
    group_id=None,
) -> Question:
    return Question(
        id=qid,
        source=SourceRef(ordinal=ordinal, label=label, pages=[1]),
        type=qtype,
        group_id=group_id,
        stem=[TextBlock(text="stem text")] if stem is None else stem,
        interaction=interaction if interaction is not None else _choice(),
    )


def codes_for(question, *, assets=(), prior=()) -> set[str]:
    """Run the default rules over optional prior items then the question."""
    validator = Validator(default_rules())
    validator.register_assets(list(assets))
    for item in prior:
        if isinstance(item, QuestionGroup):
            validator.check_group(item)
        else:
            validator.check_question(item)
    return {issue.code for issue in validator.check_question(question)}


def test_clean_question_has_no_issues():
    assert codes_for(_question()) == set()


def test_missing_question_label():
    assert "missing_question_label" in codes_for(_question(label=None))
    assert "missing_question_label" in codes_for(_question(label="   "))


def test_duplicate_question_id():
    first = _question(qid="q-1", ordinal=1)
    dup = _question(qid="q-1", ordinal=2, label="2.")
    assert "duplicate_question_id" in codes_for(dup, prior=[first])


def test_empty_stem():
    assert "empty_stem" in codes_for(_question(stem=[]))


def test_interaction_type_mismatch():
    q = _question(QuestionType.MATCHING, _choice())
    assert "interaction_type_mismatch" in codes_for(q)


def test_scenario_type_allows_any_interaction():
    q = _question(QuestionType.SCENARIO, _choice())
    assert "interaction_type_mismatch" not in codes_for(q)


def test_missing_options():
    q = _question(interaction=_choice(correct=("a",), options=("a",)))
    assert "missing_options" in codes_for(q)


def test_missing_correct_answer():
    q = _question(interaction=_choice(correct=()))
    assert "missing_correct_answer" in codes_for(q)


def test_correct_answer_referencing_unknown_option():
    q = _question(interaction=_choice(correct=("zz",)))
    assert "invalid_answer_reference" in codes_for(q)


def test_single_choice_with_two_answers():
    q = _question(interaction=_choice(correct=("a", "b")))
    assert "answer_count_mismatch" in codes_for(q)
    multi = _question(QuestionType.MULTIPLE_CHOICE, _choice(correct=("a", "b")), label="2.")
    assert "answer_count_mismatch" not in codes_for(multi)


def test_true_false_option_count():
    q = _question(
        QuestionType.TRUE_FALSE, _choice(correct=("a",), options=("a", "b", "c"))
    )
    assert "answer_count_mismatch" in codes_for(q)


def test_invalid_ordering():
    inter = OrderingInteraction(items=[_item("x"), _item("y")], correct_order=["x"])
    assert "invalid_ordering" in codes_for(_question(QuestionType.ORDERING, inter))


def test_broken_matching_pairs():
    inter = MatchingInteraction(
        left=[_item("l1")],
        right=[_item("r1")],
        pairs=[MatchPair(left_id="l1", right_id="nope")],
    )
    assert "invalid_matching_pairs" in codes_for(_question(QuestionType.MATCHING, inter))


def test_invalid_drag_drop_mapping():
    inter = DragAndDropInteraction(
        tokens=[_item("t1")],
        targets=[_item("z1")],
        placements=[Placement(token_id="t9", target_id="z1")],
    )
    assert "invalid_drag_drop_mapping" in codes_for(
        _question(QuestionType.DRAG_AND_DROP, inter)
    )


def test_blank_without_accepted_answers():
    inter = FillInBlankInteraction(blanks=[Blank(id="b1", accepted=[])])
    assert "missing_correct_answer" in codes_for(
        _question(QuestionType.FILL_IN_BLANK, inter)
    )


def test_missing_image_reference():
    q = _question(stem=[TextBlock(text="stem text"), ImageBlock(asset_id="nope")])
    assert "missing_asset" in codes_for(q)


def test_image_reference_with_registered_asset_is_clean():
    asset = Asset(
        id="img-1",
        kind=AssetKind.EMBEDDED,
        media_type="image/png",
        filename="img-1.png",
        origin=PageRegion(page=1),
        sha256="0" * 64,
    )
    q = _question(stem=[TextBlock(text="stem text"), ImageBlock(asset_id="img-1")])
    assert "missing_asset" not in codes_for(q, assets=[asset])


def _group(members=("q-1",)) -> QuestionGroup:
    return QuestionGroup(
        id="g-1",
        kind=GroupKind.SCENARIO,
        title=None,
        context=[TextBlock(text="shared context")],
        question_ids=list(members),
    )


def test_unknown_group_reference():
    q = _question(group_id="g-404")
    assert "unknown_group" in codes_for(q)


def test_question_not_listed_by_its_group():
    q = _question(qid="q-9", group_id="g-1", label="9.")
    assert "group_member_mismatch" in codes_for(q, prior=[_group(members=("q-1",))])


def test_group_member_never_imported():
    validator = Validator(default_rules())
    validator.check_group(_group(members=("q-1", "q-missing")))
    validator.check_question(_question(qid="q-1", group_id="g-1"))
    codes = {issue.code for issue in validator.finish()}
    assert "missing_group_member" in codes


def test_custom_rule_set_is_respected():
    # The engine runs exactly the rules it is given — adding/removing rules
    # requires no engine changes.
    validator = Validator(rules=[])
    assert validator.check_question(_question(label=None, stem=[])) == []
