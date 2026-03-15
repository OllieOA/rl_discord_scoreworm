"""Generates the score worm chart image from a completed game's goal list."""

import io

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from PIL import Image

from game_state import GoalEvent

GAME_DURATION = 300   # seconds (5:00)

# Colours
_BLUE_FILL      = "#4A90D9"
_BLUE_LINE      = "#1A5FA8"
_ORANGE_FILL    = "#E8821A"
_ORANGE_LINE    = "#C45E00"
_ZERO_LINE      = "#888888"
_BACKGROUND     = "#1A1A2E"
_TEXT           = "#E0E0E0"
_GRID           = "#2E2E4E"
_OT_HATCH_COLOUR = "#CC2222"


def _build_steps(
    goals: list[GoalEvent],
    end_type: str = "normal",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert a list of GoalEvents into explicit step-function coordinates.
    The line is flat between goals, then jumps vertically at each goal time.
    """
    if end_type == "forfeit":
        x_end = goals[-1].game_time if goals else 0
    elif end_type == "overtime":
        x_end = max(g.game_time for g in goals) if goals else GAME_DURATION
    else:  # "normal"
        x_end = GAME_DURATION

    xs = [0]
    ys = [0]
    y = 0

    for goal in sorted(goals, key=lambda g: g.game_time):
        xs.append(goal.game_time)   # hold previous y up to this point
        ys.append(y)
        y += 1 if goal.team == "blue" else -1
        xs.append(goal.game_time)   # vertical jump
        ys.append(y)

    xs.append(x_end)               # hold final score to end of game
    ys.append(y)

    return np.array(xs, dtype=float), np.array(ys, dtype=float)


def _fmt_time(seconds: float, _pos=None) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def generate(
    goals: list[GoalEvent],
    end_type: str = "normal",
    colour_on_left: str = "blue",
) -> Image.Image:
    """
    Generate the score worm chart and return it as a PIL Image.

    The image can be posted directly to Discord via discord.py's File API
    by wrapping it in an io.BytesIO buffer.

    end_type:       "normal", "forfeit", or "overtime"
    colour_on_left: "blue" or "orange" — which team is shown on the left of
                    the HUD (and therefore tracked as "blue" in GoalEvent).
                    Controls fill/line colours and axis labels.
    """
    xs, ys = _build_steps(goals, end_type)

    # ── colour/label mapping — depends on which team is on the left ───────────
    # game_state always labels the left-side score "blue" and right-side "orange".
    # When the player is actually Orange, the positive y-direction and top fills
    # belong to Orange, not Blue.
    if colour_on_left == "orange":
        left_fill, left_line, left_name  = _ORANGE_FILL, _ORANGE_LINE, "Orange"
        right_fill, right_line, right_name = _BLUE_FILL, _BLUE_LINE, "Blue"
    else:
        left_fill, left_line, left_name  = _BLUE_FILL, _BLUE_LINE, "Blue"
        right_fill, right_line, right_name = _ORANGE_FILL, _ORANGE_LINE, "Orange"

    # ── figure setup ─────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 4), facecolor=_BACKGROUND)
    ax.set_facecolor(_BACKGROUND)

    # ── overtime region (drawn before the score line so it sits behind) ──────
    if end_type == "overtime":
        x_max = max(g.game_time for g in goals) if goals else GAME_DURATION
        ax.axvspan(
            GAME_DURATION, x_max,
            facecolor=_OT_HATCH_COLOUR, alpha=0.07,
            hatch="////", edgecolor=_OT_HATCH_COLOUR, linewidth=0,
            zorder=1,
        )
        ax.axvline(GAME_DURATION, color=_OT_HATCH_COLOUR, linewidth=1,
                   linestyle="--", alpha=0.6, zorder=2)
        ax.text(
            (GAME_DURATION + x_max) / 2, 0,
            "Overtime", color=_OT_HATCH_COLOUR, alpha=0.5,
            ha="center", va="center", fontsize=8, rotation=90,
            zorder=2,
        )

    # ── zero baseline ────────────────────────────────────────────────────────
    ax.axhline(0, color=_ZERO_LINE, linewidth=1, zorder=1)

    # ── colour fills ─────────────────────────────────────────────────────────
    ax.fill_between(xs, ys, 0, where=(ys > 0),
                    color=left_fill, alpha=0.4, step=None, zorder=2)
    ax.fill_between(xs, ys, 0, where=(ys < 0),
                    color=right_fill, alpha=0.4, step=None, zorder=2)

    # ── score line ───────────────────────────────────────────────────────────
    # Draw each segment in the colour of whichever team is leading
    for i in range(len(xs) - 1):
        y_seg = ys[i]
        colour = left_line if y_seg > 0 else (right_line if y_seg < 0 else _ZERO_LINE)
        ax.plot(xs[i:i+2], ys[i:i+2], color=colour, linewidth=2.5, zorder=3, solid_capstyle="round")

    # ── goal markers — dot at the post-jump y value ──────────────────────────
    y_running = 0
    for goal in sorted(goals, key=lambda g: g.game_time):
        y_running += 1 if goal.team == "blue" else -1
        colour = left_line if goal.team == "blue" else right_line
        ax.scatter(goal.game_time, y_running, color=colour, s=50, zorder=4)

    # ── axes ─────────────────────────────────────────────────────────────────
    if end_type == "overtime":
        x_max = max(g.game_time for g in goals) if goals else GAME_DURATION
        pad = (x_max - GAME_DURATION) * 0.05 + 5
        ax.set_xlim(0, x_max + pad)
        all_ticks = sorted(set(range(0, int(x_max) + 60, 60)) | {GAME_DURATION})
        ax.xaxis.set_major_locator(ticker.FixedLocator(all_ticks))
    else:
        ax.set_xlim(0, GAME_DURATION)
        ax.xaxis.set_major_locator(ticker.MultipleLocator(60))

    y_max = max(abs(ys).max(), 1)
    ax.set_ylim(-y_max - 0.5, y_max + 0.5)

    ax.xaxis.set_major_formatter(ticker.FuncFormatter(_fmt_time))
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    ax.tick_params(colors=_TEXT, labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)

    ax.grid(axis="y", color=_GRID, linewidth=0.5, zorder=0)

    # ── labels ───────────────────────────────────────────────────────────────
    ax.set_xlabel("Match time", color=_TEXT, fontsize=10)
    ax.set_ylabel(f"{left_name} \u2212 {right_name}", color=_TEXT, fontsize=10)

    left_goals  = sum(1 for g in goals if g.team == "blue")
    right_goals = sum(1 for g in goals if g.team == "orange")
    ax.set_title(
        f"Score Worm  \u2014  {left_name} {left_goals} : {right_goals} {right_name}",
        color=_TEXT, fontsize=12, pad=10,
    )

    plt.tight_layout()

    # ── render to PIL Image ───────────────────────────────────────────────────
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=_BACKGROUND)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).copy()


if __name__ == "__main__":
    # Normal game
    test_goals_normal = [
        GoalEvent("blue",   GAME_DURATION - 45,  45),
        GoalEvent("orange", GAME_DURATION - 90,  90),
        GoalEvent("orange", GAME_DURATION - 140, 140),
        GoalEvent("blue",   GAME_DURATION - 200, 200),
        GoalEvent("blue",   GAME_DURATION - 260, 260),
    ]
    generate(test_goals_normal, end_type="normal").save("scoreworm_preview.png")
    print("Saved scoreworm_preview.png (normal)")

    # Overtime game — same goals, ends in OT goal
    test_goals_ot = [
        GoalEvent("blue",   GAME_DURATION - 45,  45),
        GoalEvent("orange", GAME_DURATION - 90,  90),
        GoalEvent("orange", GAME_DURATION - 140, 140),
        GoalEvent("blue",   GAME_DURATION - 200, 200),
        GoalEvent("blue",   0,                   GAME_DURATION + 40),
    ]
    generate(test_goals_ot, end_type="overtime").save("scoreworm_preview_ot.png")
    print("Saved scoreworm_preview_ot.png (overtime)")

    # Forfeit — game ended early
    test_goals_forfeit = [
        GoalEvent("blue",   GAME_DURATION - 45,  45),
        GoalEvent("orange", GAME_DURATION - 90,  90),
        GoalEvent("orange", GAME_DURATION - 140, 140),
    ]
    generate(test_goals_forfeit, end_type="forfeit").save("scoreworm_preview_forfeit.png")
    print("Saved scoreworm_preview_forfeit.png (forfeit)")
