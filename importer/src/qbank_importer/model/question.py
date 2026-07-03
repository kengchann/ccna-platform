"""Canonical question model.

A ``Question`` pairs source-faithful content (stem, options, explanation —
all made of ContentBlocks) with a typed ``Interaction`` describing the
structure and correct response for its question type.

These models enforce *shape* only (field types, discriminators, required
fields). Referential integrity — answer ids that resolve to options, complete
orderings, valid matching pairs — is deliberately NOT enforced here: a
question whose answer key is broken in the source must still be importable
and flagged for review ("flag, don't fix"). Those checks live in
:mod:`qbank_importer.validation` as independent rules.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import Field

from .content import ContentBlock, _StrictModel


class QuestionType(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    DRAG_AND_DROP = "drag_and_drop"
    MATCHING = "matching"
    ORDERING = "ordering"
    FILL_IN_BLANK = "fill_in_blank"
    SCENARIO = "scenario"
    CASE_STUDY = "case_study"


class SourceRef(_StrictModel):
    """Where the question sits in the source document."""

    ordinal: int = Field(ge=1, description="1-based position within the source document")
    label: str | None = Field(
        default=None,
        description='Question label exactly as printed, e.g. "Question 137" or "137."',
    )
    pages: list[int] = Field(
        default_factory=list,
        description="1-based source pages this question spans, in order",
    )


class Item(_StrictModel):
    """A selectable/movable unit: an answer option, ordering item, matching
    entry, or drag token/target. ``label`` is the printed marker ("A.", "B)")
    when the source has one; ``content`` is the item's content, exact."""

    id: str
    label: str | None = None
    content: list[ContentBlock]


class ChoiceInteraction(_StrictModel):
    """Options with one or more correct answers.

    Covers single choice, multiple choice, and true/false — the question's
    ``type`` distinguishes them; true/false options keep the source's exact
    wording ("True", "False", or whatever was printed).
    """

    kind: Literal["choice"] = "choice"
    options: list[Item]
    correct_option_ids: list[str]


class OrderingInteraction(_StrictModel):
    """Items the learner must arrange; ``correct_order`` lists item ids in
    the correct sequence."""

    kind: Literal["ordering"] = "ordering"
    items: list[Item]
    correct_order: list[str]


class MatchPair(_StrictModel):
    left_id: str
    right_id: str


class MatchingInteraction(_StrictModel):
    """Two columns of items and the correct left→right pairs. A right item
    may be a distractor (unpaired) or match multiple left items, exactly as
    the source defines."""

    kind: Literal["matching"] = "matching"
    left: list[Item]
    right: list[Item]
    pairs: list[MatchPair]


class Placement(_StrictModel):
    token_id: str
    target_id: str


class DragAndDropInteraction(_StrictModel):
    """Draggable tokens, drop targets, and the correct placements. Tokens may
    be unused (distractors) and targets may accept multiple tokens, exactly
    as the source defines."""

    kind: Literal["drag_and_drop"] = "drag_and_drop"
    tokens: list[Item]
    targets: list[Item]
    placements: list[Placement]


class Blank(_StrictModel):
    """One blank in a fill-in-the-blank question. The stem keeps the source's
    original placeholder text (underscores, brackets, ...) exactly as
    printed; blanks are ordered as they appear in the stem."""

    id: str
    accepted: list[str] = Field(
        default_factory=list,
        description="Accepted answers, exact strings from the source",
    )


class FillInBlankInteraction(_StrictModel):
    kind: Literal["fill_in_blank"] = "fill_in_blank"
    blanks: list[Blank]


Interaction = Annotated[
    Union[
        ChoiceInteraction,
        OrderingInteraction,
        MatchingInteraction,
        DragAndDropInteraction,
        FillInBlankInteraction,
    ],
    Field(discriminator="kind"),
]


class Question(_StrictModel):
    """One imported question, faithful to the source document."""

    id: str
    source: SourceRef
    type: QuestionType
    group_id: str | None = Field(
        default=None, description="QuestionGroup this question belongs to, if any"
    )
    stem: list[ContentBlock] = Field(
        description="Question content in source order, including inline exhibits"
    )
    interaction: Interaction
    explanation: list[ContentBlock] = Field(
        default_factory=list,
        description="Explanation/rationale exactly as printed in the source, if present",
    )


class GroupKind(str, Enum):
    SCENARIO = "scenario"
    CASE_STUDY = "case_study"


class QuestionGroup(_StrictModel):
    """Scenario or case-study container: shared context (possibly multi-page,
    with exhibits) plus the ordered member questions."""

    id: str
    kind: GroupKind
    title: str | None = Field(default=None, description="Title exactly as printed, if any")
    context: list[ContentBlock]
    question_ids: list[str] = Field(description="Member question ids in source order")
