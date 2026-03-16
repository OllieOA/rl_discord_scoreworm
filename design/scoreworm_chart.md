# Score Worm Chart Design

## Visual spec

A horizontal step-chart showing how the scoreline evolved over the match.

- **X-axis:** match time (axis hidden, no labels shown)
- **Y-axis:** score differential (Left − Right), shown as absolute values with
  colour-coded team labels
- The line steps **up** each time the left-side team scores, **down** for right-side
- The local player is always on the left (top of chart)
- **Regulation background:** alternating dark/light navy bands per minute
- **Overtime extension:** chart extends past 5:00 with alternating dark/light red bands
  per OT minute
- **End marker:** gold ★ (win) or red ✗ (loss/forfeit) at the game-end point
  — placed using Twemoji PNGs via `AnnotationBbox`; falls back to text if PNG missing
- **On forfeit:** worm stops at the last goal but the full 5:00 x-range is still shown

## Winner → end icon logic

`generate()` accepts an optional `winner` string ("blue"/"orange" = left/right position).
- If `winner` is provided: use it directly for the end icon
- If `winner` is None: fall back to `ys[-1]` goal-differential

## Goal annotations

`annotate_goals(goals)` returns per-goal emoji codepoints based on rules:
- 🇧🇷 Brazil 7-1 rule: blue scores to make it 7-1

`ANNOTATION_LEGEND` maps codepoint → Discord legend line (one legend entry per unique
annotation in the match, appended to the Discord message).

## Assets

Twemoji PNGs at 72×72 committed to `assets/emoji/`:
- `1f3c6.png` 🏆 — win
- `274c.png` ❌ — loss/forfeit
- `1f1e7-1f1f7.png` 🇧🇷 — Brazil 7-1

Add new ones with `uv run python tools/fetch_emoji.py <emoji>`.
