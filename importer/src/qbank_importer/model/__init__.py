"""Canonical model for imported question banks.

Everything serialized into an import bundle is defined in this package.
JSON Schemas for the TypeScript side can be exported via
``qbank-import schema``.
"""

from .content import (
    Asset,
    AssetKind,
    ContentBlock,
    ImageBlock,
    PageRegion,
    TableBlock,
    TextBlock,
    VerbatimBlock,
)
from .manifest import BUNDLE_FORMAT_VERSION, BundleManifest, SourceInfo
from .question import (
    Blank,
    ChoiceInteraction,
    DragAndDropInteraction,
    FillInBlankInteraction,
    GroupKind,
    Interaction,
    Item,
    MatchingInteraction,
    MatchPair,
    OrderingInteraction,
    Placement,
    Question,
    QuestionGroup,
    QuestionType,
    SourceRef,
)
from .report import ImportReport, ImportResult, Issue, QuestionResult, QuestionStatus, Severity

__all__ = [
    "Asset",
    "AssetKind",
    "Blank",
    "BUNDLE_FORMAT_VERSION",
    "BundleManifest",
    "ChoiceInteraction",
    "ContentBlock",
    "DragAndDropInteraction",
    "FillInBlankInteraction",
    "GroupKind",
    "ImageBlock",
    "ImportReport",
    "ImportResult",
    "Interaction",
    "Issue",
    "Item",
    "MatchingInteraction",
    "MatchPair",
    "OrderingInteraction",
    "PageRegion",
    "Placement",
    "Question",
    "QuestionGroup",
    "QuestionResult",
    "QuestionStatus",
    "QuestionType",
    "Severity",
    "SourceInfo",
    "SourceRef",
    "TableBlock",
    "TextBlock",
    "VerbatimBlock",
]
