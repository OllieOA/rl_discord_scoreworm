"""Generates the score worm chart image from a completed game's goal list."""

import io
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — required when called from a non-main thread
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
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
_BAND_REG_DARK  = "#1A1A2E"   # same as _BACKGROUND — seamless with dark minutes
_BAND_REG_LIGHT = "#222240"   # subtly lighter navy
_BAND_OT_DARK   = "#1F0808"   # deep dark red
_BAND_OT_LIGHT  = "#2E1010"   # slightly lighter dark red

_EMOJI_DIR = Path(__file__).parent / "assets" / "emoji"
_EMOJI_ZOOM = 0.42   # 72px source -> ~30px rendered at 150 DPI


def _load_emoji(codepoint: str) -> OffsetImage | None:
    """Load a Twemoji PNG as an OffsetImage; returns None if the file is absent."""
    path = _EMOJI_DIR / f"{codepoint}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    return OffsetImage(np.array(img), zoom=_EMOJI_ZOOM)


def _place_emoji(ax, codepoint: str, x: float, y: float, fallback_text: str = "",
                 fallback_color: str = "#FFFFFF") -> None:
    """Place an emoji PNG at data coordinates, falling back to a text symbol."""
    img_obj = _load_emoji(codepoint)
    if img_obj is not None:
        ax.add_artist(AnnotationBbox(img_obj, (x, y), frameon=False, zorder=5))
    elif fallback_text:
        ax.text(x, y, fallback_text, fontsize=22, color=fallback_color,
                ha="center", va="center", fontweight="bold", zorder=5)


# Legend text for goal annotations displayed in the Discord post.
# Maps codepoint -> label shown under the title when that annotation appears.
# Add an entry here whenever a new annotation rule is added below.
ANNOTATION_LEGEND: dict[str, str] = {
    "1f1e7-1f1f7": "\U0001f1e7\U0001f1f7 - Brazil 7-1",   # 🇧🇷
}


def annotate_goals(goals: list[GoalEvent]) -> dict[int, str]:
    """Return a mapping of goal_index (in game_time order) -> emoji codepoint.

    Rules are evaluated in priority order; first match wins per goal.

    Current rules:
      Brazil — the single goal that brings the scoreline to exactly 7-1 in
               either direction gets the Brazilian flag emoji.
    """
    annotations: dict[int, str] = {}
    blue = orange = 0
    for i, goal in enumerate(sorted(goals, key=lambda g: g.game_time)):
        if goal.team == "blue":
            blue += 1
        else:
            orange += 1
        if (blue == 7 and orange == 1) or (blue == 1 and orange == 7):
            annotations[i] = "1f1e7-1f1f7"   # 🇧🇷
    return annotations


