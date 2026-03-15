"""
Extract HUD snippets and raw template captures from a record_session.py directory.

Files are assumed to be pre-curated: sorted numerically, one file per score,
starting at score 0.  File at index i → score i.

Saves to:
  templates/raw/capture_{score}_{side}.png       — for process_templates.py
  tests/fixtures/snippet/count_up.{l}-{r}_{m}-{s}_{colour}.png  — for tests

Side and colour are inferred from the directory name:
  *left*  → side=left,  colour=blue   (blue score is on the left)
  *right* → side=right, colour=orange (blue score is on the right)

Usage:
    uv run python tools/extract_session_templates.py sessions/left_count_up
    uv run python tools/extract_session_templates.py sessions/right_count_up
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
from PIL import Image

from capture import HUD_HEIGHT, HUD_LEFT, HUD_TOP, HUD_WIDTH
from ocr import read_hud

TEMPLATES_DIR = "templates"
SNIPPETS_DIR  = os.path.join("tests", "fixtures", "snippet")


def crop_hud(path: str) -> np.ndarray:
    """Load a full-screen image and return the HUD strip as an RGB numpy array."""
    full = np.array(Image.open(path).convert("RGB"))
    return full[HUD_TOP:HUD_TOP + HUD_HEIGHT, HUD_LEFT:HUD_LEFT + HUD_WIDTH]


def timer_str(hud: np.ndarray) -> str:
    """Return 'M-SS' from template matching, or 'n-n' if unreadable."""
    seconds = read_hud(hud).time
    if seconds is None:
        return "n-n"
    m, s = divmod(seconds, 60)
    return f"{m}-{s:02d}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("session_dir", help="path to the session directory")
    parser.add_argument("--dry-run", action="store_true",
                        help="print actions without writing files")
    args = parser.parse_args()

    session_dir = args.session_dir.rstrip("/\\")

    # Infer side from directory name
    name = os.path.basename(session_dir).lower()
    if "left" in name:
        side, colour = "left", "blue"
    elif "right" in name:
        side, colour = "right", "orange"
    else:
        raise SystemExit(f"Cannot infer side from directory name '{name}'. "
                         "Directory must contain 'left' or 'right'.")

    files = sorted(
        (f for f in os.listdir(session_dir) if f.lower().endswith(".png")),
        key=lambda f: int(os.path.splitext(f)[0]),
    )

    print(f"Directory : {session_dir}")
    print(f"Side      : {side}  |  colour on left: {colour}")
    print(f"Files     : {len(files)}  (scores 0–{len(files) - 1})")

    raw_dir     = os.path.join(TEMPLATES_DIR, "raw")
    os.makedirs(raw_dir,     exist_ok=True)
    os.makedirs(SNIPPETS_DIR, exist_ok=True)

    skipped_raw, written_raw = 0, 0
    written_snippet = 0

    for score, fname in enumerate(files):
        full_path = os.path.join(session_dir, fname)
        hud = crop_hud(full_path)
        t   = timer_str(hud)

        # ── templates/raw/ ────────────────────────────────────────────────────
        raw_path = os.path.join(raw_dir, f"capture_{score}_{side}.png")
        if os.path.exists(raw_path):
            skipped_raw += 1
        elif not args.dry_run:
            cv2.imwrite(raw_path, cv2.cvtColor(hud, cv2.COLOR_RGB2BGR))
            written_raw += 1
        else:
            written_raw += 1  # count as would-be written

        # ── tests/fixtures/snippet/ ───────────────────────────────────────────
        if side == "left":
            score_part = f"{score}-0"
        else:
            score_part = f"0-{score}"

        snippet_name = f"count_up.{score_part}_{t}_{colour}.png"
        snippet_path = os.path.join(SNIPPETS_DIR, snippet_name)

        if not args.dry_run:
            Image.fromarray(hud).save(snippet_path)
            written_snippet += 1
        else:
            written_snippet += 1

        print(f"  score={score:>3}  timer={t}  raw={'skip' if os.path.exists(raw_path) else 'save'}  snippet={snippet_name}")

    print(f"\nDone.")
    print(f"  templates/raw : {written_raw} written, {skipped_raw} skipped (already existed)")
    print(f"  snippets      : {written_snippet} written to {SNIPPETS_DIR}/")
    if args.dry_run:
        print("  (dry run — no files were actually written)")


if __name__ == "__main__":
    main()
