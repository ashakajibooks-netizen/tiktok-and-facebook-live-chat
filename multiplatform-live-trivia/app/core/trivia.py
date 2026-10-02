"""Trivia Game Engine implementing monotonic timing and state machine."""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Set, Tuple

from app.core.matcher import matches_answer
from app.models import ChatMessage, GameCommand, GameSnapshot, Question

logger = logging.getLogger(__name__)


class GameState(Enum):
    IDLE = "IDLE"
    WAITING_FOR_START = "WAITING_FOR_START"
    ACTIVE = "ACTIVE"
    DRAINING = "DRAINING"
    RESULT = "RESULT"
    TRANSITION = "TRANSITION"
    FINISHED = "FINISHED"
    STOPPED = "STOPPED"


class TriviaEngine:

    def __init__(
        self,
        questions: list[Question],
        chat_queue: asyncio.Queue[ChatMessage],
        command_queue: asyncio.Queue[GameCommand] | None = None,
        question_duration_sec: float = 10.0,
        question_time_sec: float | None = None,
        result_duration_sec: float = 3.0,
        transition_duration_sec: float = 3.0,
        transition_time_sec: float | None = None,
        fuzzy_threshold: float = 85.0,
        drain_idle_ms: float = 50.0,
        drain_hard_cap_ms: float = 1500.0,
        fb_tolerance_sec: float = 1.0,
    ):
        self.questions = questions
        self.chat_queue = chat_queue
        self.command_queue = command_queue or asyncio.Queue()
        self.question_time_sec = (
            question_time_sec if question_time_sec is not None else question_duration_sec
        )
        self.transition_time_sec = (
            transition_time_sec if transition_time_sec is not None else transition_duration_sec
        )
        self.result_duration_sec = result_duration_sec
        self.fuzzy_threshold = fuzzy_threshold
        self.drain_idle_ms = drain_idle_ms / 1000.0
        self.drain_hard_cap_ms = drain_hard_cap_ms / 1000.0
        self.fb_tolerance_sec = fb_tolerance_sec

        self.state = GameState.WAITING_FOR_START
        self.current_question_idx = 0
        self.scores: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.answered_users: Set[Tuple[str, str]] = set()

        self.round_start_mono: float = 0.0
        self.round_start_wall_utc: datetime = datetime.now(timezone.utc)
        self.deadline_mono: float = 0.0
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start engine background task if running inside an event loop."""
        if self._task is None or self._task.done():
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self.run())
            except RuntimeError:
                pass

    async def stop(self) -> None:
        """Stop trivia engine loop and cancel background task."""
        self.state = GameState.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def handle_command(self, command: GameCommand) -> None:
        """Enqueue command for immediate execution."""
        self.command_queue.put_nowait(command)

    async def run(self) -> None:
        """Main trivia execution loop."""
        while self.state not in (GameState.FINISHED, GameState.STOPPED):
            await self._process_commands()

            if self.state in (GameState.WAITING_FOR_START, GameState.IDLE):
                await self._drain_queue_discard()
                await asyncio.sleep(0.02)

            elif self.state == GameState.ACTIVE:
                await self._process_active_round()

            elif self.state == GameState.DRAINING:
                await self._process_draining()

            elif self.state == GameState.RESULT:
                await self._drain_queue_discard()
                await asyncio.sleep(self.transition_time_sec)
                self.current_question_idx += 1
                if self.current_question_idx >= len(self.questions):
                    self.state = GameState.FINISHED
                else:
                    self.state = GameState.WAITING_FOR_START

    async def _process_commands(self) -> None:
        while not self.command_queue.empty():
            cmd = self.command_queue.get_nowait()
            action_raw = getattr(cmd, "command", None) or getattr(cmd, "action", None)
            if hasattr(action_raw, "value"):
                action_str = str(action_raw.value).upper()
            elif hasattr(action_raw, "name"):
                action_str = str(action_raw.name).upper()
            else:
                action_str = str(action_raw).upper()

            if "STOP" in action_str:
                self.state = GameState.STOPPED
            elif "START" in action_str and self.state in (GameState.WAITING_FOR_START, GameState.IDLE):
                self._start_round()

    def _start_round(self) -> None:
        self.answered_users.clear()
        self.round_start_mono = time.monotonic()
        self.round_start_wall_utc = datetime.now(timezone.utc)
        self.deadline_mono = self.round_start_mono + self.question_time_sec
        self.state = GameState.ACTIVE

    async def _process_active_round(self) -> None:
        while time.monotonic() < self.deadline_mono and self.state == GameState.ACTIVE:
            await self._process_commands()
            try:
                msg = await asyncio.wait_for(self.chat_queue.get(), timeout=0.02)
                self._evaluate_message(msg)
            except asyncio.TimeoutError:
                continue

        if self.state == GameState.ACTIVE:
            self.state = GameState.DRAINING

    async def _process_draining(self) -> None:
        drain_start = time.monotonic()
        last_msg_time = time.monotonic()

        while True:
            now = time.monotonic()
            if (now - drain_start) >= self.drain_hard_cap_ms:
                break
            if (now - last_msg_time) >= self.drain_idle_ms:
                break

            try:
                msg = await asyncio.wait_for(self.chat_queue.get(), timeout=0.01)
                last_msg_time = time.monotonic()
                self._evaluate_message(msg)
            except asyncio.TimeoutError:
                continue

        self.state = GameState.RESULT

    def _evaluate_message(self, msg: ChatMessage) -> None:
        try:
            msg_text = getattr(msg, "text", None) or getattr(msg, "message", "")
            display_name = (
                getattr(msg, "display_name", None)
                or getattr(msg, "username", None)
                or getattr(msg, "user_id", "unknown")
            )
            user_id = getattr(msg, "user_id", "unknown")

            platform_raw = getattr(msg, "platform", "unknown")
            if hasattr(platform_raw, "value"):
                platform_str = str(platform_raw.value)
            else:
                platform_str = str(platform_raw)

            # Ignore late messages
            msg_rx = getattr(msg, "received_at", None)
            if msg_rx is not None and self.round_start_mono > 0 and self.deadline_mono > 0:
                if msg_rx < (self.round_start_mono - 0.05) or msg_rx > self.deadline_mono:
                    return

            platform_created_at = getattr(msg, "platform_created_at", None)
            if platform_str.lower() == "facebook" and platform_created_at:
                earliest_allowed = self.round_start_wall_utc.timestamp() - self.fb_tolerance_sec
                if isinstance(platform_created_at, (int, float)):
                    ts = platform_created_at
                elif hasattr(platform_created_at, "timestamp"):
                    ts = platform_created_at.timestamp()
                else:
                    ts = 0.0
                if ts < earliest_allowed:
                    return

            player_key = (platform_str.lower(), str(user_id))
            if player_key in self.answered_users:
                return

            self.answered_users.add(player_key)

            if not self.questions or self.current_question_idx >= len(self.questions):
                return

            current_q = self.questions[self.current_question_idx]
            q_answers = getattr(current_q, "answers", ())
            ans_type = getattr(current_q, "answer_type", None)
            ans_type_str = ans_type.name if hasattr(ans_type, "name") else (str(ans_type) if ans_type else None)

            if matches_answer(msg_text, q_answers, self.fuzzy_threshold, ans_type_str):
                if player_key not in self.scores:
                    self.scores[player_key] = {
                        "platform": platform_str,
                        "user_id": str(user_id),
                        "display_name": str(display_name),
                        "username": str(display_name),
                        "score": 0,
                        "score_reached_at": 0.0,
                    }
                self.scores[player_key]["score"] += 1
                self.scores[player_key]["score_reached_at"] = time.monotonic()
        except Exception as e:
            logger.exception("Error evaluating message: %s", e)

    async def _drain_queue_discard(self) -> None:
        while not self.chat_queue.empty():
            try:
                self.chat_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def get_snapshot(self) -> GameSnapshot:
        current_q = (
            self.questions[self.current_question_idx]
            if self.questions and 0 <= self.current_question_idx < len(self.questions)
            else None
        )

        sorted_scores = sorted(
            self.scores.values(),
            key=lambda x: (-x["score"], x["score_reached_at"])
        )

        leaderboard_entries = [
            {
                "display_name": entry.get("display_name") or entry.get("username", ""),
                "username": entry.get("display_name") or entry.get("username", ""),
                "score": entry["score"],
                "platform": entry.get("platform", ""),
            }
            for entry in sorted_scores
        ]

        state_str = self.state.name if hasattr(self.state, "name") else str(self.state)

        return GameSnapshot(
            state=state_str,
            question_number=self.current_question_idx + 1,
            total_questions=len(self.questions),
            question=current_q.question if current_q else "",
            deadline=self.deadline_mono,
            platforms={},
            queue_size=self.chat_queue.qsize(),
            queue_capacity=getattr(self.chat_queue, "maxsize", 100),
            dropped_messages=0,
            leaderboard=leaderboard_entries,
        )