"""Read-only traversal helpers over the canonical model, shared by the
validation rules and the preview builder."""

from __future__ import annotations

from typing import Iterator

from .content import ContentBlock
from .question import (
    ChoiceInteraction,
    DragAndDropInteraction,
    Item,
    MatchingInteraction,
    OrderingInteraction,
    Question,
)


def interaction_items(question: Question) -> list[Item]:
    """All Items of a question's interaction, in display order."""
    inter = question.interaction
    if isinstance(inter, ChoiceInteraction):
        return inter.options
    if isinstance(inter, OrderingInteraction):
        return inter.items
    if isinstance(inter, MatchingInteraction):
        return inter.left + inter.right
    if isinstance(inter, DragAndDropInteraction):
        return inter.tokens + inter.targets
    return []  # fill-in-blank has no item content


def iter_blocks(question: Question) -> Iterator[tuple[str, ContentBlock]]:
    """Every content block of a question with a human-readable location,
    in display order: stem, interaction items, explanation."""
    for block in question.stem:
        yield "stem", block
    for item in interaction_items(question):
        for block in item.content:
            yield f"item {item.id!r}", block
    for block in question.explanation:
        yield "explanation", block
