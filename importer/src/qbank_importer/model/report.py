"""Import report: the audit trail of an import run.

Every deviation from a clean extraction — an OCR correction, an ambiguous
segmentation, a type/answer mismatch — is recorded here as an ``Issue`` so
administrators can review exactly what the importer did and where human
attention is needed. The report never blocks an import; it describes one.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .content import PageRegion, _StrictModel


class Severity(str, Enum):
    #: Informational, no action needed (e.g. "cropped vector figure on page 12").
    INFO = "info"
    #: The question imported but needs human review.
    WARNING = "warning"
    #: The question could not be imported; its source location is recorded.
    ERROR = "error"


class Issue(_StrictModel):
    severity: Severity
    code: str = Field(
        description=(
            'Stable machine-readable code, e.g. "ocr_correction", '
            '"ambiguous_segmentation", "answer_count_mismatch"'
        )
    )
    message: str = Field(description="Human-readable description for the admin review UI")
    origin: PageRegion | None = Field(
        default=None, description="Source location the issue refers to, when known"
    )


class QuestionStatus(str, Enum):
    IMPORTED = "imported"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class QuestionResult(_StrictModel):
    """Outcome for one question position in the source document."""

    ordinal: int = Field(ge=1)
    question_id: str | None = Field(
        default=None, description="Null only when the question failed to import"
    )
    status: QuestionStatus
    issues: list[Issue] = Field(default_factory=list)


class ImportReport(_StrictModel):
    started_at: datetime
    finished_at: datetime
    source_filename: str
    results: list[QuestionResult]
    run_issues: list[Issue] = Field(
        default_factory=list,
        description="Issues not tied to a single question (document-level anomalies)",
    )

    def count(self, status: QuestionStatus) -> int:
        return sum(1 for r in self.results if r.status is status)

    def issue_count(self, severity: Severity) -> int:
        per_question = sum(
            1 for r in self.results for i in r.issues if i.severity is severity
        )
        return per_question + sum(1 for i in self.run_issues if i.severity is severity)


class ImportResult(_StrictModel):
    """Headline summary of one import run, derived from the detailed
    :class:`ImportReport`. This is what admin tooling shows first; the report
    remains the full audit trail."""

    questions_imported: int = Field(
        ge=0, description="Questions written to the bundle (clean + needs-review)"
    )
    questions_needing_review: int = Field(ge=0)
    questions_skipped: int = Field(
        ge=0, description="Source positions that could not be imported at all"
    )
    groups_imported: int = Field(ge=0)
    images_imported: int = Field(ge=0)
    warnings: int = Field(ge=0, description="Total warning-severity issues")
    errors: int = Field(ge=0, description="Total error-severity issues")
    elapsed_seconds: float = Field(ge=0)

    @classmethod
    def from_run(cls, report: ImportReport, group_count: int, asset_count: int) -> "ImportResult":
        return cls(
            questions_imported=report.count(QuestionStatus.IMPORTED)
            + report.count(QuestionStatus.NEEDS_REVIEW),
            questions_needing_review=report.count(QuestionStatus.NEEDS_REVIEW),
            questions_skipped=report.count(QuestionStatus.FAILED),
            groups_imported=group_count,
            images_imported=asset_count,
            warnings=report.issue_count(Severity.WARNING),
            errors=report.issue_count(Severity.ERROR),
            elapsed_seconds=(report.finished_at - report.started_at).total_seconds(),
        )
