# CCNA Learning Platform

A web-based learning platform for Cisco CCNA certification, built around
interactive question types, learning analytics, and (eventually) additional
certifications.

## Repository layout

```
apps/web/       Next.js web platform (TypeScript). Serves learners and admins.
                Owns the PostgreSQL database (Prisma schema in apps/web/prisma).

importer/       Question Bank Import Engine (Python). A standalone package +
                CLI that converts source documents (PDF first) into a
                canonical "import bundle" that the web app ingests.

docs/           Architecture and format documentation.
```

## Why two languages

The import engine has strict fidelity requirements: original embedded images
must be extracted byte-for-byte where possible, figures must be cropped from
the exact PDF region when direct extraction is impossible, and CLI output must
keep its exact whitespace. Python's PyMuPDF is the strongest tool available
for coordinate-aware PDF text, image, and region extraction, so the importer
is Python. The platform itself is a standard Next.js/TypeScript app.

The two sides are decoupled by the **import bundle** format
(see [docs/import-engine.md](docs/import-engine.md)): the importer writes a
bundle (manifest + questions as JSONL + original asset files), and the web app
loads bundles into PostgreSQL. Any future source format (Word, JSON, CSV,
Markdown) is a new importer source that targets the same bundle format —
nothing downstream changes.

## Getting started

### Importer (Python 3.11+)

```
cd importer
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -e .[dev]
pytest
qbank-import --help
```

### Web app (Node 20+)

```
cd apps/web
npm install
npm run dev
```

## Status

- [x] Canonical question model (all planned question types)
- [x] Import bundle format v1 (streaming writer/reader)
- [x] Pipeline stages: Input → Parser → Normalizer → Validator → Preview → Import
- [x] Modular validation framework (independent rules, `validation/rules/`)
- [x] Preview + ImportResult structures, CLI (`pdf`, `preview`, `schema`)
- [ ] PDF extraction implementation (`importer/src/qbank_importer/sources/pdf/`)
- [ ] Bundle ingestion endpoint in the web app
- [ ] Admin review UI for flagged questions
