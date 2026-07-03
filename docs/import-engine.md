# Question Bank Import Engine — Architecture

## Purpose

Convert source documents containing our original question banks into a
canonical, machine-readable form ("import bundle") that the web platform
ingests. The first supported source format is PDF; the architecture must admit
Word/JSON/CSV/Markdown sources later without redesign.

## Non-negotiable fidelity rules

These rules bind every source implementation:

1. **Never rewrite content.** No paraphrasing, no grammar fixes, no
   simplification. Text is carried through exactly as extracted. The only
   permitted correction is an obvious OCR/recognition artifact, and any such
   correction must be recorded as an `Issue` on the question so an admin can
   audit it.
2. **Verbatim blocks are sacred.** Cisco CLI output, running configs, routing
   tables, and similar material are stored as `verbatim` content blocks.
   Whitespace, indentation, capitalization, prompts, and line breaks are
   preserved exactly. No normalization of any kind.
3. **Images are originals.** If an image is embedded in the source, extract
   the original bytes (`kind: "embedded"`). If direct extraction is not
   possible (e.g. a diagram drawn from vector strokes), render/crop the exact
   source region (`kind: "page_crop"`). Never recreate, redraw, or substitute
   an image. Every asset records its provenance (page + bounding box).
4. **Order is meaning.** Content blocks within a question, options within an
   interaction, and multiple images belonging to one question keep their
   source order. Questions keep their source ordinal.
5. **Flag, don't fix.** When extraction is uncertain (ambiguous segmentation,
   type/answer mismatch, unreadable region), the question is still imported
   and marked `needs_review` with descriptive issues. The importer never
   silently drops or "repairs" content, and a single bad question never aborts
   a 1000-question import.

## High-level design: the pipeline

```
 Input ──► Parser ──► Normalizer ──► Validator ──► Preview ──► Import
   │          │            │             │            │           │
 sources/  ImportSource  pipeline/    validation/  pipeline/   bundle/
 open_     .extract()    normalize.py (rule set)   preview.py  writer.py
 source()  (format-                                            (staged
           specific)                                            bundle)
```

Orchestrated by `pipeline/runner.py` (`run_import`), which returns an
`ImportOutcome` (manifest + report + result summary + preview).

- **Input** — `sources.open_source()` picks the parser by format/suffix;
  `ImportSource.describe()` identifies the document (hash, size, pages).
- **Parser** — `ImportSource.extract()` is the *only* format-specific stage.
  It streams `ExtractedQuestion` / `ExtractedGroup` / `FailedQuestion` items.
  Adding Word/JSON/CSV support later = one new `ImportSource` implementation
  registered in `sources/__init__.py`; nothing else changes.
- **Normalizer** — structural normalization only: guarantees non-empty,
  run-unique question/group/asset ids and remaps in-item image references
  when an asset id had to change. Ids are importer bookkeeping, so this is
  safe; *content is never touched*.
- **Validator** — independent rules over the stream (see below).
- **Preview** — data structures an administrator reviews before accepting an
  import: per-question stem/choices/images/type/warnings/status. Buildable
  during the run or re-derived from a bundle on disk (`preview_from_bundle`).
- **Import** — persistence into the staged bundle (`BundleWriter`). Loading
  a bundle into PostgreSQL is the web app's half of this stage and consumes
  the bundle artifact.

The pipeline is streaming end-to-end: one question (plus its asset bytes) is
in flight at a time, so 1000+ question PDFs import in bounded memory. Parsing
is fully decoupled from the UI and the database: the importer has no
knowledge of Next.js or Prisma; the web app has no knowledge of PDFs.

## Validation framework

`validation/` runs independent rules over the item stream:

- `ValidationRule` (base.py) — one rule = one concern; override
  `check_question`, `check_group`, and/or `finish` (whole-run checks such as
  group members that never appeared). Rules *observe only*: they yield
  `Issue`s and never mutate or reject.
- `Validator` (engine.py) — runs a rule list and owns the shared `RunState`
  (assets seen, question ids seen, group memberships), so rules stay
  stateless and order-independent.
