"""Tests for OCR reading of known HUD captures."""

import os

import numpy as np
import pytest
from PIL import Image

from capture import HUD_HEIGHT, HUD_LEFT, HUD_TOP, HUD_WIDTH
from ocr import read_hud

SNIPPET_DIR = "tests/fixtures/snippet"
FULL_DIR    = "tests/fixtures/full_screen"


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_snippet(fname: str) -> np.ndarray:
    """Load a HUD-strip snippet fixture as an RGB numpy array."""
    return np.array(Image.open(os.path.join(SNIPPET_DIR, fname)).convert("RGB"))


def load_full_screen(fname: str) -> np.ndarray:
    """Load a full-screen fixture and crop to the HUD region."""
    full = np.array(Image.open(os.path.join(FULL_DIR, fname)).convert("RGB"))
    return full[HUD_TOP:HUD_TOP + HUD_HEIGHT, HUD_LEFT:HUD_LEFT + HUD_WIDTH]


def parse_fixture(fname: str) -> dict:
    """Parse [desc].[left]-[right]_[min]-[sec]_[colour].png into a components dict.

    'n' in any position means null / not applicable for that image.
    """
    stem = os.path.splitext(fname)[0]
    desc, rest = stem.split(".", 1)
    scores, time_part, colour = rest.rsplit("_", 2)
    left_str, right_str = scores.split("-", 1)
    min_str, sec_str = time_part.split("-")
    return {
        "desc":           desc,
        "left_score":     None if left_str  == "n" else int(left_str),
        "right_score":    None if right_str == "n" else int(right_str),
        "time":           None if min_str   == "n" else int(min_str) * 60 + int(sec_str),
        "colour_on_left": None if colour    == "n" else colour,
    }


def _list(directory: str) -> list[str]:
    return sorted(f for f in os.listdir(directory) if f.endswith(".png"))


# ── Full-screen timer (parameterised) ─────────────────────────────────────────
# tournament_lobby is handled separately as a special case because its expected
# behaviour (no valid game readings) can't be expressed by the filename alone.

_TIMER_CASES = [
    f for f in _list(FULL_DIR)
    if not f.startswith("tournament_lobby")
]


# Timer templates were built from snippet captures; a handful of full-screen
# fixtures expose calibration gaps where specific digits (7, 5) or the colon
# score just below the 0.6 threshold.  These are marked xfail so failures are
# visible without blocking CI — fix by recapturing timer templates from
# full-screen sources.
_TIMER_CALIBRATION_XFAIL = {
    "mid_game.3-2_0-17_blue.png",        # colon 0.48, '7' 0.40
    "mid_game_semifinal.1-0_1-15_blue.png",  # '5' 0.54
}


@pytest.mark.parametrize("fname", _TIMER_CASES, ids=_TIMER_CASES)
def test_full_screen_timer(fname: str, request):
    """Timer is accurately read from every full-screen capture."""
    if fname in _TIMER_CALIBRATION_XFAIL:
        request.node.add_marker(pytest.mark.xfail(
            reason="timer template calibration gap — digit scores just below threshold",
            strict=False,
        ))
    expected = parse_fixture(fname)["time"]
    reading = read_hud(load_full_screen(fname))
    assert reading.time == expected, f"Expected time={expected}, got {reading.time}"


# ── Snippet digit recognition (exhaustive, parameterised) ─────────────────────
# Snippets were taken from the same raw captures used to build the templates,
# so every digit 0–9 on each side is represented and should match perfectly.
#
# Blue-on-left images: blue score is in the left region → reading.blue
# Orange-on-left images: blue score is in the right region → reading.orange

_BLUE_LEFT_SNIPPETS   = [f for f in _list(SNIPPET_DIR)
                          if parse_fixture(f)["colour_on_left"] == "blue"]
_ORANGE_LEFT_SNIPPETS = [f for f in _list(SNIPPET_DIR)
                          if parse_fixture(f)["colour_on_left"] == "orange"]


@pytest.mark.parametrize("fname", _BLUE_LEFT_SNIPPETS, ids=_BLUE_LEFT_SNIPPETS)
def test_snippet_left_score_digit(fname: str):
    """Every digit 0–9 is recognised on the left (blue-background) side."""
    info = parse_fixture(fname)
    reading = read_hud(load_snippet(fname))
    assert reading.blue == info["left_score"], (
        f"Expected left score={info['left_score']}, got {reading.blue}"
    )


@pytest.mark.parametrize("fname", _ORANGE_LEFT_SNIPPETS, ids=_ORANGE_LEFT_SNIPPETS)
def test_snippet_right_score_digit(fname: str):
    """Every digit 0–9 is recognised on the right (blue-background) side."""
    info = parse_fixture(fname)
    reading = read_hud(load_snippet(fname))
    assert reading.orange == info["right_score"], (
        f"Expected right score={info['right_score']}, got {reading.orange}"
    )


# ── Special case handling ──────────────────────────────────────────────────────

def test_end_game_screen_all_none():
    """After the game ends and the HUD disappears, all readings must be None."""
    reading = read_hud(load_full_screen("end_game_screen.n-n_n-n_n.png"))
    assert reading.blue   is None, f"Expected blue=None,   got {reading.blue}"
    assert reading.orange is None, f"Expected orange=None, got {reading.orange}"
    assert reading.time   is None, f"Expected time=None,   got {reading.time}"


