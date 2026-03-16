# Result Screen Fixtures

Full-screen (2560×1440) captures of the Rocket League post-match result card,
taken at the moment it first appears (i.e. immediately after the HUD disappears).

These are used to build and test `detect_winner()` in `ocr.py`.

## Filename format

```
{outcome}_{end_type}_{colour_on_left}.png
```

| Field | Values | Meaning |
|-------|--------|---------|
| `outcome` | `win`, `loss` | Whether the **left-side** player won or lost |
| `end_type` | `normal`, `overtime`, `forfeit`, `forfeit_ot` | How the game ended |
| `colour_on_left` | `blue`, `orange` | Which RL team colour is on the left side of the HUD |

## Required fixtures (7)

| Filename | Scenario | Status |
|----------|----------|--------|
| `win_normal_blue.png` | Player wins by goals, regulation, blue on left | Available — extract from `full_game_blue-blue` frame ~381 |
| `loss_normal_blue.png` | Player loses by goals, regulation, blue on left | **Need to collect** |
| `win_overtime_blue.png` | Player wins golden goal OT, blue on left | Available — extract from `full_game_overtime_blue-blue` frame ~522 |
| `loss_overtime_blue.png` | Player loses golden goal OT, blue on left | **Need to collect** |
| `win_forfeit_blue.png` | Opponent forfeits while player is winning, regulation, blue on left | Available — extract from `full_game_forfeit_blue-blue` frame ~259 |
| `loss_forfeit_blue.png` | Leading team (opponent) forfeits while player is losing, regulation — KEY BUG CASE | **Need to collect** |
| `win_forfeit_ot_blue.png` | Either team forfeits in OT with no OT goal scored yet, blue on left | **Need to collect** |

## Optional fixtures

| Filename | Scenario | Status |
|----------|----------|--------|
| `win_normal_orange.png` | Player wins, regulation, orange on left | Available — extract from `full_game_orange-blue` frame ~428 |
| `win_overtime_orange.png` | Player wins OT, orange on left | Available — extract from `full_game_overtime_orange-blue` frame ~548 |
| `win_forfeit_orange.png` | Opponent forfeits, player winning, orange on left | Need to collect |

## Extracting from existing full_game_session recordings

The first None-streak frame (where the result screen first appears) is at
`game_end_index - 2`. Copy that frame from the session directory and rename it:

```
# Example: win_normal_blue from full_game_blue-blue (game_end = 383, first None = 381)
cp tests/fixtures/full_game_session/full_game_blue-blue/00381.png \
   tests/fixtures/result_screen/win_normal_blue.png
```

Verify visually that the result card is actually visible in the frame
(not the scoreboard or lobby).

## Capturing new fixtures

Use `tools/record_session.py` at 0.5s interval. The result screen appears in
the first captured frame after the last HUD-visible frame and stays visible for
at least 0.5s (guaranteed at current poll rate).

After recording, copy the first post-HUD frame and name it per the format above.
