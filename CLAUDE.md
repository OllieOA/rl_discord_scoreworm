# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

**rl_discord_scoreworm** watches a live Rocket League match and automatically posts a score worm chart to Discord when the game ends.

A **score worm** is a horizontal step-chart showing how the scoreline evolved over the course of the match. The x-axis is match time (no labels shown — axis hidden). The y-axis is the score differential (Left − Right, shown as absolute values with colour-coded team labels): the line steps **up** each time the left-side team scores and **down** each time the right-side team scores. The local player is always on the left (top of chart). Regulation background uses alternating dark/light navy bands per minute. In overtime the chart extends past 5:00 with alternating dark/light red bands per OT minute. A gold ★ or red ✗ marks the game-end point. On forfeit the worm stops at the last goal but the full 5:00 x-range is still shown.

### Detection logic
- **Game start:** OCR reads `0-0` on both scores and `5:00` on the timer simultaneously
- **Goal:** either team's score increments by 1 between consecutive frames
- **Corrupt read:** score decreases or jumps by >1 → frame discarded, `prev` unchanged
- **OT-pending:** timer `0:00` with level scores sets `_ot_pending`; first frame where scores are readable but timer is `None` (OVERTIME banner) → transition to OVERTIME state
- **Forfeit:** game ends without reaching `0:00` (opponent leaves)
- **Game end (all cases):** 3 consecutive all-`None` frames — post-match scoreboard replaced the HUD

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
run_bot.bat                          # run the bot (main entry point)
uv run python main.py                # equivalent — run directly if needed
uv run python game_state.py          # run tracker only (no Discord), prints goal events
uv run python scoreworm.py           # render a test chart → scoreworm_preview.png
uv run python capture.py             # save a HUD screenshot → hud_preview.png

# Template capture workflow (do in-game, one session per side)
uv run python tools/record_session.py                          # record full-screen frames → sessions/<timestamp>/
uv run python tools/extract_session_templates.py sessions/left_count_up   # extract snippets + raw crops
uv run python tools/extract_session_templates.py sessions/right_count_up
uv run python tools/process_templates.py                       # build score templates from raw crops

# Timer templates (rebuilt from session snippets)
uv run python tools/rebuild_timer_templates.py --overwrite

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
| `ocr.py` | Template-matching OCR. Preprocesses frames (greyscale → binarise → 4× upscale → dilate). **Scores** try 5 binarisation thresholds (110/128/150/170/190) and accept the highest-confidence batched NCC result — thresholds ≥170 reject the overtime orange panel background (greyscale ≈158) without a separate code path. **Timer** uses a single threshold (128) with sliding `cv2.matchTemplate` across positional zones (minute x<380, tens 380–580, ones ≥580 in 4× space); regular-time reads are gated on a colon template match (≥0.65) to reject the "OVERTIME" text frame; overtime reads (`+` template detected at ≥0.75) parse `+M:SS` or `+MM:SS`. Returns `HudReading(blue, orange, time)` — fields are `None` if unreadable. ~165ms/call. |
| `game_state.py` | Polls capture+OCR every 0.5s. State machine: `IDLE → IN_GAME → OVERTIME → (callback) → IDLE`. Corrupt-read guard discards impossible score transitions. OT-pending flag defers OVERTIME transition until the banner frame. On each all-None frame, grabs the full screen and calls `detect_winner()`; stores the first non-None result in `_detected_winner`. Fires `on_game_over(goals, end_type, colour_on_left, game_end_time, winner)` when 3 consecutive all-None frames are detected. Also exposes `replay(readings)` for testing. |
| `scoreworm.py` | Takes a list of `GoalEvent`, `end_type`, and optional `winner` string, returns a PIL Image. Uses `winner` for the end icon when provided; falls back to `ys[-1]` goal-differential otherwise. `annotate_goals(goals)` (public) returns per-goal codepoints; `ANNOTATION_LEGEND` maps codepoint → Discord legend line. End icons (🏆/❌) and goal annotations (🇧🇷 at 7-1) are placed as Twemoji PNGs via `AnnotationBbox`; falls back to text if PNG missing. Worm stops at last goal on forfeit; extends past 5:00 with red OT bands. Pure function — no I/O side effects. |
| `bot.py` | Logs into Discord, starts `GameTracker` in a background thread. Uses `asyncio.run_coroutine_threadsafe` to post the image when `on_game_over` fires. Builds Discord message as header + optional legend lines (one per unique special goal annotation, e.g. `🇧🇷 - Brazil 7-1`). |
| `tools/record_session.py` | Records full-screen captures to `sessions/<timestamp>/` at a configurable interval (default 1s). Used to capture template source material in-game. |
| `tools/extract_session_templates.py` | Processes a `sessions/` directory (one file per score, sorted numerically). Saves raw HUD crops to `templates/raw/` and labelled HUD strips to `tests/fixtures/snippet/`. Side is inferred from directory name (`left`/`right`). |
| `tools/process_templates.py` | Converts `templates/raw/capture_N_{side}.png` files into preprocessed score templates in `templates/score/`. Preprocessing must match `ocr.py` exactly. |
| `tools/rebuild_timer_templates.py` | Rebuilds `templates/timer/` from session-style snippet fixtures. |
| `tools/annotate_sessions.py` | Runs OCR over full-game session recordings and writes `annotation.json` into each session folder. |
| `tools/fetch_emoji.py` | Downloads Twemoji PNG assets by emoji char or codepoint into `assets/emoji/`. Usage: `uv run python tools/fetch_emoji.py 🏆 ❌ 🇧🇷` |

