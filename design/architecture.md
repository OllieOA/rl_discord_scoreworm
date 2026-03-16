# Architecture

## Pipeline

```
capture.py → ocr.py → game_state.py → scoreworm.py → bot.py
```

## Module responsibilities

| Module | Responsibility |
|--------|----------------|
| `capture.py` | Grabs the HUD region from the centre monitor. Auto-detects the centre screen from a 3-monitor setup by sorting monitors by left-edge position. HUD region: left=1040, top=0, width=480, height=110 (tuned for 2560×1440). Also exposes `grab_full_frame()` for full 2560×1440 capture (used for result-screen detection). |
| `ocr.py` | Template-matching OCR. Preprocesses frames (greyscale → binarise → 4× upscale → dilate). **Scores** try 5 binarisation thresholds (110/128/150/170/190) and accept the highest-confidence batched NCC result — thresholds ≥170 reject the overtime orange panel background (greyscale ≈158) without a separate code path. **Timer** uses a single threshold (128) with sliding `cv2.matchTemplate` across positional zones (minute x<380, tens 380–580, ones ≥580 in 4× space); regular-time reads are gated on a colon template match (≥0.65) to reject the "OVERTIME" text frame; overtime reads (`+` template detected at ≥0.75) parse `+M:SS` or `+MM:SS`. **`detect_winner(frame)`** matches "WINNER" / "WINNER BY FORFEIT" label + colour-analyses the large team-name text (stub until templates built). Returns `HudReading(blue, orange, time)` — fields are `None` if unreadable. ~165ms/call. |
| `game_state.py` | Polls capture+OCR every 0.5s. State machine: `IDLE → IN_GAME → OVERTIME → (callback) → IDLE`. Corrupt-read guard discards impossible score transitions. OT-pending flag defers OVERTIME transition until the banner frame. On each all-None frame, grabs the full screen and calls `detect_winner()`; accumulates candidates in `_winner_candidates`; at game-end picks max confidence and maps rl_colour → left/right using `_colour_on_left`. Fires `on_game_over(goals, end_type, colour_on_left, game_end_time, winner)` when 3 consecutive all-None frames are detected. Also exposes `replay(readings)` for testing. |
| `scoreworm.py` | Takes a list of `GoalEvent`, `end_type`, and optional `winner` string, returns a PIL Image. Uses `winner` for the end icon when provided; falls back to `ys[-1]` goal-differential otherwise. `annotate_goals(goals)` (public) returns per-goal codepoints; `ANNOTATION_LEGEND` maps codepoint → Discord legend line. End icons (🏆/❌) and goal annotations (🇧🇷 at 7-1) are placed as Twemoji PNGs via `AnnotationBbox`; falls back to text if PNG missing. Worm stops at last goal on forfeit; extends past 5:00 with red OT bands. Pure function — no I/O side effects. |
| `bot.py` | Logs into Discord, starts `GameTracker` in a background thread. Uses `asyncio.run_coroutine_threadsafe` to post the image when `on_game_over` fires. Builds Discord message as header + optional legend lines (one per unique special goal annotation, e.g. `🇧🇷 - Brazil 7-1`). |

## Tools

| Tool | Purpose |
|------|---------|
| `tools/record_session.py` | Records full-screen captures to `sessions/<timestamp>/` at a configurable interval (default 1s). Used to capture template source material in-game. |
| `tools/extract_session_templates.py` | Processes a `sessions/` directory (one file per score, sorted numerically). Saves raw HUD crops to `templates/raw/` and labelled HUD strips to `tests/fixtures/snippet/`. Side is inferred from directory name (`left`/`right`). |
| `tools/process_templates.py` | Converts `templates/raw/capture_N_{side}.png` files into preprocessed score templates in `templates/score/`. Preprocessing must match `ocr.py` exactly. |
| `tools/rebuild_timer_templates.py` | Rebuilds `templates/timer/` from session-style snippet fixtures. |
| `tools/annotate_sessions.py` | Runs OCR over full-game session recordings and writes `annotation.json` into each session folder. |
| `tools/fetch_emoji.py` | Downloads Twemoji PNG assets by emoji char or codepoint into `assets/emoji/`. Usage: `uv run python tools/fetch_emoji.py 🏆 ❌ 🇧🇷` |
| `tools/extract_result_screen_fixtures.sh` | Copies the 3-frame None-streak clips from sessions into `tests/fixtures/result_screen/` sub-directories. |

## Game state detection logic

- **Game start:** OCR reads `0-0` on both scores and `5:00` on the timer simultaneously
- **Goal:** either team's score increments by 1 between consecutive frames
- **Corrupt read:** score decreases or jumps by >1 → frame discarded, `prev` unchanged
- **OT-pending:** timer `0:00` with level scores sets `_ot_pending`; first frame where scores are readable but timer is `None` (OVERTIME banner) → transition to OVERTIME state
- **Forfeit:** game ends without reaching `0:00` (opponent leaves)
- **Game end (all cases):** 3 consecutive all-`None` frames — post-match scoreboard replaced the HUD
