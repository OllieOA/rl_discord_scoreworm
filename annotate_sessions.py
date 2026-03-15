"""
Annotate full-game session recordings with goal events detected by OCR.

For each session folder under tests/fixtures/full_game_session/:
  - Crops every frame to the HUD region and runs read_hud() in parallel
  - Records only events: game start, each goal, game end
  - Writes annotation.json into the session folder

Usage:
    uv run python annotate_sessions.py

Review each annotation.json before running tests against it.
"""

import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))

from capture import HUD_HEIGHT, HUD_LEFT, HUD_TOP, HUD_WIDTH
from ocr import read_hud

SESSION_ROOT = Path("tests/fixtures/full_game_session")

SESSION_META = {
    "full_game_blue-blue": {
        "colour_on_left": "blue",
        "expected_end_type": "normal",
        "expected_winner": "blue",
    },
    "full_game_forfeit_blue-blue": {
        "colour_on_left": "blue",
        "expected_end_type": "forfeit",
        "expected_winner": None,
    },
    "full_game_orange-blue": {
        "colour_on_left": "orange",
        "expected_end_type": "normal",
        "expected_winner": "blue",
    },
    "full_game_overtime_blue-blue": {
        "colour_on_left": "blue",
        "expected_end_type": "overtime",
        "expected_winner": "blue",
    },
    "full_game_overtime_orange-blue": {
        "colour_on_left": "orange",
        "expected_end_type": "overtime",
        "expected_winner": "blue",
    },
}

GAME_DURATION = 300   # seconds (5:00)
NONE_STREAK_THRESHOLD = 3


def _annotate_frame(png_path: str) -> dict:
    """Worker: load one full-screen frame, crop to HUD, run OCR."""
    img = np.array(Image.open(png_path).convert("RGB"))
    hud = img[HUD_TOP : HUD_TOP + HUD_HEIGHT, HUD_LEFT : HUD_LEFT + HUD_WIDTH]
    r = read_hud(hud)
    return {
        "index": int(Path(png_path).stem),
        "frame": Path(png_path).name,
        "blue": r.blue,
        "orange": r.orange,
        "time_seconds": r.time,
    }


def _fmt_timestamp(time_seconds: int | None, is_overtime: bool) -> str | None:
    if time_seconds is None:
        return None
    m, s = divmod(time_seconds, 60)
    return f"+{m}:{s:02d}" if is_overtime else f"{m}:{s:02d}"


