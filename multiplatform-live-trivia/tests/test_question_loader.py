"""Tests for app.services.question_loader."""
import json
import pytest

from app.models import AnswerType
from app.services.question_loader import load_questions


def test_load_valid_questions(tmp_path):
    data = [
        {
            "question": "What is the capital of France?",
            "answers": ["Paris"],
            "answer_type": "text",
        },
        {
            "question": "What is 2 + 2?",
            "answers": ["4"],
            "answer_type": "number",
        },
    ]
    file_path = tmp_path / "questions.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    questions = load_questions(file_path)
    assert len(questions) == 2
    assert questions[0].question == "What is the capital of France?"
    assert questions[0].answer_type == AnswerType.TEXT
    assert questions[1].answer_type == AnswerType.NUMBER


def test_rejects_duplicate_questions(tmp_path):
    data = [
        {"question": "Who wrote Hamlet?", "answers": ["Shakespeare"]},
        {"question": "who wrote hamlet?", "answers": ["William Shakespeare"]},
    ]
    file_path = tmp_path / "questions.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate normalized question"):
        load_questions(file_path)


def test_rejects_duplicate_answers_in_same_question(tmp_path):
    data = [
        {"question": "Name a color.", "answers": ["Red", "red"]},
    ]
    file_path = tmp_path / "questions.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate answer"):
        load_questions(file_path)


def test_rejects_empty_question_text(tmp_path):
    data = [
        {"question": "  ", "answers": ["Answer"]},
    ]
    file_path = tmp_path / "questions.json"
    file_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="missing or empty"):
        load_questions(file_path)