### Template system

Templates are preprocessed (binarised, 4× scaled, dilated) PNG crops that must match `ocr.py`'s preprocessing exactly (`SCALE=4`, `THRESHOLD=128`, `DILATE_K=4`, `DILATE_I=2`).

| Directory | Contents | How generated |
|-----------|----------|---------------|
| `templates/score/` | `0_left.png`–`99_left.png`, `0_right.png`–`99_right.png` — one per score value per side (200 total) | `tools/process_templates.py` (from `templates/raw/`) |
| `templates/timer/` | `0.png`–`9.png` + `colon.png` + `plus.png` | `tools/rebuild_timer_templates.py` (digits/colon from session snippets); `plus.png` extracted manually via connected-components from the `+3:40` overtime fixture |
| `templates/raw/` | Full raw HUD strips from session recordings, named `capture_{score}_{side}.png` | `tools/extract_session_templates.py` |
| `assets/emoji/` | Twemoji PNG assets (72×72) committed to the repo — `1f3c6.png` 🏆, `274c.png` ❌, `1f1e7-1f1f7.png` 🇧🇷. Add new ones with `tools/fetch_emoji.py`. | `tools/fetch_emoji.py` |

### Session workflow

Sessions are recorded in-game with `tools/record_session.py` (one frame per second). After recording, the directory is manually curated: one file per score event, sorted numerically (file at index `i` → score `i`). Then `tools/extract_session_templates.py` processes the directory.

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

> **Note:** In RL, the local player's team is always shown on the left. If the player is on Orange, Orange appears on the left (`BLUE_X` region). `detect_left_colour()` in `ocr.py` detects this by comparing mean R vs B channel in the left panel region.

### Test fixtures

Both fixture directories use the same filename format:

```
[desc].[left_score]-[right_score]_[min]-[sec]_[colour].png
```

`colour` is the team shown on the **left** side of the HUD. `n` in any position means not applicable / unreadable.

| Directory | Contents |
|-----------|----------|
| `tests/fixtures/snippet/` | HUD-strip crops (480×110) — used for score and timer unit tests |
| `tests/fixtures/full_screen/` | Full 2560×1440 captures — used for timer and special-case tests; `load_full_screen()` crops to the HUD region automatically |
| `tests/fixtures/result_screen/` | Full 2560×1440 post-match result card captures — used for `detect_winner()` tests. Filename format: `{outcome}_{end_type}_{colour_on_left}.png`. See README in that directory and `TODO_TEST_CASES.txt` for collection status. |

**These files are protected** — do not rename or delete them without prompting the user to manually verify the correct label. If a test fails, report it and ask the user to inspect the image.

| Directory | Contents |
|-----------|----------|
| `tests/fixtures/full_game_session/` | Full 2560×1440 session recordings (PNG sequences) + `annotation.json` per session. **Gitignored** (too large to commit) — files live on disk only. **Protected** — do not create, modify, or delete any file in this directory under any circumstances. |

Test output (e.g. generated scoreworm images) goes to `tests/output/` which is gitignored. Never write test output into any `tests/fixtures/` subdirectory.

### Known issues / TODOs

- **OCR speed** — `read_hud` takes ~165ms: timer ~122ms (10 `cv2.matchTemplate` sliding-window calls at ~11ms each — inherent cost of 1D scan across 440×1040 strip), scores ~41ms (5 threshold × 2 batched matmuls). Well within the 0.5s polling interval. Timer is the bottleneck if further optimisation is needed.
- **Scores > 99** return None (acceptable)
- **1 xfail:** `count_up.10-95_1-13_orange` — '9' template outscores '3' at the ones position; needs '9' template rebuilt from a less ambiguous source
- **Forfeit winner wrong when leading team quits / OT forfeit** — infrastructure wired: `detect_winner()` is called on each None-streak frame and the result is passed through to `scoreworm.generate()` and `bot.py`. Still a stub (`(None, False)`) until result-screen templates are built. Scope: forfeit cases only — OT golden goals rely on `ys[-1]` (result screen may not appear until after the goal replay animation). See `forfeit_winner_detection.md`.

### Active plans

Plans live in `.claude/plans/`. Completed plans are archived in `.claude/plans/done/`.

| File | Status | Summary |
|------|--------|---------|
| `forfeit_winner_detection.md` | **In progress** | Forfeit winner detection: infrastructure wired + stub in place; most result_screen fixtures now ready to extract; e2e clip fixtures identified; templates not yet built |
| `scoreworm_emoji_markers.md` | **Done** (archived) | Emoji goal markers via Twemoji PNGs + matplotlib OffsetImage; Brazil rule (7-1); extensible annotation system |
| `implement_alerter.md` | **Done** | Alerter installed; `idle_prompt` filter + bottom-left window positioning fixed |
| `goal_annotation_ideas.md` | **Backlog** | Future goal annotations (🐢 turtle, ◀️ reverse, 🎩 hat trick) — require extra telemetry fields on `GoalEvent` not yet available |

> **Next session:** see `next_prompt.txt` in the repo root for the prepared pick-up prompt (end-screen detection work).
