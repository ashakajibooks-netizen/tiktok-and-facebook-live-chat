from datetime import datetime, timezone

from app.models import (
    ChatMessage,
    GameCommand,
    GameCommandType,
    GameState,
    Platform,
    PlatformStatusType,
    Question,
)


def test_chat_message_supports_optional_message_id_and_platform_timestamp():
    msg = ChatMessage(
        platform=Platform.TIKTOK,
        message_id=None,
        user_id="123",
        username="Alice",
        text="Paris",
        received_at=10.5,
        platform_created_at=datetime.now(timezone.utc),
    )
    assert msg.message_id is None
    assert msg.platform is Platform.TIKTOK


def test_core_enums_have_required_values():
    assert GameState.WAITING_FOR_START.value == "WAITING_FOR_START"
    assert GameCommand(GameCommandType.START).command is GameCommandType.START
    assert PlatformStatusType.CONNECTED.value == "CONNECTED"


def test_question_model_preserves_aliases():
    q = Question(
        question="Who wrote Hamlet?",
        answers=("William Shakespeare", "Shakespeare"),
    )
    assert q.answers == ("William Shakespeare", "Shakespeare")