def _extract_events(frames: list[dict]) -> dict:
    """
    Sequential pass over sorted OCR results.
    Returns a dict with game_start, goals list, and game_end.
    """
    game_start = None
    game_end = None
    goals = []

    state = "idle"   # idle | in_game | overtime
    prev = None
    none_streak = 0
    timer_reached_zero = False
    ot_pending = False   # t==0 with equal scores seen; waiting for OVERTIME banner

    for f in frames:
        b, o, t = f["blue"], f["orange"], f["time_seconds"]
        frame_ref = {"frame": f["frame"], "index": f["index"]}

        # Any None field: handle side-effects but never update prev or detect goals.
        # This ensures score comparisons only happen between fully-readable frames,
        # so a None frame mid-sequence (e.g. goal animation) is transparent.
        if b is None or o is None or t is None:
            if b is None and o is None and t is None:
                # All-None streak — post-match scoreboard replacing HUD
                none_streak += 1
                if none_streak >= NONE_STREAK_THRESHOLD and state != "idle":
                    if state == "overtime":
                        end_type = "overtime"
                    elif timer_reached_zero:
                        end_type = "normal"
                    else:
                        end_type = "forfeit"
                    game_end = {**frame_ref, "end_type": end_type}
                    state = "idle"
                    prev = None
            elif state == "in_game" and ot_pending and t is None:
                # Scores readable but timer gone — OVERTIME banner has appeared
                state = "overtime"
                ot_pending = False
            continue  # never update prev or detect goals on any None frame

        none_streak = 0

        # --- All fields readable from here ---

        if state == "idle":
            if b == 0 and o == 0 and t == GAME_DURATION:
                game_start = frame_ref
                state = "in_game"
                prev = f

        elif state == "in_game":
            is_overtime = False

            if prev is not None:
                bd = b - prev["blue"]
                od = o - prev["orange"]
                if bd == 1 and od == 0:
                    goals.append({
                        **frame_ref,
                        "team": "blue",
                        "score": [b, o],
                        "time_seconds": t,
                        "timestamp": _fmt_timestamp(t, is_overtime),
                        "is_overtime": is_overtime,
                    })
                elif od == 1 and bd == 0:
                    goals.append({
                        **frame_ref,
                        "team": "orange",
                        "score": [b, o],
                        "time_seconds": t,
                        "timestamp": _fmt_timestamp(t, is_overtime),
                        "is_overtime": is_overtime,
                    })
                elif bd not in (0, 1) or od not in (0, 1):
                    # Impossible transition — corrupt read (e.g. goal animation
                    # artefact misread as a large number). Discard frame; keep prev.
                    continue

            if t == 0:
                timer_reached_zero = True
                if b == o:
                    ot_pending = True
                else:
                    ot_pending = False  # juggling goal made scores unequal — normal end

            prev = f

        elif state == "overtime":
            is_overtime = True

            if prev is not None:
                bd = b - prev["blue"]
                od = o - prev["orange"]
                if bd == 1 and od == 0:
                    goals.append({
                        **frame_ref,
                        "team": "blue",
                        "score": [b, o],
                        "time_seconds": t,
                        "timestamp": _fmt_timestamp(t, is_overtime),
                        "is_overtime": is_overtime,
                    })
                elif od == 1 and bd == 0:
                    goals.append({
                        **frame_ref,
                        "team": "orange",
                        "score": [b, o],
                        "time_seconds": t,
                        "timestamp": _fmt_timestamp(t, is_overtime),
                        "is_overtime": is_overtime,
                    })
                elif bd not in (0, 1) or od not in (0, 1):
                    # Impossible transition — corrupt read. Discard frame; keep prev.
                    continue

            prev = f

    return {
        "game_start": game_start,
        "game_end": game_end,
        "goals": goals,
    }


def annotate_session(session_dir: Path, workers: int) -> None:
    name = session_dir.name
    meta = SESSION_META.get(name)
    if meta is None:
        print(f"[skip] {name} — no metadata entry")
        return

    png_paths = sorted(session_dir.glob("*.png"), key=lambda p: int(p.stem))
    if not png_paths:
        print(f"[skip] {name} — no PNG files found")
        return

    print(f"[annotate] {name}  ({len(png_paths)} frames)…", flush=True)

    # Parallel OCR
    raw: list[dict] = [None] * len(png_paths)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_annotate_frame, str(p)): i for i, p in enumerate(png_paths)}
        done = 0
        for fut in as_completed(futures):
            raw[futures[fut]] = fut.result()
            done += 1
            if done % 50 == 0 or done == len(png_paths):
                print(f"  {done}/{len(png_paths)}", flush=True)

    raw.sort(key=lambda r: r["index"])

    events = _extract_events(raw)

    # Print summary
    print(f"  game_start : {events['game_start']}")
    print(f"  game_end   : {events['game_end']}")
    print(f"  goals ({len(events['goals'])}):")
    for g in events["goals"]:
        ot = " (OT)" if g["is_overtime"] else ""
        print(f"    {g['timestamp']:>6}{ot}  {g['team']:6s}  {g['score'][0]}-{g['score'][1]}")

    annotation = {"session": name, **meta, **events}

    out_path = session_dir / "annotation.json"
    with open(out_path, "w") as f:
        json.dump(annotation, f, indent=2)
    print(f"  -> {out_path}\n")


def main() -> None:
    workers = min(24, (os.cpu_count() or 4) * 3 // 4)
    print(f"Using {workers} workers\n")

    session_dirs = sorted(d for d in SESSION_ROOT.iterdir() if d.is_dir() and d.name in SESSION_META)
    if not session_dirs:
        print(f"No session directories found under {SESSION_ROOT}")
        return

    for session_dir in session_dirs:
        annotate_session(session_dir, workers)

    print("Done. Review each annotation.json before running tests.")


if __name__ == "__main__":
    main()
