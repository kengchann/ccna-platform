"""Pipeline runner: Input → Parser → Normalizer → Validator → Preview → Import.

- **Input**: resolve and identify the source document (``source.describe()``;
  format selection happens in :func:`qbank_importer.sources.open_source`).
- **Parser**: ``source.extract()`` — the only format-specific stage.
- **Normalizer**: structural id normalization (:class:`Normalizer`).
- **Validator**: independent rules over the stream (:class:`Validator`).
- **Preview**: admin-facing view of what was staged (:class:`PreviewBuilder`).
- **Import**: persistence into the staged bundle (:class:`BundleWriter`);
  loading a bundle into the platform database is the web app's job and
  consumes the bundle this stage produces.

The whole pipeline is streaming: one extracted item (with its asset bytes)
is in flight at a time. Only bounded metadata — ids, asset records, previews,
per-question results — accumulates over a run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..bundle import BundleWriter
from ..model import (
    Asset,
    BundleManifest,
    ImportReport,
    ImportResult,
    Issue,
    QuestionResult,
    QuestionStatus,
    Severity,
)
from ..sources import (
    AssetPayload,
    ExtractedGroup,
    ExtractedQuestion,
    FailedQuestion,
    ImportSource,
)
from ..validation import ValidationRule, Validator, default_rules
from .normalize import Normalizer
from .preview import ImportPreview, PreviewBuilder


@dataclass(frozen=True)
class ImportOutcome:
    """Everything one pipeline run produces."""

    manifest: BundleManifest
    report: ImportReport      # full audit trail (also persisted in the bundle)
    result: ImportResult      # headline summary
    preview: ImportPreview    # admin review view


def _status_for(issues: list[Issue]) -> QuestionStatus:
    if any(i.severity in (Severity.WARNING, Severity.ERROR) for i in issues):
        return QuestionStatus.NEEDS_REVIEW
    return QuestionStatus.IMPORTED


def run_import(
    source: ImportSource,
    out_dir: Path,
    *,
    rules: list[ValidationRule] | None = None,
) -> ImportOutcome:
    """Run the full pipeline for ``source``, staging a bundle at ``out_dir``."""
    started_at = datetime.now(timezone.utc)
    source_info = source.describe()

    normalizer = Normalizer()
    validator = Validator(default_rules() if rules is None else rules)
    stored_assets: dict[str, Asset] = {}
    preview_builder = PreviewBuilder(stored_assets)
    results: list[QuestionResult] = []
    run_issues: list[Issue] = []

    def persist_assets(writer: BundleWriter, payloads: list[AssetPayload]) -> None:
        stored = [writer.add_asset(p.asset, p.data) for p in payloads]
        for asset in stored:
            stored_assets[asset.id] = asset
        validator.register_assets(stored)

    with BundleWriter(out_dir, source_info) as writer:
        for raw in source.extract():
            item = normalizer.apply(raw)
            match item:
                case ExtractedGroup(group=group, assets=payloads, issues=issues):
                    persist_assets(writer, payloads)
                    all_issues = issues + validator.check_group(group)
                    writer.add_group(group)
                    preview_builder.add_group(group)
                    run_issues.extend(all_issues)

                case ExtractedQuestion(question=question, assets=payloads, issues=issues):
                    persist_assets(writer, payloads)
                    all_issues = issues + validator.check_question(question)
                    status = _status_for(all_issues)
                    writer.add_question(question)
                    preview_builder.add_question(question, all_issues, status)
                    results.append(
                        QuestionResult(
                            ordinal=question.source.ordinal,
                            question_id=question.id,
                            status=status,
                            issues=all_issues,
                        )
                    )

                case FailedQuestion(ordinal=ordinal, issues=issues):
                    preview_builder.add_failed(ordinal, issues)
                    results.append(
                        QuestionResult(
                            ordinal=ordinal,
                            question_id=None,
                            status=QuestionStatus.FAILED,
                            issues=issues,
                        )
                    )

        run_issues.extend(validator.finish())

        report = ImportReport(
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            source_filename=source_info.filename,
            results=results,
            run_issues=run_issues,
        )
        manifest = writer.finalize(report)

    return ImportOutcome(
        manifest=manifest,
        report=report,
        result=ImportResult.from_run(report, manifest.group_count, manifest.asset_count),
        preview=preview_builder.build(source_info, run_issues),
    )
