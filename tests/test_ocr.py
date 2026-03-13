"""Tests for OCR reading of known HUD captures."""

import numpy as np
import pytest
from PIL import Image

from ocr import read_hud

FIXTURES = "tests/fixtures"


def load(filename: str) -> np.ndarray:
    """Load a fixture image as an RGB numpy array (same format as grab_frame)."""
    return np.array(Image.open(f"{FIXTURES}/{filename}").convert("RGB"))


def test_game_start_timer():
    """Timer should read 5:00 (300 seconds) from the game-start fixture."""
    frame = load("game_start_0_0_5_00.png")
    reading = read_hud(frame)
    assert reading.time == 300, (
        f"Expected time=300 (5:00), got {reading.time}"
    )


@pytest.mark.skip(reason="Score templates not yet captured — run capture_templates.py --count 9 first")
def test_game_start_scores():
    """Both scores should read 0 from the game-start fixture."""
    frame = load("game_start_0_0_5_00.png")
    reading = read_hud(frame)
    assert reading.blue == 0, f"Expected left score=0, got {reading.blue}"
    assert reading.orange == 0, f"Expected right score=0, got {reading.orange}"


@pytest.mark.skip(reason="Score templates not yet captured — score reading required for IN_GAME transition")
def test_game_start_triggers_in_game(tmp_path, monkeypatch):
    """A 0-0 / 5:00 reading should transition the tracker from IDLE to IN_GAME."""
    from game_state import GameTracker, State

    frame = load("game_start_0_0_5_00.png")
    fired = []
    tracker = GameTracker(on_game_over=lambda goals: fired.append(goals))
    reading = read_hud(frame)
    tracker._tick(reading)

    assert tracker._state is State.IN_GAME, (
        f"Expected IN_GAME after 0-0/5:00 reading, got {tracker._state.name}. "
        f"OCR reading was: {reading}"
    )
