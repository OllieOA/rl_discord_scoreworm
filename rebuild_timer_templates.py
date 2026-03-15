"""
Rebuild timer templates from HUD snippet files with valid timestamps.

Reads all *.png files in the snippet directory, parses the timestamp from
the naming convention:
    [desc].[left]-[right]_[min]-[sec]_[colour].png

Skips files where time is 'n-n'.  Preprocesses the timer region of each
snippet, segments characters using column projection, and saves one crop
per unique digit label to templates/timer/.

Run this whenever the timer templates need refreshing from new capture data.
Delete templates/timer/*.png first if you want a full rebuild.

Usage:
    python rebuild_timer_templates.py
    python rebuild_timer_templates.py --snippet-dir tests/fixtures/snippet
    python rebuild_timer_templates.py --overwrite   # replace existing templates
"""

import argparse
import os

import cv2
import numpy as np

from ocr import _preprocess, TIMER_X

SNIPPET_DIR = os.path.join("tests", "fixtures", "snippet")
TIMER_DIR   = os.path.join("templates", "timer")


# ── Helpers (reused from extract_timer_templates.py) ─────────────────────────

def find_char_crops(img: np.ndarray, min_gap: int = 15,
                    min_width: int = 25) -> list[np.ndarray]:
    """Split a binary timer strip into character crops via column projection."""
    col_sum = img.sum(axis=0)
    in_char, chars, x_start = False, [], 0
    for x, val in enumerate(col_sum):
        if not in_char and val > 0:
            in_char, x_start = True, x
        elif in_char and val == 0:
            in_char = False
            chars.append((x_start, x))
    if in_char:
        chars.append((x_start, len(col_sum)))

    # Merge close segments
    merged = []
    for seg in chars:
        if merged and seg[0] - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(list(seg))

    return [img[:, x0:x1] for x0, x1 in merged
            if x1 - x0 >= min_width]


def parse_time_labels(min_str: str, sec_str: str) -> list[str]:
    """('4', '12') → ['4', 'colon', '1', '2']"""
    labels = [min_str, "colon"]
    sec = int(sec_str)
    labels.append(str(sec // 10))
    labels.append(str(sec % 10))
    return labels


def parse_snippet_time(fname: str) -> tuple[str, str] | None:
    """Return (min_str, sec_str) parsed from filename, or None if time is n-n."""
    stem = os.path.splitext(fname)[0]
    try:
        _, rest = stem.split(".", 1)
        _, time_part, _ = rest.rsplit("_", 2)
        min_str, sec_str = time_part.split("-")
        if min_str == "n" or sec_str == "n":
            return None
        return min_str, sec_str
    except (ValueError, AttributeError):
        return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snippet-dir", default=SNIPPET_DIR,
                        help=f"directory of HUD snippet files (default: {SNIPPET_DIR})")
    parser.add_argument("--overwrite", action="store_true",
                        help="overwrite existing templates")
    args = parser.parse_args()

    os.makedirs(TIMER_DIR, exist_ok=True)

    files = sorted(f for f in os.listdir(args.snippet_dir) if f.endswith(".png"))
    saved: dict[str, str] = {}   # label → source filename
    skipped = 0

    for fname in files:
        parsed = parse_snippet_time(fname)
        if parsed is None:
            skipped += 1
            continue

        min_str, sec_str = parsed
        labels = parse_time_labels(min_str, sec_str)

        img = cv2.imread(os.path.join(args.snippet_dir, fname),
                         cv2.IMREAD_UNCHANGED)
        if img is None:
            continue

        # Convert to RGB numpy array for _preprocess
        if img.ndim == 2:
            rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        elif img.shape[2] == 4:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        else:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        timer_strip = _preprocess(rgb, *TIMER_X)
        crops = find_char_crops(timer_strip)

        if len(crops) != len(labels):
            print(f"  {fname}: expected {len(labels)} chars, "
                  f"found {len(crops)} — skipping")
            continue

        for crop, label in zip(crops, labels):
            out_path = os.path.join(TIMER_DIR, f"{label}.png")
            if label not in saved:
                if not os.path.exists(out_path) or args.overwrite:
                    cv2.imwrite(out_path, crop)
                    saved[label] = fname
                    print(f"  {label}.png  <- {fname}")
                else:
                    saved[label] = "pre-existing"

    print(f"\n{len(saved)} labels covered: {sorted(saved.keys())}")
    print(f"{skipped} files skipped (n-n timestamp)")

    missing = (set("0123456789") | {"colon"}) - set(saved.keys())
    if missing:
        print(f"Still missing: {sorted(missing)}")
    else:
        print("All digits covered.")


if __name__ == "__main__":
    main()
