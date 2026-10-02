"""Atomic persistence module with Windows PermissionError retry handling."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def atomic_write_file(filepath: str | Path, content: str, retries: list[float] | None = None) -> bool:
    if retries is None:
        retries = [0.05, 0.1, 0.2, 0.4]

    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f".tmp_{os.getpid()}")

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        for attempt, delay in enumerate([0.0] + retries):
            if delay > 0:
                time.sleep(delay)
            try:
                os.replace(temp_path, path)
                return True
            except PermissionError as e:
                if attempt == len(retries):
                    logger.error("Failed to replace file %s due to lock: %s", path, e)
                    raise
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

    return False


def save_json_atomic(filepath: str | Path, data: Any) -> bool:
    json_str = json.dumps(data, indent=2, ensure_ascii=False)
    return atomic_write_file(filepath, json_str)