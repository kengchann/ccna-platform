"""The import pipeline: Input → Parser → Normalizer → Validator → Preview → Import.

Public surface:

- :func:`run_import` / :class:`ImportOutcome` — run the pipeline for any
  :class:`~qbank_importer.sources.base.ImportSource`.
- :func:`preview_from_bundle` and the preview models — the admin review view.
"""

from .normalize import Normalizer
from .preview import (
    ChoicePreview,
    FailedPreview,
    GroupPreview,
    ImagePreview,
    ImportPreview,
    PreviewBuilder,
    QuestionPreview,
    blocks_to_plain_text,
    preview_from_bundle,
)
from .runner import ImportOutcome, run_import

__all__ = [
    "ChoicePreview",
    "FailedPreview",
    "GroupPreview",
    "ImagePreview",
    "ImportOutcome",
    "ImportPreview",
    "Normalizer",
    "PreviewBuilder",
    "QuestionPreview",
    "blocks_to_plain_text",
    "preview_from_bundle",
    "run_import",
]
