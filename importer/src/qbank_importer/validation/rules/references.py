"""Rules for cross-references: image assets and group membership."""

from __future__ import annotations

from typing import Iterable, Iterator

from ...model import ContentBlock, ImageBlock, Issue, Question, QuestionGroup
from ...model.traverse import iter_blocks
from ..base import RunState, ValidationRule


class ImageReferenceRule(ValidationRule):
    """Every ImageBlock must point at an asset that was actually extracted —
    a dangling reference means an original figure was lost."""

    code = "missing_asset"

    def _check_blocks(
        self, blocks: Iterable[tuple[str, ContentBlock]], state: RunState
    ) -> Iterator[Issue]:
        for where, block in blocks:
            if isinstance(block, ImageBlock) and block.asset_id not in state.assets:
                yield self.issue(
                    f"{where} references asset {block.asset_id!r} which was not extracted"
                )

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        yield from self._check_blocks(iter_blocks(question), state)

    def check_group(self, group: QuestionGroup, state: RunState) -> Iterator[Issue]:
        yield from self._check_blocks((("group context", b) for b in group.context), state)


class GroupMembershipRule(ValidationRule):
    """Group declarations and question back-references must agree. Sources
    emit groups before their members, so both directions are checkable:
    per-question here, never-seen members in ``finish``."""

    code = "group_member_mismatch"

    def check_question(self, question: Question, state: RunState) -> Iterator[Issue]:
        if question.group_id is None:
            return
        members = state.group_members.get(question.group_id)
        if members is None:
            yield self.issue(
                f"question references unknown group {question.group_id!r}",
                code="unknown_group",
            )
        elif question.id not in members:
            yield self.issue(
                f"question {question.id!r} claims group {question.group_id!r} "
                "but the group does not list it as a member"
            )

    def finish(self, state: RunState) -> Iterator[Issue]:
        for group_id, members in state.group_members.items():
            for member in members:
                if member not in state.seen_question_ids:
                    yield self.issue(
                        f"group {group_id!r} lists member {member!r} "
                        "but no such question was imported",
                        code="missing_group_member",
                    )
