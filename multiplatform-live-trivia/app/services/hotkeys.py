"""Global Hotkey Listener using pynput."""
from __future__ import annotations

import logging
from typing import Callable, Optional

from pynput import keyboard

logger = logging.getLogger(__name__)


class HotkeyListener:
    def __init__(
        self,
        on_start: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
    ) -> None:
        self.on_start = on_start
        self.on_stop = on_stop
        self._listener: Optional[keyboard.Listener] = None

    def start(self) -> None:
        def on_press(key):
            try:
                if key == keyboard.Key.f9:
                    logger.info("Hotkey F9 pressed: START")
                    if self.on_start:
                        self.on_start()
                elif key == keyboard.Key.f10:
                    logger.info("Hotkey F10 pressed: STOP")
                    if self.on_stop:
                        self.on_stop()
            except Exception as exc:
                logger.error(f"Error handling hotkey press: {exc}")

        self._listener = keyboard.Listener(on_press=on_press)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()