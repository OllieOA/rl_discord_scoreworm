# Test Fixtures

## Protection rule

**Fixture files are protected** — do not rename or delete any fixture without prompting
the user to manually verify the correct label. If a test fails against a fixture, report
it and ask the user to inspect the image before changing anything.

## snippet/ and full_screen/ naming format

```
[desc].[left_score]-[right_score]_[min]-[sec]_[colour].png
```

`colour` is the team shown on the **left** side of the HUD. `n` in any position means
not applicable / unreadable.

## Fixture directories

| Directory | Contents |
|-----------|----------|
| `tests/fixtures/snippet/` | HUD-strip crops (480×110) — used for score and timer unit tests |
| `tests/fixtures/full_screen/` | Full 2560×1440 captures — used for timer and special-case tests; `load_full_screen()` crops to HUD region automatically |
| `tests/fixtures/result_screen/` | Full 2560×1440 post-match result card captures — one sub-directory per scenario, 3 PNGs each (`00.png`/`01.png`/`02.png` = full None streak). Sub-directory named `{outcome}_{end_type}_{colour_on_left}/`. See README in that directory. |
| `tests/fixtures/full_game_session/` | Full 2560×1440 session recordings (PNG sequences) + `annotation.json` per session. **Gitignored** — files live on disk only. **Protected** — do not create, modify, or delete any file in this directory under any circumstances. |

## result_screen/ scenarios

| Folder | Scenario | Frames available |
|--------|----------|-----------------|
| `win_normal_blue/` | Player wins regulation, Blue on left | 3/3 |
| `loss_normal_blue/` | Player loses regulation, Blue on left | 3/3 |
| `win_overtime_blue/` | Player wins OT golden goal, Blue on left | 3/3 |
| `loss_overtime_blue/` | Player loses OT, Blue on left | 3/3 |
| `win_forfeit_blue/` | Opponent forfeits while player winning | 3/3 |
| `loss_forfeit_orange/` | Orange on left leads 2–1, forfeits — KEY BUG case | 3/3 |
| `loss_overtime_orange/` | Orange on left, loses OT golden goal | 3/3 |
| `win_normal_orange/` | Player wins regulation, Orange on left (optional) | 3/3 |
| `win_overtime_orange/` | Player wins OT, Orange on left (optional) | 3/3 |
| `loss_forfeit_blue/` | Blue leads, blue forfeits | **Not collected** |
| `win_forfeit_ot_blue/` | OT forfeit at 0-0 diff | **Not collected** |

## Test output

Test output (e.g. generated scoreworm images) goes to `tests/output/` which is gitignored.
Never write test output into any `tests/fixtures/` subdirectory.
