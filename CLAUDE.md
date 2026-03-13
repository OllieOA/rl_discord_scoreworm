# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

**rl_discord_scoreworm** watches a live Rocket League match and automatically posts a score worm chart to Discord when the game ends.

A **score worm** is a horizontal step-chart showing how the scoreline evolved over the course of the match. The x-axis is match time (0:00 → 5:00), and the y-axis is the score differential (Blue − Orange). The line steps **up** each time Blue scores and **down** each time Orange scores. Blue territory (above zero) is filled blue, Orange territory (below zero) is filled orange.

### Detection logic
- **Game start:** OCR reads `0-0` on both scores and `5:00` on the timer simultaneously
- **Goal:** either team's score increments by 1 between consecutive frames
- **Normal-time end:** timer reaches `0:00` and scores are not level
- **Overtime:** timer reaches `0:00` with level scores → RL displays "OVERTIME" and the timer counts **up**; game ends when the next goal makes scores uneven
- **Scoreboard gone:** 3 consecutive frames where all OCR values are `None` (post-match scoreboard has replaced the HUD)

## Tooling

- **Package manager:** `uv` (installed at `C:\Users\Ollie\.local\bin\uv.exe`) — use `uv run` or activate `.venv` first
- **Screen capture:** `mss` — uses Desktop Duplication API, works with fullscreen games
- **OCR:** template matching via `opencv-python` (Tesseract was tried and abandoned — RL uses a custom font)
- **Chart:** `matplotlib` + `Pillow`
- **Discord bot:** `discord.py` 2.x
- **Config:** `.env` file (copy from `.env.example`) with `DISCORD_TOKEN` and `DISCORD_CHANNEL_ID`
- **Python:** 3.12.1, venv at `.venv/`

## Common Commands

```bash
uv sync                              # install dependencies
uv run python bot.py                 # run the bot (main entry point)
uv run python game_state.py          # run tracker only (no Discord)
uv run python scoreworm.py           # render a test chart → scoreworm_preview.png
uv run python capture.py             # save a HUD screenshot → hud_preview.png

# Template capture (score digits — do incrementally, one goal per 20s)
uv run python capture_templates.py --count 9
uv run python capture_templates.py --from-raw   # reprocess without going in-game

# Template extraction (timer digits — from timer_raw captures)
uv run python extract_timer_templates.py

# Tests
uv run pytest
uv run pytest tests/test_ocr.py -v
```

## Architecture

```
capture.py → ocr.py → game_state.py → scoreworm.py → bot.py
```

| Module | Responsibility |
|--------|----------------|
| `capture.py` | Grabs the HUD region from the centre monitor. Auto-detects the centre screen from a 3-monitor setup by sorting monitors by left-edge position. HUD region: left=1040, top=0, width=480, height=110 (tuned for 2560×1440). |
| `ocr.py` | Template-matching OCR. Preprocesses frames (greyscale → binarise at 128 → 4× upscale → dilate). Timer uses **fixed character slots** for M, :, S1, S2 (sliding window was unreliable with this font). Scores use sliding window + NMS. Returns `HudReading(blue, orange, time)` — fields are `None` if unreadable. |
| `game_state.py` | Polls capture+OCR every 0.5s. State machine: `IDLE → IN_GAME → OVERTIME → (callback) → IDLE`. Logs every probe result and saves the last 50 frames to `logs/`. Fires `on_game_over(goals: list[GoalEvent])` when a game ends. |
| `scoreworm.py` | Takes a list of `GoalEvent` and returns a PIL Image of the score worm chart. Pure function — no I/O side effects. |
| `bot.py` | Logs into Discord, starts `GameTracker` in a background thread. Uses `asyncio.run_coroutine_threadsafe` to post the image when `on_game_over` fires. |

### Template system

Templates are stored as preprocessed (binarised, 4× scaled, dilated) PNG crops:

| Directory | Contents | How generated |
|-----------|----------|---------------|
| `templates/score/` | `0.png` – `9.png` — score digit templates | `capture_templates.py` (live, incremental goals) |
| `templates/timer/` | `0.png` – `9.png` + `colon.png` | `extract_timer_templates.py` (from timer_raw captures) |
| `templates/raw/` | Full raw HUD frames from score capture sessions | Saved automatically by `capture_templates.py` |
| `templates/timer_raw/` | Full preprocessed timer strips | Saved by `capture_templates.py` (legacy) |

**Critical:** preprocessing in `capture_templates.py` and `ocr.py` must use identical parameters (`SCALE=4`, `THRESHOLD=128`, `DILATE_K=4`, `DILATE_I=2`) or templates won't match.

### HUD sub-regions (within the 480×110 crop)

| Region | X range | Content |
|--------|---------|---------|
| `BLUE_X` | 0 – 110 | Left team score |
| `TIMER_X` | 110 – 370 | Match timer |
| `ORANGE_X` | 370 – 480 | Right team score |

> **Note:** In RL, the local player's team is always shown on the left. If the player is on Orange, Orange appears on the left (`BLUE_X` region). Team-side detection is not yet implemented.

### Known issues / TODOs
- Score templates need recapturing (`templates/score/` was accidentally overwritten)
- Team-side detection not implemented: currently assumes the left score is always Blue
- Game-end detection via scoreboard disappearance (3× None) may need tuning
