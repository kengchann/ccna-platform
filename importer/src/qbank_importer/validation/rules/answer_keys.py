"""Rules for answer keys, one per interaction kind.

Each rule only inspects its own interaction kind and ignores every other
question, so the rules stay independent and individually testable.
"""

from __future__ import annotations

from typing import Iterator

from ...model import (
    ChoiceInteraction,
    DragAndDropInteraction,
    FillInBlankInteraction,
    Issue,
    Item,
    MatchingInteraction,
    OrderingInteraction,
    Question,
    QuestionType,
)
from ..base import RunState, ValidationRule


def _duplicates(items: list[Item]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for item in items:
        if item.id in seen:
            dupes.append(item.id)
        seen.add(item.id)
    return dupes


def _unknown(referenced: list[str], items: list[Item]) -> list[str]:
    known = {i.id for i in items}
    return [r for r in referenced if r not in known]


class ChoiceAnswerRule(ValidationRule):
    code = "invalid_choice_answer"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        inter = question.interaction
        if not isinstance(inter, ChoiceInteraction):
            return

        if len(inter.options) < 2:
            yield self.issue(
                f"choice question has {len(inter.options)} answer option(s)",
                code="missing_options",
            )
        if dupes := _duplicates(inter.options):
            yield self.issue(f"duplicate option ids: {dupes}", code="duplicate_option_ids")

        n_correct = len(inter.correct_option_ids)
        if n_correct == 0:
            yield self.issue("no correct answer is marked", code="missing_correct_answer")
        elif unknown := _unknown(inter.correct_option_ids, inter.options):
            yield self.issue(
                f"correct answer references unknown option ids: {unknown}",
                code="invalid_answer_reference",
            )

        if question.type is QuestionType.SINGLE_CHOICE and n_correct > 1:
            yield self.issue(
                f"single-choice question has {n_correct} marked answers",
                code="answer_count_mismatch",
            )
        if question.type is QuestionType.TRUE_FALSE:
            if len(inter.options) != 2:
                yield self.issue(
                    f"true/false question has {len(inter.options)} options",
                    code="answer_count_mismatch",
                )
            if n_correct > 1:
                yield self.issue(
                    f"true/false question has {n_correct} marked answers",
                    code="answer_count_mismatch",
                )


class OrderingAnswerRule(ValidationRule):
    code = "invalid_ordering"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        inter = question.interaction
        if not isinstance(inter, OrderingInteraction):
            return
        if dupes := _duplicates(inter.items):
            yield self.issue(f"duplicate ordering item ids: {dupes}")
        if not inter.correct_order:
            yield self.issue("no correct order is defined", code="missing_correct_answer")
        elif sorted(inter.correct_order) != sorted(i.id for i in inter.items):
            yield self.issue(
                "correct_order does not list each ordering item exactly once"
            )


class MatchingAnswerRule(ValidationRule):
    code = "invalid_matching_pairs"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        inter = question.interaction
        if not isinstance(inter, MatchingInteraction):
            return
        if dupes := _duplicates(inter.left) + _duplicates(inter.right):
            yield self.issue(f"duplicate matching item ids: {dupes}")
        if not inter.pairs:
            yield self.issue("no matching pairs are defined", code="missing_correct_answer")
        if unknown := _unknown([p.left_id for p in inter.pairs], inter.left):
            yield self.issue(f"pairs reference unknown left item ids: {unknown}")
        if unknown := _unknown([p.right_id for p in inter.pairs], inter.right):
            yield self.issue(f"pairs reference unknown right item ids: {unknown}")


class DragAndDropAnswerRule(ValidationRule):
    code = "invalid_drag_drop_mapping"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        inter = question.interaction
        if not isinstance(inter, DragAndDropInteraction):
            return
        if dupes := _duplicates(inter.tokens) + _duplicates(inter.targets):
            yield self.issue(f"duplicate drag-and-drop item ids: {dupes}")
        if not inter.placements:
            yield self.issue("no correct placements are defined", code="missing_correct_answer")
        if unknown := _unknown([p.token_id for p in inter.placements], inter.tokens):
            yield self.issue(f"placements reference unknown token ids: {unknown}")
        if unknown := _unknown([p.target_id for p in inter.placements], inter.targets):
            yield self.issue(f"placements reference unknown target ids: {unknown}")


class FillInBlankAnswerRule(ValidationRule):
    code = "invalid_blanks"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        inter = question.interaction
        if not isinstance(inter, FillInBlankInteraction):
            return
        if not inter.blanks:
            yield self.issue("question has no blanks defined", code="missing_correct_answer")
        ids = [b.id for b in inter.blanks]
        if len(ids) != len(set(ids)):
            yield self.issue(f"duplicate blank ids: {ids}", code="duplicate_blank_ids")
        for blank in inter.blanks:
            if not blank.accepted:
                yield self.issue(
                    f"blank {blank.id!r} has no accepted answers",
                    code="missing_correct_answer",
                )