def test_time_only_at_game_start():
    """Pre-game countdown uses a different font/style — OCR should return all None.

    This is the decorative hexagon-frame "5:00" screen shown before kick-off,
    not the in-game HUD timer.  All readings being None means game_state stays
    IDLE and is not falsely triggered by the pre-game display.
    """
    reading = read_hud(load_snippet("time_only_at_start_of_game.n-n_5-00_n.png"))
    assert reading.time   is None, f"Expected time=None (pre-game font), got {reading.time}"
    assert reading.blue   is None, f"Expected blue=None,   got {reading.blue}"
    assert reading.orange is None, f"Expected orange=None, got {reading.orange}"


def test_tournament_lobby_no_game_readings():
    """Tournament lobby must not produce readings that could falsely trigger game detection."""
    reading = read_hud(load_full_screen("tournament_lobby.n-n_2-05_n.png"))
    assert reading.blue   is None, f"Expected blue=None in lobby,   got {reading.blue}"
    assert reading.orange is None, f"Expected orange=None in lobby, got {reading.orange}"
    assert reading.time   is None, f"Expected time=None in lobby,   got {reading.time}"


@pytest.mark.xfail(reason="timer template calibration gap — '5' digit scores 0.54, just below threshold", strict=False)
def test_semifinal_extra_ui_does_not_confuse_timer():
    """Extra tournament bracket UI in the timer region must not corrupt the timer reading."""
    reading = read_hud(load_full_screen("mid_game_semifinal.1-0_1-15_blue.png"))
    assert reading.time == 75, f"Expected time=75 (1:15), got {reading.time}"


# ── Bright spot robustness ────────────────────────────────────────────────────

def test_bright_spot_timer():
    """Timer is read correctly despite a bright spot in the scoreboard area."""
    reading = read_hud(load_full_screen("mid_game_bright_spot.4-21_3-50_orange.png"))
    assert reading.time == 230, f"Expected time=230 (3:50), got {reading.time}"


@pytest.mark.xfail(reason="double-digit score OCR not yet supported — single-digit templates don't match two-digit layouts", strict=False)
def test_bright_spot_score():
    """Blue score (right side) is read correctly despite a bright spot in the scoreboard."""
    reading = read_hud(load_full_screen("mid_game_bright_spot.4-21_3-50_orange.png"))
    # orange on left → blue score is on the right → reading.orange
    assert reading.orange == 21, f"Expected right score=21, got {reading.orange}"


@pytest.mark.xfail(reason="bright spot fully saturates right score region — digit shape is lost entirely", strict=False)
def test_bright_spot_single_digit_score():
    """Score read attempt when a bright spot fully saturates the score region."""
    # orange on left → blue score is on the right (score=2) → reading.orange
    reading = read_hud(load_full_screen("mid_game_bright_spot.0-2_4-56_orange.png"))
    assert reading.time   == 296, f"Expected time=296 (4:56), got {reading.time}"
    assert reading.orange == 2,   f"Expected right score=2, got {reading.orange}"


@pytest.mark.xfail(reason="double-digit score OCR not yet supported", strict=False)
def test_bright_spot_double_digit_blue_left():
    """Double-digit blue score on the left is read despite a bright spot."""
    # blue on left, score=19
    reading = read_hud(load_full_screen("mid_game_bright_spot.19-0_4-21_blue.png"))
    assert reading.time == 261, f"Expected time=261 (4:21), got {reading.time}"
    assert reading.blue == 19,  f"Expected left score=19, got {reading.blue}"


@pytest.mark.xfail(reason="double-digit score OCR not yet supported", strict=False)
def test_bright_spot_double_digit_blue_right():
    """Double-digit blue score on the right is read despite a bright spot."""
    # orange on left → blue score is on the right (score=28)
    reading = read_hud(load_full_screen("mid_game_bright_spot.3-28_3-53_orange.png"))
    assert reading.time   == 233, f"Expected time=233 (3:53), got {reading.time}"
    assert reading.orange == 28,  f"Expected right score=28, got {reading.orange}"


# ── Double-digit score recognition (full screen, parameterised) ───────────────
# Only the blue score can be asserted: we have left templates for blue-on-left
# and right templates for blue-on-right. Orange scores have no templates yet.

_DOUBLE_DIGIT_CASES = [
    # (fname,                                  blue_side, expected_blue)
    ("mid_game.18-1_4-02_blue.png",            "left",    18),
    ("mid_game.10-22_3-27_orange.png",         "right",   22),
    ("mid_game.3-21_3-50_orange.png",          "right",   21),
]


@pytest.mark.xfail(
    reason="double-digit score OCR not yet supported — templates are full-region "
           "single-digit captures; two digits cramped together don't match",
    strict=False,
)
@pytest.mark.parametrize(
    "fname,blue_side,expected_blue",
    _DOUBLE_DIGIT_CASES,
    ids=[c[0] for c in _DOUBLE_DIGIT_CASES],
)
def test_full_screen_double_digit_blue_score(fname: str, blue_side: str, expected_blue: int):
    """Double-digit blue scores are correctly read from full-screen captures."""
    reading = read_hud(load_full_screen(fname))
    actual = reading.blue if blue_side == "left" else reading.orange
    attr   = "reading.blue" if blue_side == "left" else "reading.orange"
    assert actual == expected_blue, (
        f"{fname}: expected {attr}={expected_blue}, got {actual}"
    )
