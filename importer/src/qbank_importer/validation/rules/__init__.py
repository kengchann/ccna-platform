"""Built-in validation rules.

To add a rule: subclass :class:`~qbank_importer.validation.base.ValidationRule`
in the module matching its concern (or a new module), then add it to
:func:`default_rules`. Nothing else changes.
"""

from __future__ import annotations

from ..base import ValidationRule
from .answer_keys import (
    ChoiceAnswerRule,
    DragAndDropAnswerRule,
    FillInBlankAnswerRule,
    MatchingAnswerRule,
    OrderingAnswerRule,
)
from .basics import (
    DuplicateQuestionIdRule,
    EmptyStemRule,
    InteractionTypeRule,
    MissingQuestionLabelRule,
)
from .references import GroupMembershipRule, ImageReferenceRule


def default_rules() -> list[ValidationRule]:
    """Fresh instances of every built-in rule (rules may not be shared
    between runs — the engine's RunState is per-run, but keep instances
    per-run too so stateful rules stay possible)."""
    return [
        MissingQuestionLabelRule(),
        DuplicateQuestionIdRule(),
        EmptyStemRule(),
        InteractionTypeRule(),
        ChoiceAnswerRule(),
        OrderingAnswerRule(),
        MatchingAnswerRule(),
        DragAndDropAnswerRule(),
        FillInBlankAnswerRule(),
        ImageReferenceRule(),
        GroupMembershipRule(),
    ]


__all__ = [
    "ChoiceAnswerRule",
    "DragAndDropAnswerRule",
    "DuplicateQuestionIdRule",
    "EmptyStemRule",
    "FillInBlankAnswerRule",
    "GroupMembershipRule",
    "ImageReferenceRule",
    "InteractionTypeRule",
    "MatchingAnswerRule",
    "MissingQuestionLabelRule",
    "OrderingAnswerRule",
    "default_rules",
]