def _build_steps(
    goals: list[GoalEvent],
    end_type: str = "normal",
    forfeit_time: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Convert a list of GoalEvents into explicit step-function coordinates.
    The line is flat between goals, then jumps vertically at each goal time.
    """
    if end_type == "forfeit":
        x_end = forfeit_time if forfeit_time else (goals[-1].game_time if goals else 0)
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


def generate(
    goals: list[GoalEvent],
    end_type: str = "normal",
    colour_on_left: str = "blue",
    forfeit_time: int = 0,
    winner: str | None = None,
) -> Image.Image:
    """
    Generate the score worm chart and return it as a PIL Image.

    The image can be posted directly to Discord via discord.py's File API
    by wrapping it in an io.BytesIO buffer.

    end_type:       "normal", "forfeit", or "overtime"
    colour_on_left: "blue" or "orange" — which team is shown on the left of
                    the HUD (and therefore tracked as "blue" in GoalEvent).
                    Controls fill/line colours and axis labels.
    winner:         "blue" (left side won) or "orange" (right side won), or
                    None to fall back to ys[-1] goal-differential logic.
    """
    xs, ys = _build_steps(goals, end_type, forfeit_time)

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

    # ── end icon — computed before drawing ───────────────────────────────────
    if winner is not None:
        end_icon = "win" if winner == "blue" else "loss"
    else:
        final_y = ys[-1]
        if final_y > 0:
            end_icon = "win"
        elif final_y < 0:
            end_icon = "loss"
        else:
            end_icon = None

    # ── figure setup ─────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(10, 4), facecolor=_BACKGROUND)
    ax.set_facecolor(_BACKGROUND)

    # ── regulation minute bands (drawn first, lowest zorder) ─────────────────
    minute_edges = list(range(0, GAME_DURATION + 1, 60))
    for i, (x0, x1) in enumerate(zip(minute_edges, minute_edges[1:])):
        colour = _BAND_REG_LIGHT if i % 2 else _BAND_REG_DARK
        ax.axvspan(x0, x1, facecolor=colour, alpha=1.0, zorder=0, linewidth=0)

    # ── overtime bands (replaces old hatched axvspan + axvline + text) ────────
    if end_type == "overtime":
        x_ot_end = max(g.game_time for g in goals) if goals else GAME_DURATION
        ot_end_ceil = ((int(x_ot_end) - GAME_DURATION) // 60 + 1) * 60 + GAME_DURATION
        ot_edges = list(range(GAME_DURATION, ot_end_ceil + 1, 60))
        for i, (x0, x1) in enumerate(zip(ot_edges, ot_edges[1:])):
            colour = _BAND_OT_LIGHT if i % 2 else _BAND_OT_DARK
            ax.axvspan(x0, x1, facecolor=colour, alpha=1.0, zorder=0, linewidth=0)

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

    # ── goal annotations (Brazil etc.) ───────────────────────────────────────
    sorted_goals = sorted(goals, key=lambda g: g.game_time)
    goal_annotations = annotate_goals(sorted_goals)
    y_running = 0
    for i, goal in enumerate(sorted_goals):
        y_running += 1 if goal.team == "blue" else -1
        if i in goal_annotations:
            _place_emoji(ax, goal_annotations[i], goal.game_time, y_running)

    # ── end icon — placed at the worm tip (xs[-1], ys[-1]) ───────────────────
    if end_icon == "win":
        _place_emoji(ax, "1f3c6", xs[-1], ys[-1],
                     fallback_text="\u2605", fallback_color="#FFD700")   # ★
    elif end_icon == "loss":
        _place_emoji(ax, "274c", xs[-1], ys[-1],
                     fallback_text="\u2717", fallback_color="#FF4444")   # ✗

    # ── axes ─────────────────────────────────────────────────────────────────
    if end_type == "overtime":
        x_max = max(g.game_time for g in goals) if goals else GAME_DURATION
        pad = (x_max - GAME_DURATION) * 0.05 + 5
        ax.set_xlim(0, x_max + pad)
    else:
        ax.set_xlim(0, GAME_DURATION)

    y_max = max(abs(ys).max(), 1)
    ax.set_ylim(-y_max - 0.5, y_max + 0.5)

    ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda y, _: str(abs(int(y)))))

    ax.xaxis.set_visible(False)
    ax.spines["bottom"].set_visible(False)

    ax.tick_params(colors=_TEXT, labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)

    ax.grid(axis="y", color=_GRID, linewidth=0.5, zorder=0)

    # ── labels ───────────────────────────────────────────────────────────────
    # Place colour-coded team labels on the y-axis: left team above zero, right below
    ax.text(-0.045, 0.75, left_name, transform=ax.transAxes,
            color=left_fill, fontsize=10, fontweight="bold",
            ha="right", va="center")
    ax.text(-0.045, 0.25, right_name, transform=ax.transAxes,
            color=right_fill, fontsize=10, fontweight="bold",
            ha="right", va="center")

    plt.tight_layout()

    # ── render to PIL Image ───────────────────────────────────────────────────
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, facecolor=_BACKGROUND)
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).copy()


if __name__ == "__main__":
    import os
    os.makedirs("tests/output", exist_ok=True)

    # Normal game
    test_goals_normal = [
        GoalEvent("blue",   GAME_DURATION - 45,  45),
        GoalEvent("orange", GAME_DURATION - 90,  90),
        GoalEvent("orange", GAME_DURATION - 140, 140),
        GoalEvent("blue",   GAME_DURATION - 200, 200),
        GoalEvent("blue",   GAME_DURATION - 260, 260),
    ]
    generate(test_goals_normal, end_type="normal").save("tests/output/scoreworm_preview.png")
    print("Saved tests/output/scoreworm_preview.png (normal)")

    # Overtime game — same goals, ends in OT goal
    test_goals_ot = [
        GoalEvent("blue",   GAME_DURATION - 45,  45),
        GoalEvent("orange", GAME_DURATION - 90,  90),
        GoalEvent("orange", GAME_DURATION - 140, 140),
        GoalEvent("blue",   GAME_DURATION - 200, 200),
        GoalEvent("blue",   0,                   GAME_DURATION + 40),
    ]
    generate(test_goals_ot, end_type="overtime").save("tests/output/scoreworm_preview_ot.png")
    print("Saved tests/output/scoreworm_preview_ot.png (overtime)")

    # Forfeit — game ended early
    test_goals_forfeit = [
        GoalEvent("blue",   GAME_DURATION - 45,  45),
        GoalEvent("orange", GAME_DURATION - 90,  90),
        GoalEvent("orange", GAME_DURATION - 140, 140),
    ]
    generate(test_goals_forfeit, end_type="forfeit").save("tests/output/scoreworm_preview_forfeit.png")
    print("Saved tests/output/scoreworm_preview_forfeit.png (forfeit)")

    # Brazil — 7-1 scoreline (blue scores 7th while orange has 1)
    test_goals_brazil = (
        [GoalEvent("orange", GAME_DURATION - 10, 10)] +
        [GoalEvent("blue",   GAME_DURATION - (20 + i * 25), 20 + i * 25) for i in range(7)]
    )
    generate(test_goals_brazil, end_type="normal").save("tests/output/scoreworm_preview_brazil.png")
    print("Saved tests/output/scoreworm_preview_brazil.png (brazil)")
