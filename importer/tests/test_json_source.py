"""Tests for the JSON authoring source."""

import json

from qbank_importer.model import QuestionType
from qbank_importer.pipeline import run_import
from qbank_importer.sources import ExtractedGroup, FailedQuestion, open_source
from qbank_importer.sources.json import JsonImportSource


def write(tmp_path, doc, name="bank.json"):
    path = tmp_path / name
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def extract(path):
    return list(JsonImportSource(path).extract())


def test_open_source_selects_json_by_suffix(tmp_path):
    path = write(tmp_path, {"questions": []})
    assert isinstance(open_source(path), JsonImportSource)


def test_single_choice_with_cli_block(tmp_path):
    path = write(
        tmp_path,
        {
            "questions": [
                {
                    "type": "single_choice",
                    "label": "1",
                    "stem": [{"text": "Question?"}, {"cli": "Router# show ip route\n  C 10.0.0.0"}],
                    "options": [
                        {"id": "a", "text": "Alpha", "correct": True},
                        {"id": "b", "text": "Beta"},
                    ],
                    "explanation": ["Because alpha."],
                }
            ]
        },
    )
    (item,) = extract(path)
    q = item.question
    assert q.type is QuestionType.SINGLE_CHOICE
    assert q.stem[1].kind == "verbatim"
    assert q.stem[1].text == "Router# show ip route\n  C 10.0.0.0"
    assert q.interaction.correct_option_ids == ["a"]
    assert q.explanation[0].text == "Because alpha."


def test_ordering_and_fill_in_blank(tmp_path):
    path = write(
        tmp_path,
        {
            "questions": [
                {
                    "type": "ordering",
                    "stem": "Order them.",
                    "items": [{"id": "x", "text": "X"}, {"id": "y", "text": "Y"}],
                    "correct_order": ["y", "x"],
                },
                {
                    "type": "fill_in_blank",
                    "stem": "The command is ____.",
                    "blanks": [{"id": "b1", "accepted": ["startup-config"]}],
                },
            ]
        },
    )
    items = extract(path)
    assert items[0].question.interaction.correct_order == ["y", "x"]
    assert items[1].question.interaction.blanks[0].accepted == ["startup-config"]


def test_scenario_group_emitted_before_members(tmp_path):
    path = write(
        tmp_path,
        {
            "groups": [
                {
                    "id": "s1",
                    "kind": "scenario",
                    "title": "Branch office",
                    "context": ["Shared context."],
                    "questions": ["1", "2"],
                }
            ],
            "questions": [
                {
                    "type": "single_choice",
                    "label": "1",
                    "stem": "Q1?",
                    "options": [{"id": "a", "text": "A", "correct": True}, {"id": "b", "text": "B"}],
                },
                {
                    "type": "single_choice",
                    "label": "2",
                    "stem": "Q2?",
                    "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B", "correct": True}],
                },
            ],
        },
    )
    items = extract(path)
    assert isinstance(items[0], ExtractedGroup)
    assert items[0].group.title == "Branch office"
    assert items[0].group.question_ids == ["q1", "q2"]
    assert [i.question.group_id for i in items[1:]] == ["s1", "s1"]


def test_bad_question_becomes_failed_not_fatal(tmp_path):
    path = write(
        tmp_path,
        {
            "questions": [
                {"type": "not_a_type", "stem": "Broken"},
                {
                    "type": "single_choice",
                    "stem": "Good?",
                    "options": [{"id": "a", "text": "A", "correct": True}, {"id": "b", "text": "B"}],
                },
            ]
        },
    )
    items = extract(path)
    assert isinstance(items[0], FailedQuestion)
    assert items[0].issues[0].code == "authoring_error"
    assert items[1].question.type is QuestionType.SINGLE_CHOICE


def test_image_bytes_embedded(tmp_path):
    img = tmp_path / "diagram.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    path = write(
        tmp_path,
        {
            "questions": [
                {
                    "type": "single_choice",
                    "stem": [{"text": "See figure."}, {"image": "diagram.png", "caption": "Topology"}],
                    "options": [{"id": "a", "text": "A", "correct": True}, {"id": "b", "text": "B"}],
                }
            ]
        },
    )
    (item,) = extract(path)
    assert len(item.assets) == 1
    assert item.assets[0].data == b"\x89PNG\r\n\x1a\nfake"
    image_blocks = [b for b in item.question.stem if b.kind == "image"]
    assert image_blocks[0].caption == "Topology"
    assert image_blocks[0].asset_id == item.assets[0].asset.id


def test_end_to_end_pipeline(tmp_path):
    path = write(
        tmp_path,
        {
            "questions": [
                {
                    "type": "multiple_choice",
                    "stem": "Pick two.",
                    "options": [
                        {"id": "a", "text": "A", "correct": True},
                        {"id": "b", "text": "B"},
                        {"id": "c", "text": "C", "correct": True},
                    ],
                }
            ]
        },
    )
    outcome = run_import(open_source(path), tmp_path / "bundle")
    assert outcome.result.questions_imported == 1
    assert outcome.result.questions_skipped == 0
    assert outcome.result.errors == 0
