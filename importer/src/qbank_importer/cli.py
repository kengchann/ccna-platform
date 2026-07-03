"""Administrator CLI for the import engine.

    qbank-import pdf bank.pdf --out bundles/bank-v1
    qbank-import preview bundles/bank-v1
    qbank-import schema --out schemas/
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from . import __version__
from .errors import ImporterError
from .model import (
    Asset,
    BundleManifest,
    ImportReport,
    ImportResult,
    Question,
    QuestionGroup,
    QuestionStatus,
)
from .pipeline import ImportPreview, preview_from_bundle, run_import
from .sources import open_source

app = typer.Typer(
    name="qbank-import",
    help="Question Bank Import Engine",
    no_args_is_help=True,
)


def _print_result(result: ImportResult) -> None:
    typer.echo(
        f"questions imported: {result.questions_imported} "
        f"(needs review: {result.questions_needing_review})  "
        f"skipped: {result.questions_skipped}"
    )
    typer.echo(
        f"groups: {result.groups_imported}  images: {result.images_imported}  "
        f"warnings: {result.warnings}  errors: {result.errors}  "
        f"elapsed: {result.elapsed_seconds:.2f}s"
    )


@app.command()
def pdf(
    source_file: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", "-o", help="Bundle output directory (must be empty)"),
) -> None:
    """Import a question-bank PDF into a staged bundle."""
    try:
        source = open_source(source_file, format_name="pdf")
        outcome = run_import(source, out)
    except ImporterError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(f"bundle written to {out}")
    _print_result(outcome.result)
    if outcome.result.questions_skipped:
        raise typer.Exit(code=2)


@app.command(name="json")
def json_(
    source_file: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    out: Path = typer.Option(..., "--out", "-o", help="Bundle output directory (must be empty)"),
) -> None:
    """Import a hand-authored JSON question bank into a staged bundle."""
    try:
        source = open_source(source_file, format_name="json")
        outcome = run_import(source, out)
    except ImporterError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    typer.echo(f"bundle written to {out}")
    _print_result(outcome.result)
    if outcome.result.questions_skipped:
        raise typer.Exit(code=2)


@app.command()
def preview(
    bundle_dir: Path = typer.Argument(..., exists=True, file_okay=False),
    json_out: Path = typer.Option(
        None, "--json", help="Also write the full ImportPreview as JSON to this file"
    ),
) -> None:
    """Show the admin review view of a staged bundle."""
    try:
        data: ImportPreview = preview_from_bundle(bundle_dir)
    except ImporterError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    for group in data.groups:
        typer.echo(f"[group {group.group_id}] {group.kind.value}: {group.title or '(untitled)'}")
    for q in data.questions:
        marker = "!" if q.status is QuestionStatus.NEEDS_REVIEW else " "
        typer.echo(
            f"{marker} #{q.ordinal:<5} {q.source_label or q.question_id:<14} "
            f"{q.type.value:<16} images: {len(q.images)}  warnings: {len(q.warnings)}"
        )
        for issue in q.warnings:
            typer.echo(f"        - [{issue.severity.value}] {issue.code}: {issue.message}")
    for failed in data.failed:
        typer.secho(f"x #{failed.ordinal:<5} FAILED", fg=typer.colors.RED)
        for issue in failed.issues:
            typer.echo(f"        - [{issue.severity.value}] {issue.code}: {issue.message}")
    for issue in data.run_issues:
        typer.echo(f"run: [{issue.severity.value}] {issue.code}: {issue.message}")

    if json_out is not None:
        json_out.write_text(data.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"preview JSON written to {json_out}")


@app.command()
def schema(
    out: Path = typer.Option(..., "--out", "-o", help="Directory to write JSON Schema files"),
) -> None:
    """Export JSON Schemas of the bundle models (for the TypeScript side)."""
    out.mkdir(parents=True, exist_ok=True)
    models = {
        "question": Question,
        "question-group": QuestionGroup,
        "asset": Asset,
        "manifest": BundleManifest,
        "report": ImportReport,
        "preview": ImportPreview,
    }
    for name, model in models.items():
        path = out / f"{name}.schema.json"
        path.write_text(
            json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8"
        )
        typer.echo(f"wrote {path}")


@app.command()
def version() -> None:
    """Print the importer version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
