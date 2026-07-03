"""Rules for question identity and basic structure."""

from __future__ import annotations

from typing import Iterator

from ...model import (
    ChoiceInteraction,
    DragAndDropInteraction,
    FillInBlankInteraction,
    Issue,
    MatchingInteraction,
    OrderingInteraction,
    Question,
    QuestionType,
)
from ..base import RunState, ValidationRule


class MissingQuestionLabelRule(ValidationRule):
    """The source usually numbers its questions; a question without a printed
    label suggests the segmenter guessed a boundary."""

    code = "missing_question_label"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        if question.source.label is None or not question.source.label.strip():
            yield self.issue(
                f"question at ordinal {question.source.ordinal} has no printed question number"
            )


class DuplicateQuestionIdRule(ValidationRule):
    code = "duplicate_question_id"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        first = state.seen_question_ids.get(question.id)
        if first is not None:
            yield self.issue(
                f"question id {question.id!r} already used at ordinal {first}"
            )


class EmptyStemRule(ValidationRule):
    code = "empty_stem"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        if not question.stem:
            yield self.issue("question has no stem content")


#: Which interaction kind each question type requires. Scenario and
#: case-study questions may use any interaction (their type describes the
#: framing, not the response mechanic).
_REQUIRED_INTERACTION: dict[QuestionType, type] = {
    QuestionType.SINGLE_CHOICE: ChoiceInteraction,
    QuestionType.MULTIPLE_CHOICE: ChoiceInteraction,
    QuestionType.TRUE_FALSE: ChoiceInteraction,
    QuestionType.DRAG_AND_DROP: DragAndDropInteraction,
    QuestionType.MATCHING: MatchingInteraction,
    QuestionType.ORDERING: OrderingInteraction,
    QuestionType.FILL_IN_BLANK: FillInBlankInteraction,
}


class InteractionTypeRule(ValidationRule):
    """The declared question type must match the interaction the parser
    produced (an "invalid question type" is really a type/structure clash)."""

    code = "interaction_type_mismatch"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        required = _REQUIRED_INTERACTION.get(question.type)
        if required is not None and not isinstance(question.interaction, required):
            yield self.issue(
                f"question type {question.type.value!r} requires a "
                f"{required.model_fields['kind'].default!r} interaction, "
                f"got {question.interaction.kind!r}"
            )
