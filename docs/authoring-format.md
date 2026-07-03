# JSON Authoring Format

The JSON source (`importer/src/qbank_importer/sources/json/`) is the
recommended way to create original question banks. You write a JSON document;
the importer runs it through the same pipeline as any other source and
produces a bundle the web app loads.

```
qbank-import json content/my-bank.json --out apps/web/content/bundle
```

## Document

```json
{
  "bank": "Optional bank name",
  "groups": [ ... ],
  "questions": [ ... ]
}
```

## Content blocks

Anywhere content is expected (`stem`, `explanation`, option/item `content`,
group `context`) you provide a list of blocks. Each block is one of:

| Block | Meaning |
|-------|---------|
| `"a plain string"` or `{"text": "..."}` | prose |
| `{"cli": "..."}` | verbatim CLI/config — whitespace preserved exactly, rendered monospace |
| `{"table": [["r1c1","r1c2"], ["r2c1","r2c2"]]}` | table with exact cell text |
| `{"image": "diagram.png", "caption": "..."}` | image file (path relative to the JSON); original bytes are embedded |

A bare string is shorthand for a single text block, so `"stem": "Question?"`
works.

## Questions

Common fields: `type` (required), `label` (printed number, optional),
`stem`, `explanation`.

- **single_choice / multiple_choice / true_false** — `options`, each
  `{"id","text"|"content","correct": true?}`. Mark the correct option(s) with
  `"correct": true`.
- **ordering** — `items` plus `correct_order` (list of item ids in order).
- **matching** — `left`, `right`, and `pairs` (`{"left": id, "right": id}`).
- **drag_and_drop** — `tokens`, `targets`, and `placements`
  (`{"token": id, "target": id}`).
- **fill_in_blank** — `blanks`, each `{"id", "accepted": ["answer", ...]}`.

## Groups (scenario / case study)

```json
"groups": [
  { "id": "s1", "kind": "scenario", "title": "...",
    "context": [ ...blocks... ], "questions": ["7", "8"] }
]
```

`questions` lists the `label`s of member questions. The group's shared context
is imported once and each member question is linked to it.

## Fidelity

The authoring format carries content through exactly as written — no
rewriting or normalization. Plausibility problems (a single-choice question
with two correct options, an ordering that misses an item) are not rejected;
they are imported and flagged `needs_review` by the pipeline's validator, the
same as any other source. See [import-engine.md](import-engine.md).

See [`content/sample-networking.json`](../content/sample-networking.json) for a
complete example.
