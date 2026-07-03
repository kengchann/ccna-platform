"""Validation rule contract and shared run state.

Design constraints:

- **Rules are independent.** Each rule checks one concern, knows nothing
  about other rules, and can be added/removed without touching the engine.
- **Flag, don't fix.** Rules only *observe*: they yield Issues and never
  mutate what they check. Anything they flag is still imported, marked
  ``needs_review``.
- **Streaming-safe.** Rules see one question/group at a time. Cross-item
  concerns (duplicate ids, group membership) read the :class:`RunState`
  the engine maintains, and may do a final pass in ``finish()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Iterator

from ..model import Asset, Issue, PageRegion, Question, QuestionGroup, Severity


@dataclass
class RunState:
    """What the engine has seen so far in this import run. Rules read it;
    only the engine writes it."""

    #: Asset metadata persisted so far, by asset id.
    assets: dict[str, Asset] = field(default_factory=dict)
    #: Question id -> source ordinal of its first occurrence.
    seen_question_ids: dict[str, int] = field(default_factory=dict)
    #: Group id -> declared member question ids, in declaration order.
    group_members: dict[str, list[str]] = field(default_factory=dict)

    def record_assets(self, assets: Iterable[Asset]) -> None:
        for asset in assets:
            self.assets[asset.id] = asset

    def record_group(self, group: QuestionGroup) -> None:
        self.group_members[group.id] = list(group.question_ids)

    def record_question(self, question: Question) -> None:
        self.seen_question_ids.setdefault(question.id, question.source.ordinal)


class ValidationRule:
    """One independent check. Subclass and override any subset of hooks.

    ``code`` is the stable machine-readable identifier used in the Issues the
    rule emits (the admin UI groups and filters by it).
    """

    code: str = ""

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        return iter(())

    def check_group(self, group: QuestionGroup, state: RunState) -> Iterator[Issue]:
        return iter(())

    def finish(self, state: RunState) -> Iterator[Issue]:
        """Called once after the last item; for whole-run checks."""
        return iter(())

    def issue(
        self,
        message: str,
        *,
        severity: Severity = Severity.WARNING,
        code: str | None = None,
        origin: PageRegion | None = None,
    ) -> Issue:
        return Issue(
            severity=severity, code=code or self.code, message=message, origin=origin
        )
