"""Map an authoring JSON document onto the canonical model.

Groups are emitted before their member questions (the source contract).
Shape problems in a single question become a FailedQuestion; the rest of the
document still imports.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any, Iterator

from ...model import (
    Asset,
    AssetKind,
    Blank,
    ChoiceInteraction,
    ContentBlock,
    DragAndDropInteraction,
    FillInBlankInteraction,
    GroupKind,
    ImageBlock,
    Interaction,
    Issue,
    Item,
    MatchingInteraction,
    MatchPair,
    OrderingInteraction,
    PageRegion,
    Placement,
    Question,
    QuestionGroup,
    QuestionType,
    Severity,
    SourceRef,
    TableBlock,
    TextBlock,
    VerbatimBlock,
)
from ..base import AssetPayload, ExtractedGroup, ExtractedItem, ExtractedQuestion, FailedQuestion


class AuthoringError(ValueError):
    """A question/group cannot be built from its JSON (shape mistake)."""


class JsonDocumentReader:
    def __init__(self, document: Any, base_dir: Path) -> None:
        self._doc = document
        self._base = base_dir
        self._ordinal = 0
        self._asset_seq = 0

    def items(self) -> Iterator[ExtractedItem]:
        if not isinstance(self._doc, dict):
            raise AuthoringError("top-level JSON must be an object")

        # label -> group_id, so questions can be matched to their group.
        groups = self._doc.get("groups", []) or []
        member_to_group: dict[str, str] = {}
        group_defs: dict[str, dict] = {}
        for index, raw in enumerate(groups, start=1):
            gid = str(raw.get("id") or f"g{index}")
            group_defs[gid] = raw
            for member in raw.get("questions", []) or []:
                member_to_group[str(member)] = gid

        emitted_groups: set[str] = set()
        questions = self._doc.get("questions", []) or []
        for raw in questions:
            self._ordinal += 1
            label = str(raw.get("label") or self._ordinal)
            group_id = member_to_group.get(label)

            if group_id and group_id not in emitted_groups:
                yield self._group(group_defs[group_id], group_id)
                emitted_groups.add(group_id)

            try:
                yield self._question(raw, label, group_id)
            except AuthoringError as exc:
                yield FailedQuestion(
                    ordinal=self._ordinal,
                    issues=[
                        Issue(
                            severity=Severity.ERROR,
                            code="authoring_error",
                            message=f"question {label!r}: {exc}",
                        )
                    ],
                )

    # -- questions ---------------------------------------------------------

    def _question(self, raw: dict, label: str, group_id: str | None) -> ExtractedQuestion:
        try:
            qtype = QuestionType(raw["type"])
        except (KeyError, ValueError):
            raise AuthoringError(f"missing or unknown type {raw.get('type')!r}")

        assets: list[AssetPayload] = []
        stem = self._blocks(raw.get("stem", []), assets, f"q{self._ordinal}")
        explanation = self._blocks(raw.get("explanation", []), assets, f"q{self._ordinal}")
        interaction = self._interaction(qtype, raw, assets)

        question = Question(
            id=f"q{self._ordinal}",
            source=SourceRef(ordinal=self._ordinal, label=label, pages=[]),
            type=qtype,
            group_id=group_id,
            stem=stem,
            interaction=interaction,
            explanation=explanation,
        )
        return ExtractedQuestion(question=question, assets=assets)

    def _interaction(self, qtype: QuestionType, raw: dict, assets: list[AssetPayload]) -> Interaction:
        if qtype in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE):
            return self._choice(raw, assets)
        if qtype == QuestionType.ORDERING:
            return self._ordering(raw, assets)
        if qtype == QuestionType.MATCHING:
            return self._matching(raw, assets)
        if qtype == QuestionType.DRAG_AND_DROP:
            return self._drag_and_drop(raw, assets)
        if qtype == QuestionType.FILL_IN_BLANK:
            return self._fill_in_blank(raw)
        # Scenario/case-study questions carry whichever interaction they list.
        return self._choice(raw, assets)

    def _items(self, raw_items: Any, assets: list[AssetPayload], prefix: str) -> list[Item]:
        if not isinstance(raw_items, list):
            raise AuthoringError(f"{prefix} must be a list")
        items: list[Item] = []
        for index, entry in enumerate(raw_items, start=1):
            item_id = str(entry.get("id") or f"{prefix}{index}")
            content = self._item_content(entry, assets, f"{self._ownerid()}-{item_id}")
            items.append(Item(id=item_id, label=entry.get("label"), content=content))
        return items

    def _item_content(self, entry: dict, assets: list[AssetPayload], owner: str) -> list[ContentBlock]:
        if "content" in entry:
            return self._blocks(entry["content"], assets, owner)
        if "text" in entry:
            return [TextBlock(text=entry["text"])]
        raise AuthoringError(f"item {entry.get('id')!r} has no text/content")

    def _choice(self, raw: dict, assets: list[AssetPayload]) -> ChoiceInteraction:
        options = raw.get("options")
        if not isinstance(options, list) or not options:
            raise AuthoringError("choice question needs a non-empty 'options' list")
        items: list[Item] = []
        correct: list[str] = []
        for index, entry in enumerate(options, start=1):
            item_id = str(entry.get("id") or chr(ord("a") + index - 1))
            content = self._item_content(entry, assets, f"{self._ownerid()}-{item_id}")
            items.append(Item(id=item_id, label=entry.get("label"), content=content))
            if entry.get("correct"):
                correct.append(item_id)
        return ChoiceInteraction(options=items, correct_option_ids=correct)

    def _ordering(self, raw: dict, assets: list[AssetPayload]) -> OrderingInteraction:
        items = self._items(raw.get("items"), assets, "item")
        order = [str(x) for x in raw.get("correct_order", [])] or [i.id for i in items]
        return OrderingInteraction(items=items, correct_order=order)

    def _matching(self, raw: dict, assets: list[AssetPayload]) -> MatchingInteraction:
        left = self._items(raw.get("left"), assets, "l")
        right = self._items(raw.get("right"), assets, "r")
        pairs = [
            MatchPair(left_id=str(p["left"]), right_id=str(p["right"]))
            for p in raw.get("pairs", [])
            if "left" in p and "right" in p
        ]
        return MatchingInteraction(left=left, right=right, pairs=pairs)

    def _drag_and_drop(self, raw: dict, assets: list[AssetPayload]) -> DragAndDropInteraction:
        tokens = self._items(raw.get("tokens"), assets, "t")
        targets = self._items(raw.get("targets"), assets, "z")
        placements = [
            Placement(token_id=str(p["token"]), target_id=str(p["target"]))
            for p in raw.get("placements", [])
            if "token" in p and "target" in p
        ]
        return DragAndDropInteraction(tokens=tokens, targets=targets, placements=placements)

    def _fill_in_blank(self, raw: dict) -> FillInBlankInteraction:
        blanks_raw = raw.get("blanks")
        if not isinstance(blanks_raw, list) or not blanks_raw:
            raise AuthoringError("fill_in_blank question needs a non-empty 'blanks' list")
        blanks = [
            Blank(
                id=str(b.get("id") or f"b{index}"),
                accepted=[str(a) for a in (b.get("accepted") or [])],
            )
            for index, b in enumerate(blanks_raw, start=1)
        ]
        return FillInBlankInteraction(blanks=blanks)

    # -- groups ------------------------------------------------------------

    def _group(self, raw: dict, group_id: str) -> ExtractedGroup:
        try:
            kind = GroupKind(raw.get("kind", "scenario"))
        except ValueError:
            kind = GroupKind.SCENARIO
        assets: list[AssetPayload] = []
        context = self._blocks(raw.get("context", []), assets, group_id)
        group = QuestionGroup(
            id=group_id,
            kind=kind,
            title=raw.get("title"),
            context=context,
            question_ids=[
                f"q{i + 1}"
                for i, q in enumerate(self._doc.get("questions", []))
                if str(q.get("label") or (i + 1)) in {str(m) for m in raw.get("questions", [])}
            ],
        )
        return ExtractedGroup(group=group, assets=assets)

    # -- content blocks ----------------------------------------------------

    def _blocks(self, raw_blocks: Any, assets: list[AssetPayload], owner: str) -> list[ContentBlock]:
        if raw_blocks is None:
            return []
        if isinstance(raw_blocks, str):
            raw_blocks = [{"text": raw_blocks}]
        if not isinstance(raw_blocks, list):
            raise AuthoringError(f"content for {owner} must be a string or list")
        blocks: list[ContentBlock] = []
        for entry in raw_blocks:
            blocks.append(self._block(entry, assets, owner))
        return blocks

    def _block(self, entry: Any, assets: list[AssetPayload], owner: str) -> ContentBlock:
        if isinstance(entry, str):
            return TextBlock(text=entry)
        if not isinstance(entry, dict):
            raise AuthoringError(f"content block for {owner} must be a string or object")
        if "text" in entry:
            return TextBlock(text=str(entry["text"]))
        if "cli" in entry:
            return VerbatimBlock(text=str(entry["cli"]), language_hint=entry.get("language"))
        if "verbatim" in entry:
            return VerbatimBlock(text=str(entry["verbatim"]), language_hint=entry.get("language"))
        if "table" in entry:
            rows = [[str(c) for c in row] for row in entry["table"]]
            return TableBlock(rows=rows)
        if "image" in entry:
            return self._image_block(str(entry["image"]), entry.get("caption"), assets)
        raise AuthoringError(f"unrecognized content block for {owner}: {sorted(entry)}")

    def _image_block(self, rel_path: str, caption: str | None, assets: list[AssetPayload]) -> ImageBlock:
        path = (self._base / rel_path).resolve()
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise AuthoringError(f"cannot read image {rel_path!r}: {exc}")
        self._asset_seq += 1
        asset_id = f"a{self._asset_seq}"
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        assets.append(
            AssetPayload(
                asset=Asset(
                    id=asset_id,
                    kind=AssetKind.EMBEDDED,
                    media_type=media_type,
                    filename="",
                    origin=PageRegion(page=1),
                    sha256="",
                ),
                data=data,
            )
        )
        return ImageBlock(asset_id=asset_id, caption=caption)

    def _ownerid(self) -> str:
        return f"q{self._ordinal}"
