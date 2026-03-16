# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Design reference:** for module internals, OCR pipeline details, template system,
> fixture formats, or chart visual spec — read the relevant file in `design/` rather
> than guessing. Only load what you need for the current task.

## What This Project Does

**rl_discord_scoreworm** watches a live Rocket League match and automatically posts a
score worm chart to Discord when the game ends. A score worm is a step-chart of the
score differential over time. See `design/scoreworm_chart.md` for the full visual spec.

## Coding conventions

- Use `->` not `→` in Python source (print statements, f-strings, comments). The Windows
  terminal encoding (cp1252) cannot encode `→`, causing `UnicodeEncodeError` at runtime.

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
uv run python game_state.py          # run tracker only (no Discord), prints goal events
uv run python scoreworm.py           # render a test chart → scoreworm_preview.png
uv run python capture.py             # save a HUD screenshot → hud_preview.png

# Tests — default uses 24 workers (3/4 of CPUs, preserving system headroom)
uv run pytest                        # all tests, quiet output
uv run pytest tests/test_ocr.py -k "game_start"   # single test by keyword
uv run pytest tests/test_ocr.py      # full suite after fixing
```

## Architecture

```
capture.py → ocr.py → game_state.py → scoreworm.py → bot.py
```

See `design/architecture.md` for module responsibilities, tools, and detection logic.

## Known issues / TODOs

- **OCR speed** — `read_hud` takes ~165ms. Well within the 0.5s polling interval. Timer is the bottleneck.
- **Scores > 99** return None (acceptable)
- **1 xfail:** `count_up.10-95_1-13_orange` — '9' template outscores '3' at the ones position; needs '9' template rebuilt from a less ambiguous source
- **Forfeit winner wrong when leading team quits / OT forfeit** — `detect_winner()` is wired but still a stub (`(None, False, 0.0)`) until result-screen templates are built. Scope: forfeit cases only. See `forfeit_winner_detection.md`.

## Active plans

Plans live in `.claude/plans/`. Completed plans are archived in `.claude/plans/done/`.

| File | Status | Summary |
|------|--------|---------|
| `forfeit_winner_detection.md` | **In progress** | Forfeit winner detection: infrastructure wired + stub in place; result_screen fixtures committed; templates not yet built |
| `goal_annotation_ideas.md` | **Backlog** | Future goal annotations (🐢 turtle, ◀️ reverse, 🎩 hat trick) — require extra telemetry fields on `GoalEvent` not yet available |
