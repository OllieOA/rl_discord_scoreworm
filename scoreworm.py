"""Generates the score worm chart image from a completed game's goal list."""

import io

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from PIL import Image

from game_state import GoalEvent

GAME_DURATION = 300   # seconds (5:00)

# Colours
_BLUE_FILL   = "#4A90D9"
_BLUE_LINE   = "#1A5FA8"
_ORANGE_FILL = "#E8821A"
_ORANGE_LINE = "#C45E00"
_ZERO_LINE   = "#888888"
_BACKGROUND  = "#1A1A2E"
_TEXT        = "#E0E0E0"
_GRID        = "#2E2E4E"


def _build_steps(goals: list[GoalEvent]) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert a list of GoalEvents into explicit step-function coordinates.
    The line is flat between goals, then jumps vertically at each goal time.
    """
    xs = [0]
    ys = [0]
    y = 0

    for goal in sorted(goals, key=lambda g: g.game_time):
        xs.append(goal.game_time)   # hold previous y up to this point
        ys.append(y)
        y += 1 if goal.team == "blue" else -1
        xs.append(goal.game_time)   # vertical jump
        ys.append(y)

    xs.append(GAME_DURATION)        # hold final score to end of game
    ys.append(y)

    return np.array(xs, dtype=float), np.array(ys, dtype=float)


def _fmt_time(seconds: float, _pos=None) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def generate(goals: list[GoalEvent]) -> Image.Image:
    """
    Generate the score worm chart and return it as a PIL Image.

    The image can be posted directly to Discord via discord.py's File API
    by wrapping it in an io.BytesIO buffer.
    """
    xs, ys = _build_steps(goals)

    # ── figure setup ─────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 4), facecolor=_BACKGROUND)
    ax.set_facecolor(_BACKGROUND)

    # ── zero baseline ────────────────────────────────────────────────────────
    ax.axhline(0, color=_ZERO_LINE, linewidth=1, zorder=1)

    # ── colour fills ─────────────────────────────────────────────────────────
    ax.fill_between(xs, ys, 0, where=(ys > 0),
                    color=_BLUE_FILL, alpha=0.4, step=None, zorder=2)
    ax.fill_between(xs, ys, 0, where=(ys < 0),
                    color=_ORANGE_FILL, alpha=0.4, step=None, zorder=2)

    # ── score line ───────────────────────────────────────────────────────────
    # Draw each segment in the colour of whichever team is leading
    for i in range(len(xs) - 1):
        y_seg = ys[i]
        colour = _BLUE_LINE if y_seg > 0 else (_ORANGE_LINE if y_seg < 0 else _ZERO_LINE)
        ax.plot(xs[i:i+2], ys[i:i+2], color=colour, linewidth=2.5, zorder=3, solid_capstyle="round")

    # ── goal markers — dot at the post-jump y value ──────────────────────────
    y_running = 0
    for goal in sorted(goals, key=lambda g: g.game_time):
        y_running += 1 if goal.team == "blue" else -1
        colour = _BLUE_LINE if goal.team == "blue" else _ORANGE_LINE
        ax.scatter(goal.game_time, y_running, color=colour, s=50, zorder=4)

    # ── axes ─────────────────────────────────────────────────────────────────
    ax.set_xlim(0, GAME_DURATION)
    y_max = max(abs(ys).max(), 1)
    ax.set_ylim(-y_max - 0.5, y_max + 0.5)

    ax.xaxis.set_major_formatter(ticker.FuncFormatter(_fmt_time))
    ax.xaxis.set_major_locator(ticker.MultipleLocator(60))   # tick every minute
    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))

    ax.tick_params(colors=_TEXT, labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)

    ax.grid(axis="y", color=_GRID, linewidth=0.5, zorder=0)

    # ── labels ───────────────────────────────────────────────────────────────
    ax.set_xlabel("Match time", color=_TEXT, fontsize=10)
    ax.set_ylabel("Score (Blue − Orange)", color=_TEXT, fontsize=10)

    # Final score annotation
    blue_goals   = sum(1 for g in goals if g.team == "blue")
    orange_goals = sum(1 for g in goals if g.team == "orange")
    ax.set_title(f"Score Worm  —  Blue {blue_goals} : {orange_goals} Orange",
                 color=_TEXT, fontsize=12, pad=10)

    plt.tight_layout()

    # ── render to PIL Image ───────────────────────────────────────────────────
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=_BACKGROUND)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).copy()


if __name__ == "__main__":
    test_goals = [
        GoalEvent("blue",   GAME_DURATION - 45,  45),
        GoalEvent("orange", GAME_DURATION - 90,  90),
        GoalEvent("orange", GAME_DURATION - 140, 140),
        GoalEvent("blue",   GAME_DURATION - 200, 200),
        GoalEvent("blue",   GAME_DURATION - 260, 260),
    ]
    img = generate(test_goals)
    img.save("scoreworm_preview.png")
    print("Saved scoreworm_preview.png")
