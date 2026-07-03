"""Validation engine: runs every registered rule over the item stream.

The engine owns the :class:`RunState` and is the only writer to it, so rules
stay stateless and order-independent. State is recorded *after* a question's
rules run — a duplicate-id rule therefore compares against strictly earlier
questions.
"""

from __future__ import annotations

from ..model import Asset, Issue, Question, QuestionGroup
from .base import RunState, ValidationRule


class Validator:
    def __init__(self, rules: list[ValidationRule]) -> None:
        self._rules = rules
        self._state = RunState()

    def register_assets(self, assets: list[Asset]) -> None:
        """Tell the validator which assets have been persisted (image
        references are checked against these)."""
        self._state.record_assets(assets)

    def check_group(self, group: QuestionGroup) -> list[Issue]:
        issues = [i for rule in self._rules for i in rule.check_group(group, self._state)]
        self._state.record_group(group)
        return issues

    def check_question(self, question: Question) -> list[Issue]:
        issues = [i for rule in self._rules for i in rule.check_question(question, self._state)]
        self._state.record_question(question)
        return issues

    def finish(self) -> list[Issue]:
        """Run whole-run checks; call once after the last item."""
        return [i for rule in self._rules for i in rule.finish(self._state)]
