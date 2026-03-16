# OCR Pipeline

## HUD sub-regions (within the 480×110 crop)

| Region | X range | Content |
|--------|---------|---------|
| `BLUE_X` | 0 – 110 | Left team score |
| `TIMER_X` | 110 – 370 | Match timer |
| `ORANGE_X` | 370 – 480 | Right team score |

> In RL, the local player's team is always shown on the left. If the player is on Orange,
> Orange appears on the left (`BLUE_X` region). `detect_left_colour()` in `ocr.py` detects
> this by comparing mean R vs B channel in the left panel region.

## Preprocessing constants

```python
SCALE     = 4
THRESHOLD = 128
DILATE_K  = 4
DILATE_I  = 2
```

All templates in `templates/score/` and `templates/timer/` are preprocessed with these
exact parameters. Any new template pipeline must match them.

## Template directories

| Directory | Contents | How generated |
|-----------|----------|---------------|
| `templates/score/` | `0_left.png`–`99_left.png`, `0_right.png`–`99_right.png` — one per score value per side (200 total) | `tools/process_templates.py` (from `templates/raw/`) |
| `templates/timer/` | `0.png`–`9.png` + `colon.png` + `plus.png` | `tools/rebuild_timer_templates.py` (digits/colon from session snippets); `plus.png` extracted manually via connected-components from the `+3:40` overtime fixture |
| `templates/raw/` | Full raw HUD strips from session recordings, named `capture_{score}_{side}.png` | `tools/extract_session_templates.py` |
| `templates/result/` | "WINNER" and "WINNER BY FORFEIT" label crops for result-screen detection | Not yet built — see `forfeit_winner_detection.md` |
| `assets/emoji/` | Twemoji PNG assets (72×72) — `1f3c6.png` 🏆, `274c.png` ❌, `1f1e7-1f1f7.png` 🇧🇷. Add with `tools/fetch_emoji.py`. | `tools/fetch_emoji.py` |

## Result-screen detection (`detect_winner`)

`detect_winner(frame) -> tuple[str | None, bool, float]`
Returns `(rl_colour, is_forfeit, confidence)` where `rl_colour` is the actual RL team
colour of the winner ("blue"/"orange"), not left/right position. `game_state.py` maps to
left/right using `_colour_on_left`.

**Two-step detection:**
1. Template-match "WINNER BY FORFEIT" then "WINNER" (NCC ≥ 0.7). Sets `is_forfeit`.
2. Colour-analyse the large team-name text below the label: Canny edges → dilate → mask;
   count HSV orange (H≈15–30°, S>0.7, V>0.7) vs blue (H≈200–230°, S>0.5, V>0.5) pixels.
3. `confidence = label_ncc × colour_dominance_ratio`

Exact pixel regions and HSV thresholds to be calibrated from `tests/fixtures/result_screen/`.

## Session workflow (template capture)

Sessions are recorded in-game with `tools/record_session.py` (one frame per second).
After recording, the directory is manually curated: one file per score event, sorted
numerically (file at index `i` → score `i`). Then `tools/extract_session_templates.py`
processes the directory.

### Curated score sessions

| Directory | Side | Scores covered |
|-----------|------|----------------|
| `sessions/left_count_up` | left (blue) | blue 0–99, orange 0 |
| `sessions/right_count_up` | right (orange) | blue 0, orange 0–99 |
| `sessions/double_digits` | — | double-digit captures |
| `sessions/full_tournament` | — | full tournament recording |
