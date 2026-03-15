"""Unit tests for _extract_events in annotate_sessions.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

from annotate_sessions import _extract_events

GAME_DURATION = 300


def _frame(index, blue, orange, time_seconds):
    return {
        "index": index,
        "frame": f"{index:05d}.png",
        "blue": blue,
        "orange": orange,
        "time_seconds": time_seconds,
    }


def _base_frames(*extra):
    """Game-start frame followed by extra frames, then 3x all-None to end game."""
    start = [_frame(0, 0, 0, GAME_DURATION)]
    end = [_frame(900 + i, None, None, None) for i in range(3)]
    return start + list(extra) + end


def test_goal_detected_after_none_score_frame():
    """
    Sequence: 1-0 readable, then blue=None (bright line animation), then 2-0 readable.
    The 2-0 goal must be detected despite the intermediate None frame.
    """
    frames = _base_frames(
        _frame(10, 1, 0, 245),   # 1-0 goal
        _frame(11, None, 0, 244), # goal animation — blue score obscured by bright line
        _frame(12, 2, 0, 243),   # 2-0 goal — must be detected here
    )
    events = _extract_events(frames)
    assert len(events["goals"]) == 2, f"expected 2 goals, got {events['goals']}"
    assert events["goals"][0]["score"] == [1, 0]
    assert events["goals"][1]["score"] == [2, 0]


def test_goal_detected_after_none_time_frame():
    """
    Score ticks up on a frame where the timer is None (e.g. timer animation).
    The None frame is skipped; prev stays at b=1. The next fully-readable frame
    has b=2 and compares correctly against prev → 2-0 goal detected.
    """
    frames = _base_frames(
        _frame(10, 1, 0, 245),   # 1-0 goal
        _frame(11, 2, 0, None),  # score updated but timer momentarily unreadable — skipped
        _frame(12, 2, 0, 243),   # fully readable; compares to prev (b=1) → 2-0 goal
    )
    events = _extract_events(frames)
    assert len(events["goals"]) == 2, f"expected 2 goals, got {events['goals']}"
    assert events["goals"][0]["score"] == [1, 0]
    assert events["goals"][1]["score"] == [2, 0]


def test_goal_not_double_counted_across_none_frames():
    """
    Multiple consecutive None frames between two readable frames should not
    cause a goal to be double-counted or a spurious goal to be added.
    """
    frames = _base_frames(
        _frame(10, 1, 0, 245),
        _frame(11, None, None, None),
        _frame(12, None, None, None),
        _frame(13, 1, 0, 242),   # same score after Nones — no new goal
    )
    events = _extract_events(frames)
    assert len(events["goals"]) == 1
    assert events["goals"][0]["score"] == [1, 0]


def test_goal_detected_after_corrupt_score_frame():
    """
    Frame 114 reads blue=11 due to a bright-line artefact in the goal animation.
    This is an impossible transition (1->11), so the frame must be discarded and
    prev must NOT be updated to 11. Frame 115 (blue=2) must then compare against
    prev.blue=1 and correctly detect the 2-0 goal.
    """
    frames = _base_frames(
        _frame(113, 1, 0, 221),   # 1-0 goal
        _frame(114, 11, 0, 220),  # corrupt read — bright line artefact → must be discarded
        _frame(115, 2, 0, 220),   # 2-0 goal — must be detected against prev.blue=1
    )
    events = _extract_events(frames)
    assert len(events["goals"]) == 2, f"expected 2 goals, got {events['goals']}"
    assert events["goals"][0]["score"] == [1, 0]
    assert events["goals"][1]["score"] == [2, 0]
    assert events["goals"][1]["frame"] == "00115.png"


def test_exact_user_reported_sequence():
    """
    Mirrors the exact frames described: frame 113 = 1-0, frame 114 = None-0, frame 115 = 2-0.
    Both goals must appear in the output.
    """
    frames = _base_frames(
        _frame(113, 1, 0, 245),
        _frame(114, None, 0, 244),
        _frame(115, 2, 0, 243),
    )
    events = _extract_events(frames)
    assert len(events["goals"]) == 2, f"expected 2 goals, got {events['goals']}"
    assert events["goals"][0]["score"] == [1, 0]
    assert events["goals"][1]["score"] == [2, 0]
    assert events["goals"][1]["frame"] == "00115.png"
