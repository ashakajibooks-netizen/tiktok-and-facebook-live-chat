"""Question loader service."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Union

from app.models import AnswerType, Question

"""Services question loader alias."""
from app.core.question_loader import (
    QuestionLoader,
    load_questions,
    validate_and_parse_questions,
)

__all__ = ["QuestionLoader", "load_questions", "validate_and_parse_questions"]
def _parse_answer_type(a_type_raw: str) -> AnswerType:
    if isinstance(a_type_raw, AnswerType):
        return a_type_raw

    a_type_str = str(a_type_raw).strip()

    # 1. Try Enum name lookup (e.g., AnswerType["EXACT"])
    try:
        return AnswerType[a_type_str.upper()]
    except KeyError:
        pass

    # 2. Try direct value lookup
    try:
        return AnswerType(a_type_str)
    except ValueError:
        pass

    # 3. Try lowercase/uppercase value lookup
    for attempt in (a_type_str.lower(), a_type_str.upper()):
        try:
            return AnswerType(attempt)
        except ValueError:
            pass

    # 4. Match against Enum member names or values
    clean_str = a_type_str.lower().replace("_", "")
    for member in AnswerType:
        m_name = member.name.lower().replace("_", "")
        m_val = str(member.value).lower().replace("_", "")
        if clean_str in (m_name, m_val) or m_name in clean_str or m_val in clean_str:
            return member

    # Default to first enum member if matching fails
    return list(AnswerType)[0]


def load_questions(path: Union[str, Path]) -> List[Question]:
    file_path = Path(path)
    if not file_path.exists():
        raise ValueError(f"Question file not found at path: {path}")

    with file_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, list):
        raise ValueError("Questions file must contain a JSON array.")

    questions: List[Question] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Question at index {idx} must be an object.")

        question_text = item.get("question")
        if not question_text or not isinstance(question_text, str):
            raise ValueError(f"Missing or invalid 'question' field at index {idx}.")

        answers = item.get("answers")
        if not answers or not isinstance(answers, list):
            raise ValueError(f"Missing or invalid 'answers' list at index {idx}.")

        raw_answer_type = item.get("answer_type", "")
        a_type = _parse_answer_type(raw_answer_type) if raw_answer_type else list(AnswerType)[0]

        questions.append(
            Question(
                question=question_text,
                answers=tuple(str(a) for a in answers),
                answer_type=a_type,
            )
        )

    return questions