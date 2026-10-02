"""Tests for app.core.leaderboard."""
from app.core.leaderboard import LeaderboardManager


def test_leaderboard_scoring_and_tiebreaking():
    lb = LeaderboardManager()

    # Alice scores at t=10.0
    lb.record_score("tiktok", "101", "Alice", timestamp=10.0)
    # Bob scores at t=12.0
    lb.record_score("facebook", "202", "Bob", timestamp=12.0)
    # Alice scores again at t=15.0 (total = 2)
    lb.record_score("tiktok", "101", "Alice", timestamp=15.0)

    board = lb.get_leaderboard()
    assert len(board) == 2
    assert board[0]["display_name"] == "Alice"
    assert board[0]["score"] == 2
    assert board[1]["display_name"] == "Bob"
    assert board[1]["score"] == 1


def test_leaderboard_tiebreak_earlier_timestamp():
    lb = LeaderboardManager()

    # Both Alice and Bob have 1 point, but Bob reached it earlier
    lb.record_score("facebook", "202", "Bob", timestamp=5.0)
    lb.record_score("tiktok", "101", "Alice", timestamp=10.0)

    board = lb.get_leaderboard()
    assert board[0]["display_name"] == "Bob"
    assert board[1]["display_name"] == "Alice"