- `rules/` — built-ins, registered in `default_rules()`: missing question
  number, duplicate question ids, empty stem, question-type/interaction
  mismatch, per-interaction answer-key rules (missing options, missing/
  unknown correct answers, answer-count mismatches, invalid orderings,
  broken matching pairs, invalid drag-and-drop mappings, blank problems),
  missing image references, and group-membership consistency.

To add a rule: subclass `ValidationRule` in `validation/rules/` and add it to
`default_rules()`. The engine and pipeline need no changes.

Pydantic models enforce *shape* only (types, discriminators, required
fields). Referential problems — a correct-answer id with no matching option,
an incomplete ordering — are validation-rule territory, because per rule 5 a
question with a broken answer key must still import (as `needs_review`).

## Canonical model (summary)

Defined in `importer/src/qbank_importer/model/`. Serialized as JSON in the
bundle; JSON Schemas can be exported with `qbank-import schema` for use by the
TypeScript side.

- **ContentBlock** — ordered units of question content:
  `text` (exact prose), `verbatim` (CLI/config, exact whitespace),
  `image` (reference to an Asset), `table` (exact cell text; tables that
  cannot be reconstructed faithfully are cropped as an image instead).
- **Asset** — an original image/figure: id, `embedded` or `page_crop`,
  media type, bundle-relative filename, SHA-256, and provenance
  (`page`, `bbox`).
- **Question** — id, `SourceRef` (ordinal, printed label, page span), type,
  optional group id, `stem` (content blocks), `interaction`, optional
  `explanation` blocks, and review status/issues.
- **Interaction** — a discriminated union carrying both the structure and the
  correct response for each question type:
  - `choice` — options + correct option ids (covers single choice, multiple
    choice, and true/false)
  - `ordering` — items + correct order
  - `matching` — left/right items + correct pairs
  - `drag_and_drop` — tokens + targets + correct placements
  - `fill_in_blank` — blanks with accepted answers (stem keeps the original
    placeholder text exactly as printed)
- **QuestionGroup** — scenario / case-study container: shared context blocks
  (which may span pages and include exhibits) plus the ordered member
  question ids. Scenario-based and case-study questions are regular questions
  whose `type` reflects it and whose `group_id` points at the group.

The models enforce shape only; every integrity and plausibility concern is a
validation rule (see "Validation framework" above), so nothing the source
actually says is ever unrepresentable.

## Import bundle format v1

A bundle is a directory:

```
bundle/
  manifest.json     bundle format version, importer version, source info
                    (filename, sha256, page count), counts
  questions.jsonl   one Question JSON document per line, in source order
  groups.jsonl      one QuestionGroup per line (present only if groups exist)
  assets.jsonl      one Asset metadata record per line (provenance, sha256)
  assets/           original asset files, named <asset-id>.<ext>
  report.json       ImportReport: per-question status + issues, stats
```

JSONL keeps both writing and ingestion streaming-friendly for large banks.
`BundleWriter` (importer) and `BundleReader` (importer tests today, ingestion
tooling tomorrow) are the only components that know this layout.

## PDF source — planned decomposition

`sources/pdf/` is scaffolded but intentionally not implemented yet. The
planned stages, each independently testable:

1. **Page extraction** (PyMuPDF): text spans with coordinates/fonts, embedded
   image xrefs, vector drawing regions — raw, lossless, per page.
2. **Question segmentation**: split the page stream into per-question slices
   using the document's question labels/layout. Multi-page questions and
   scenario headers are handled here.
3. **Block classification**: within a slice, classify runs as prose vs
   verbatim (monospace font / layout cues) vs figure region vs table.
4. **Assembly**: build `Question` objects + `Asset` payloads (extract embedded
   images by xref; crop vector figure regions at high DPI), emit issues for
   anything uncertain.

Heuristics in stages 2–3 must be developed against the real canonical PDF, so
they are stubs until that document is available to test against.

## Testing strategy

- Model and bundle round-trip tests use minimal synthetic structures (clearly
  fake strings, not sample exam content) — they test serialization and
  invariants, not parsing.
- PDF stage tests (future) will use small fixture PDFs generated in-test plus
  excerpts of the real document, asserting byte-exact text and asset output.
- The pipeline is testable with an in-memory fake `ImportSource`; no PDF or
  database required.
