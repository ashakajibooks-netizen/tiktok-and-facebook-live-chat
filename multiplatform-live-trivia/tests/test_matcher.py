"""Matcher Unit Tests."""
from app.core.matcher import match_answer


def test_text_fuzzy_and_exact():
    assert match_answer("Paris", ["Paris"])
    assert match_answer("paris!!!", ["Paris"])
    assert match_answer("Pariss", ["Paris"])  # rapidfuzz score >= 85
    assert not match_answer("London", ["Paris"])


def test_numeric_equivalence():
    assert match_answer("1,000,000", ["1000000"])
    assert match_answer("1 000 000", ["1000000"])
    assert match_answer("3.14", ["3,14"])
    assert not match_answer("1000001", ["1000000"])


def test_numbered_text_strictness():
    assert match_answer("Apollo 11", ["Apollo 11"])
    assert not match_answer("Apollo 12", ["Apollo 11"])


def test_roman_numerals():
    assert match_answer("VIII", ["VIII"])
    assert not match_answer("VII", ["VIII"])


def test_short_answer_protection():
    assert match_answer("cat", ["cat"])
    assert not match_answer("car", ["cat"])  # Strict match required for length <= 3