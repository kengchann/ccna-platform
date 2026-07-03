"""Normalizer stage: structural normalization of parser output.

Scope is deliberately narrow. Ids (question/group/asset) are importer
bookkeeping, not source content, so the normalizer may repair them; the
*content* — text, blocks, options, answer keys — is never touched, per the
fidelity rules. Concretely it guarantees:

1. Every question, group, and asset has a non-empty id.
2. Ids are unique across the whole run (duplicates from a parser are
   remapped deterministically and flagged).
3. When an asset id is remapped, the ImageBlocks *within the same item* that
   referenced it are updated, so no reference is orphaned by normalization
   itself. (Dangling references that came from the parser are left alone —
   the ImageReferenceRule flags those.)

Everything else that looks "wrong" is a job for the Validator: the
normalizer must never guess at meaning.
"""

from __future__ import annotations

from dataclasses import replace

from ..model import (
    ChoiceInteraction,
    ContentBlock,
    DragAndDropInteraction,
    ImageBlock,
    Interaction,
    Issue,
    Item,
    MatchingInteraction,
    OrderingInteraction,
    Severity,
)
from ..sources import ExtractedGroup, ExtractedItem, ExtractedQuestion, FailedQuestion


def _remap_blocks(blocks: list[ContentBlock], remap: dict[str, str]) -> list[ContentBlock]:
    return [
        b.model_copy(update={"asset_id": remap[b.asset_id]})
        if isinstance(b, ImageBlock) and b.asset_id in remap
        else b
        for b in blocks
    ]


def _remap_items(items: list[Item], remap: dict[str, str]) -> list[Item]:
    return [i.model_copy(update={"content": _remap_blocks(i.content, remap)}) for i in items]


def _remap_interaction(interaction: Interaction, remap: dict[str, str]) -> Interaction:
    if isinstance(interaction, ChoiceInteraction):
        return interaction.model_copy(update={"options": _remap_items(interaction.options, remap)})
    if isinstance(interaction, OrderingInteraction):
        return interaction.model_copy(update={"items": _remap_items(interaction.items, remap)})
    if isinstance(interaction, MatchingInteraction):
        return interaction.model_copy(
            update={
                "left": _remap_items(interaction.left, remap),
                "right": _remap_items(interaction.right, remap),
            }
        )
    if isinstance(interaction, DragAndDropInteraction):
        return interaction.model_copy(
            update={
                "tokens": _remap_items(interaction.tokens, remap),
                "targets": _remap_items(interaction.targets, remap),
            }
        )
    return interaction  # fill-in-blank has no item content


class Normalizer:
    """One instance per import run; tracks ids across the whole stream."""

    def __init__(self) -> None:
        self._question_ids: set[str] = set()
        self._group_ids: set[str] = set()
        self._asset_ids: set[str] = set()
        self._group_counter = 0

    def apply(self, item: ExtractedItem) -> ExtractedItem:
        """Return the normalized item; normalization notes are appended to
        the item's issues so they land in the import report."""
        match item:
            case ExtractedQuestion():
                return self._question(item)
            case ExtractedGroup():
                return self._group(item)
            case FailedQuestion():
                return item
        raise TypeError(f"unexpected extracted item: {type(item).__name__}")

    def _question(self, item: ExtractedQuestion) -> ExtractedQuestion:
        issues: list[Issue] = []
        question = item.question

        qid, id_issues = self._unique_id(
            question.id, self._question_ids, fallback=f"q{question.source.ordinal}", what="question"
        )
        issues += id_issues
        self._question_ids.add(qid)

        payloads, remap, asset_issues = self._normalize_assets(item.assets, owner=qid)
        issues += asset_issues

        updates: dict = {}
        if qid != question.id:
            updates["id"] = qid
        if remap:
            updates["stem"] = _remap_blocks(question.stem, remap)
            updates["explanation"] = _remap_blocks(question.explanation, remap)
            updates["interaction"] = _remap_interaction(question.interaction, remap)
        if updates:
            question = question.model_copy(update=updates)

        return replace(item, question=question, assets=payloads, issues=item.issues + issues)

    def _group(self, item: ExtractedGroup) -> ExtractedGroup:
        issues: list[Issue] = []
        group = item.group

        self._group_counter += 1
        gid, id_issues = self._unique_id(
            group.id, self._group_ids, fallback=f"g{self._group_counter}", what="group"
        )
        issues += id_issues
        self._group_ids.add(gid)

        payloads, remap, asset_issues = self._normalize_assets(item.assets, owner=gid)
        issues += asset_issues

        updates: dict = {}
        if gid != group.id:
            updates["id"] = gid
        if remap:
            updates["context"] = _remap_blocks(group.context, remap)
        if updates:
            group = group.model_copy(update=updates)

        return replace(item, group=group, assets=payloads, issues=item.issues + issues)

    def _normalize_assets(self, payloads, owner: str):
        """Ensure asset ids are present and globally unique; returns the new
        payload list, the old->new id remap, and any issues."""
        issues: list[Issue] = []
        remap: dict[str, str] = {}
        normalized = []
        for index, payload in enumerate(payloads, start=1):
            asset = payload.asset
            aid, id_issues = self._unique_id(
                asset.id, self._asset_ids, fallback=f"{owner}-img{index}", what="asset"
            )
            issues += id_issues
            self._asset_ids.add(aid)
            if aid != asset.id:
                if asset.id:  # only a real old id can have been referenced
                    remap[asset.id] = aid
                asset = asset.model_copy(update={"id": aid})
                payload = replace(payload, asset=asset)
            normalized.append(payload)
        return normalized, remap, issues

    def _unique_id(
        self, raw: str, taken: set[str], *, fallback: str, what: str
    ) -> tuple[str, list[Issue]]:
        candidate = raw.strip()
        issues: list[Issue] = []
        if not candidate:
            candidate = fallback
            issues.append(
                Issue(
                    severity=Severity.INFO,
                    code="assigned_id",
                    message=f"parser emitted no {what} id; assigned {candidate!r}",
                )
            )
        if candidate in taken:
            base, n = candidate, 2
            while candidate in taken:
                candidate = f"{base}-dup{n}"
                n += 1
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    code=f"duplicate_{what}_id_remapped",
                    message=(
                        f"{what} id {base!r} was already used; remapped to {candidate!r} "
                        "(possible mis-segmentation in the parser)"
                    ),
                )
            )
        return candidate, issues
