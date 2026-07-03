"""Preview stage: what an administrator reviews before accepting an import.

These are data structures only (no UI). A preview can be built two ways:

- incrementally during a pipeline run (:class:`PreviewBuilder`), or
- from a finished bundle on disk (:func:`preview_from_bundle`), so the
  admin UI can re-open a staged import later.

Previews carry the question's real content blocks (fidelity applies to
previews too); ``plain_text`` fields are an additional *display projection*
for list views and never replace the blocks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field

from ..bundle import BundleReader
from ..model import (
    Asset,
    ChoiceInteraction,
    ContentBlock,
    GroupKind,
    ImageBlock,
    Issue,
    Question,
    QuestionGroup,
    QuestionStatus,
    QuestionType,
    SourceInfo,
)
from ..model.content import _StrictModel
from ..model.traverse import iter_blocks


def blocks_to_plain_text(blocks: list[ContentBlock]) -> str:
    """Flatten blocks to a single display string. Text and verbatim content
    pass through exactly; images and tables become markers. Display-only."""
    parts: list[str] = []
    for block in blocks:
        if block.kind in ("text", "verbatim"):
            parts.append(block.text)
        elif block.kind == "image":
            parts.append(f"[image {block.asset_id}]")
        else:  # table
            parts.append("\n".join("\t".join(row) for row in block.rows))
    return "\n".join(parts)


class ChoicePreview(_StrictModel):
    id: str
    label: str | None
    text: str = Field(description="Display projection of the option's content blocks")
    is_correct: bool


class ImagePreview(_StrictModel):
    asset_id: str
    filename: str | None = Field(description="Null when the referenced asset is missing")
    location: str = Field(description='Where the image appears, e.g. "stem"')


class QuestionPreview(_StrictModel):
    question_id: str
    ordinal: int
    source_label: str | None
    type: QuestionType
    group_id: str | None
    stem: list[ContentBlock]
    stem_text: str = Field(description="Display projection of the stem blocks")
    choices: list[ChoicePreview] = Field(
        default_factory=list, description="Populated for choice interactions only"
    )
    images: list[ImagePreview]
    warnings: list[Issue]
    status: QuestionStatus


class FailedPreview(_StrictModel):
    """A source position that produced no question at all."""

    ordinal: int
    issues: list[Issue]


class GroupPreview(_StrictModel):
    group_id: str
    kind: GroupKind
    title: str | None
    context_text: str
    question_ids: list[str]


class ImportPreview(_StrictModel):
    source: SourceInfo
    generated_at: datetime
    questions: list[QuestionPreview]
    failed: list[FailedPreview]
    groups: list[GroupPreview]
    run_issues: list[Issue]


def _question_preview(
    question: Question,
    issues: list[Issue],
    status: QuestionStatus,
    assets: dict[str, Asset],
) -> QuestionPreview:
    images = [
        ImagePreview(
            asset_id=block.asset_id,
            filename=assets[block.asset_id].filename if block.asset_id in assets else None,
            location=where,
        )
        for where, block in iter_blocks(question)
        if isinstance(block, ImageBlock)
    ]
    choices: list[ChoicePreview] = []
    if isinstance(question.interaction, ChoiceInteraction):
        correct = set(question.interaction.correct_option_ids)
        choices = [
            ChoicePreview(
                id=opt.id,
                label=opt.label,
                text=blocks_to_plain_text(opt.content),
                is_correct=opt.id in correct,
            )
            for opt in question.interaction.options
        ]
    return QuestionPreview(
        question_id=question.id,
        ordinal=question.source.ordinal,
        source_label=question.source.label,
        type=question.type,
        group_id=question.group_id,
        stem=question.stem,
        stem_text=blocks_to_plain_text(question.stem),
        choices=choices,
        images=images,
        warnings=issues,
        status=status,
    )


class PreviewBuilder:
    """Accumulates previews as the pipeline streams; one instance per run."""

    def __init__(self, assets: dict[str, Asset]) -> None:
        self._assets = assets  # shared with the runner, which fills it as assets persist
        self._questions: list[QuestionPreview] = []
        self._failed: list[FailedPreview] = []
        self._groups: list[GroupPreview] = []

    def add_question(self, question: Question, issues: list[Issue], status: QuestionStatus) -> None:
        self._questions.append(_question_preview(question, issues, status, self._assets))

    def add_failed(self, ordinal: int, issues: list[Issue]) -> None:
        self._failed.append(FailedPreview(ordinal=ordinal, issues=issues))

    def add_group(self, group: QuestionGroup) -> None:
        self._groups.append(
            GroupPreview(
                group_id=group.id,
                kind=group.kind,
                title=group.title,
                context_text=blocks_to_plain_text(group.context),
                question_ids=group.question_ids,
            )
        )

    def build(self, source: SourceInfo, run_issues: list[Issue]) -> ImportPreview:
        return ImportPreview(
            source=source,
            generated_at=datetime.now(timezone.utc),
            questions=self._questions,
            failed=self._failed,
            groups=self._groups,
            run_issues=run_issues,
        )


def preview_from_bundle(bundle_dir: Path) -> ImportPreview:
    """Rebuild an ImportPreview from a staged bundle on disk."""
    reader = BundleReader(bundle_dir)
    report = reader.report()
    assets = {a.id: a for a in reader.assets()}
    outcomes = {r.question_id: r for r in report.results if r.question_id is not None}

    builder = PreviewBuilder(assets)
    for group in reader.groups():
        builder.add_group(group)
    for question in reader.questions():
        result = outcomes.get(question.id)
        builder.add_question(
            question,
            issues=result.issues if result else [],
            status=result.status if result else QuestionStatus.IMPORTED,
        )
    for result in report.results:
        if result.question_id is None:
            builder.add_failed(result.ordinal, result.issues)
    return builder.build(reader.manifest.source, report.run_issues)
