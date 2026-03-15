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

## Coding conventions

- Use `->` not `→` in Python source (print statements, f-strings, comments). The Windows terminal encoding (cp1252) cannot encode `→`, causing `UnicodeEncodeError` at runtime.

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
uv run python main.py                # run the bot (main entry point)
uv run python game_state.py          # run tracker only (no Discord), prints goal events
uv run python scoreworm.py           # render a test chart → scoreworm_preview.png
uv run python capture.py             # save a HUD screenshot → hud_preview.png

# Template capture workflow (do in-game, one session per side)
uv run python record_session.py                          # record full-screen frames → sessions/<timestamp>/
uv run python extract_session_templates.py sessions/left_count_up   # extract snippets + raw crops
uv run python extract_session_templates.py sessions/right_count_up
uv run python process_templates.py                       # build score templates from raw crops

# Timer templates (rebuilt from session snippets)
uv run python rebuild_timer_templates.py --overwrite

# Tests — default uses 24 workers (3/4 of CPUs, preserving system headroom)
uv run pytest                                # all tests, quiet output
uv run pytest tests/test_ocr.py             # specific file

# When iterating on a specific failure, target it directly first, then run
# the full suite to confirm no regressions:
uv run pytest tests/test_ocr.py -k "game_start"          # single test by keyword
uv run pytest "tests/test_ocr.py::test_snippet_timer[game_start.0-0_5-00_orange.png]"  # exact parametrize ID
uv run pytest tests/test_ocr.py             # full suite after fixing
```

## Architecture

```
capture.py → ocr.py → game_state.py → scoreworm.py → bot.py
```

| Module | Responsibility |
|--------|----------------|
| `capture.py` | Grabs the HUD region from the centre monitor. Auto-detects the centre screen from a 3-monitor setup by sorting monitors by left-edge position. HUD region: left=1040, top=0, width=480, height=110 (tuned for 2560×1440). |
| `ocr.py` | Template-matching OCR. Preprocesses frames (greyscale → binarise → 4× upscale → dilate). Tries multiple binarisation thresholds per frame (110/128/150/170/190) and accepts the highest-confidence result — compensates for HUD transparency shifts and the orange panel in overtime. Timer uses **positional zones** on the full timer strip (minute x<380, tens 380–580, ones ≥580 in 4× space); regular-time reads are gated on a colon template match to reject the "OVERTIME" text frame. Scores use per-value template matching (0–99 per side). Returns `HudReading(blue, orange, time)` — fields are `None` if unreadable. |
| `game_state.py` | Polls capture+OCR every 0.5s. State machine: `IDLE → IN_GAME → OVERTIME → (callback) → IDLE`. Logs every probe result and saves the last 50 frames to `logs/`. Fires `on_game_over(goals: list[GoalEvent])` when a game ends. |
| `scoreworm.py` | Takes a list of `GoalEvent` and returns a PIL Image of the score worm chart. Pure function — no I/O side effects. |
| `bot.py` | Logs into Discord, starts `GameTracker` in a background thread. Uses `asyncio.run_coroutine_threadsafe` to post the image when `on_game_over` fires. |
| `record_session.py` | Records full-screen captures to `sessions/<timestamp>/` at a configurable interval (default 1s). Used to capture template source material in-game. |
| `extract_session_templates.py` | Processes a `sessions/` directory (one file per score, sorted numerically). Saves raw HUD crops to `templates/raw/` and labelled HUD strips to `tests/fixtures/snippet/`. Side is inferred from directory name (`left`/`right`). |
| `process_templates.py` | Converts `templates/raw/capture_N_{side}.png` files into preprocessed score templates in `templates/score/`. Preprocessing must match `ocr.py` exactly. |
| `rebuild_timer_templates.py` | Rebuilds `templates/timer/` from session-style snippet fixtures. |

### Template system

Templates are preprocessed (binarised, 4× scaled, dilated) PNG crops that must match `ocr.py`'s preprocessing exactly (`SCALE=4`, `THRESHOLD=128`, `DILATE_K=4`, `DILATE_I=2`).

| Directory | Contents | How generated |
|-----------|----------|---------------|
| `templates/score/` | `0_left.png`–`99_left.png`, `0_right.png`–`99_right.png` — one per score value per side (200 total) | `process_templates.py` (from `templates/raw/`) |
| `templates/timer/` | `0.png`–`9.png` + `colon.png` | `rebuild_timer_templates.py` (from session snippets) |
| `templates/raw/` | Full raw HUD strips from session recordings, named `capture_{score}_{side}.png` | `extract_session_templates.py` |

### Session workflow

Sessions are recorded in-game with `record_session.py` (one frame per second). After recording, the directory is manually curated: one file per score event, sorted numerically (file at index `i` → score `i`). Then `extract_session_templates.py` processes the directory.

Existing curated sessions:

| Directory | Side | Scores covered |
|-----------|------|----------------|
| `sessions/left_count_up` | left (blue) | blue 0–99, orange 0 |
| `sessions/right_count_up` | right (orange) | blue 0, orange 0–99 |
| `sessions/double_digits` | — | double-digit captures |
| `sessions/full_tournament` | — | full tournament recording |

### HUD sub-regions (within the 480×110 crop)

| Region | X range | Content |
|--------|---------|---------|
| `BLUE_X` | 0 – 110 | Left team score |
| `TIMER_X` | 110 – 370 | Match timer |
| `ORANGE_X` | 370 – 480 | Right team score |

> **Note:** In RL, the local player's team is always shown on the left. If the player is on Orange, Orange appears on the left (`BLUE_X` region). Team-side detection is not yet implemented.

### Test fixtures

`tests/fixtures/snippet/` contains labelled HUD strip PNGs. Filename format:

```
[desc].[left_score]-[right_score]_[min]-[sec]_[colour].png
```

`colour` is the team shown on the **left** side of the HUD. `n` in any position means not applicable / unreadable.

**These files are protected** — do not rename or delete them without prompting the user to manually verify the correct label. If a test fails, report it and ask the user to inspect the image.

### Known issues / TODOs

- **OCR speed** — `read_hud` now runs 5 threshold images per call (timer: ~70 matchTemplate ops; scores: 5 matmuls). Still well within the 0.5s polling interval. Further optimisation possible if needed.
- Team-side detection not implemented — left score always assumed to be Blue
- Scores > 99 return None (acceptable)
- `capture_templates.py` is legacy — prefer `record_session.py` + `extract_session_templates.py`
- 1 xfail: `count_up.10-95_1-13_orange` — '9' template outscores '3' at the ones position; needs '9' template rebuilt from a less ambiguous source
