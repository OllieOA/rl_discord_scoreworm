"""
End-to-end tests replaying full-game sessions through the GameTracker state
machine using annotation data, then generating scoreworm images for visual
inspection.

Readings are reconstructed from annotation.json (not raw OCR):
  - game-start frame (0-0, 5:00)
  - one reading per goal at its annotated time
  - OT transition frames for overtime sessions
  - 3 all-None frames to trigger game-end

Scoreworm images are saved to tests/output/scoreworms/ (gitignored).
"""

import json
from pathlib import Path

import pytest

import scoreworm
from game_state import GAME_DURATION, GameTracker, GoalEvent
from ocr import HudReading

SESSION_DIR = Path("tests/fixtures/full_game_session")
SESSIONS = sorted(d.name for d in SESSION_DIR.iterdir() if d.is_dir())


# ── helpers ───────────────────────────────────────────────────────────────────


def _gs_winner(annotation: dict) -> str | None:
    """
    Translate expected_winner (actual team name) to game_state perspective.

    game_state always treats the left-side score as 'blue' and right as
    'orange', regardless of actual team colours.  When colour_on_left is
    'orange', the labels are swapped relative to the actual teams.
    """
    winner = annotation.get("expected_winner")
    if winner is None or annotation["colour_on_left"] == "blue":
        return winner
    return "orange" if winner == "blue" else "blue"


def _build_readings(annotation: dict) -> list[HudReading]:
    """
    Reconstruct a minimal HudReading sequence from annotation data sufficient
    to drive the GameTracker state machine through a full game.
    """
    readings: list[HudReading] = [HudReading(blue=0, orange=0, time=GAME_DURATION)]

    goals = annotation["goals"]
    reg_goals = [g for g in goals if not g["is_overtime"]]
    ot_goals  = [g for g in goals if g["is_overtime"]]

    for goal in reg_goals:
        blue, orange = goal["score"]
        readings.append(HudReading(blue=blue, orange=orange, time=goal["time_seconds"]))

    if annotation["expected_end_type"] == "normal":
        # Simulate the timer hitting 0:00 so _timer_reached_zero is set
        last_blue, last_orange = reg_goals[-1]["score"] if reg_goals else (0, 0)
        readings.append(HudReading(blue=last_blue, orange=last_orange, time=0))

    elif annotation["expected_end_type"] == "overtime":
        # Last regulation goal must be a tie; use its score for OT transition frames
        last_blue, last_orange = reg_goals[-1]["score"]

        # Frame at time=0 with equal scores -> sets _ot_pending
        readings.append(HudReading(blue=last_blue, orange=last_orange, time=0))
        # OVERTIME banner: scores readable, timer gone -> triggers OVERTIME state
        readings.append(HudReading(blue=last_blue, orange=last_orange, time=None))

        if ot_goals:
            for goal in ot_goals:
                blue, orange = goal["score"]
                readings.append(HudReading(blue=blue, orange=orange,
                                           time=goal["time_seconds"]))
        else:
            # No OT goal in annotation — synthesise one for the expected winner
            gs_win = _gs_winner(annotation)
            if gs_win == "blue":
                readings.append(HudReading(blue=last_blue + 1, orange=last_orange, time=10))
            else:
                readings.append(HudReading(blue=last_blue, orange=last_orange + 1, time=10))

    # 3 all-None frames to trigger the game-end callback
    for _ in range(3):
        readings.append(HudReading(blue=None, orange=None, time=None))

    return readings


# ── test ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("session_name", SESSIONS)
def test_e2e_game(session_name: str) -> None:
    annotation = json.loads(
        (SESSION_DIR / session_name / "annotation.json").read_text()
    )
    readings = _build_readings(annotation)

    captured: list[tuple[list[GoalEvent], str, str, int, str | None]] = []

    def on_game_over(goals: list[GoalEvent], end_type: str, colour_on_left: str, game_end_time: int = 0, winner: str | None = None) -> None:
        captured.append((goals, end_type, colour_on_left, game_end_time, winner))

    GameTracker(on_game_over=on_game_over).replay(readings)

    # Callback must fire exactly once
    assert len(captured) == 1, "on_game_over callback never fired (or fired multiple times)"
    goals, end_type, colour_on_left, game_end_time, winner = captured[0]

    assert end_type == annotation["expected_end_type"], \
        f"expected end_type {annotation['expected_end_type']!r}, got {end_type!r}"

    if end_type == "overtime":
        assert any(g.game_time > GAME_DURATION for g in goals), \
            "expected at least one OT goal (game_time > GAME_DURATION)"

    elif end_type == "normal":
        assert all(g.game_time <= GAME_DURATION for g in goals), \
            "all goals should be within regulation time"
        assert goals[-1].team == _gs_winner(annotation), \
            f"last goal should be scored by the winner ({_gs_winner(annotation)!r})"

    elif end_type == "forfeit":
        pass  # callback fired — that's sufficient

    # Save scoreworm for visual inspection (no assertion on image content)
    out_dir = Path("tests/output/scoreworms")
    out_dir.mkdir(parents=True, exist_ok=True)
    img = scoreworm.generate(goals, end_type=end_type,
                             colour_on_left=annotation["colour_on_left"])
    img.save(str(out_dir / f"{session_name}.png"))
