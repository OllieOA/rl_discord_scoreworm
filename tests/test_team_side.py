"""Tests for detect_left_colour — which team colour is on the left side of the HUD."""

import json
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from capture import HUD_HEIGHT, HUD_LEFT, HUD_TOP, HUD_WIDTH
from ocr import detect_left_colour

SNIPPET_DIR  = "tests/fixtures/snippet"
SESSION_DIR  = Path("tests/fixtures/full_game_session")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_snippet(fname: str) -> np.ndarray:
    return np.array(Image.open(os.path.join(SNIPPET_DIR, fname)).convert("RGB"))


def _load_session_frame(session_dir: Path, frame_name: str) -> np.ndarray:
    """Load a full-screen session frame and crop to the HUD region."""
    full = np.array(Image.open(session_dir / frame_name).convert("RGB"))
    return full[HUD_TOP:HUD_TOP + HUD_HEIGHT, HUD_LEFT:HUD_LEFT + HUD_WIDTH]


def _glob_snippets() -> list[str]:
    """Return all snippet filenames that have a definite colour suffix (_blue or _orange)."""
    fnames = []
    for fname in os.listdir(SNIPPET_DIR):
        if fname.endswith("_blue.png") or fname.endswith("_orange.png"):
            fnames.append(fname)
    return sorted(fnames)


# ── Test 1: snippet fixtures ──────────────────────────────────────────────────

@pytest.mark.parametrize("fname", _glob_snippets())
def test_detect_left_colour_snippet(fname: str) -> None:
    expected = "blue" if fname.endswith("_blue.png") else "orange"
    frame = _load_snippet(fname)
    result = detect_left_colour(frame)
    assert result == expected, (
        f"{fname}: expected {expected!r}, got {result!r}"
    )


# ── Test 2: session sample ────────────────────────────────────────────────────

def _session_params() -> list[tuple[str, str, str]]:
    """Return (session_name, colour_on_left, frame_name) for 10 sampled frames per session."""
    params = []
    if not SESSION_DIR.exists():
        return params
    for session_dir in sorted(SESSION_DIR.iterdir()):
        if not session_dir.is_dir():
            continue
        ann_path = session_dir / "annotation.json"
        if not ann_path.exists():
            continue
        annotation = json.loads(ann_path.read_text())
        colour = annotation["colour_on_left"]
        start  = annotation["game_start"]["index"]
        end    = annotation["game_end"]["index"]

        # Collect PNG frame paths in sorted order
        frame_files = sorted(session_dir.glob("*.png"))
        # Restrict to the in-game window, excluding the last 5 frames before
        # game-end which may show transition HUD states (goal celebrations etc.)
        in_game = [f for f in frame_files if start <= int(f.stem) < max(start + 1, end - 5)]
        if not in_game:
            continue

        # Sample 10 evenly-spaced frames
        n = min(10, len(in_game))
        indices = [int(i * (len(in_game) - 1) / (n - 1)) for i in range(n)] if n > 1 else [0]
        for idx in indices:
            frame_path = in_game[idx]
            params.append((session_dir.name, colour, frame_path.name))
    return params


@pytest.mark.parametrize(
    "session_name, expected_colour, frame_name",
    _session_params(),
    ids=[f"{s}-{f}" for s, _, f in _session_params()],
)
def test_detect_left_colour_session(
    session_name: str, expected_colour: str, frame_name: str
) -> None:
    session_dir = SESSION_DIR / session_name
    frame = _load_session_frame(session_dir, frame_name)
    result = detect_left_colour(frame)
    assert result == expected_colour, (
        f"{session_name}/{frame_name}: expected {expected_colour!r}, got {result!r}"
    )
