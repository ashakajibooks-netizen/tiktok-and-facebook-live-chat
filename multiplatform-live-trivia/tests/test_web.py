"""Tests for Web & REST Control API endpoints."""
import pytest
from fastapi.testclient import TestClient

from app.core.engine import TriviaEngine
from app.models import Question
from app.web.server import create_app


@pytest.fixture
def test_app(tmp_path):
    import asyncio
    questions = [Question(question="Test Q?", answers=("Test A",))]
    chat_queue = asyncio.Queue(maxsize=10)
    engine = TriviaEngine(questions=questions, chat_queue=chat_queue)
    return create_app(engine, config={})


def test_api_status(test_app):
    client = TestClient(test_app)
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "IDLE" or data["state"] == "WAITING_FOR_START"


def test_api_control_start(test_app):
    client = TestClient(test_app)
    response = client.post("/api/control", json={"action": "START"})
    assert response.status_code == 200
    assert response.json()["action"] == "START"