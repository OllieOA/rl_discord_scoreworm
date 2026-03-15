"""
Extracts individual digit crops from timer_raw captures and saves them to
templates/timer/ ready for use by ocr.py.

Uses a vertical projection profile to find character boundaries automatically.
"""

import os
import cv2
import numpy as np

TIMER_RAW_DIR = os.path.join("templates", "timer_raw")
TIMER_OUT_DIR = os.path.join("templates", "timer")

# capture_9 = 4:18 (258s) is the first frame where the timer was running.
# From there it drops 1s per capture: time_seconds = 267 - i for i >= 9.
# Captures 0-8 were pre-kickoff (timer frozen at 4:21) — not useful for extraction.
def _generate_known_times() -> dict:
    times = {}
    for i in range(9, 60):
        s = 267 - i
        if s < 0:
            break
        times[i] = f"{s // 60}:{s % 60:02d}"
    return times

KNOWN_TIMES = _generate_known_times()


def find_char_crops(img: np.ndarray, min_gap: int = 15, min_width: int = 25) -> list[np.ndarray]:
    """
    Split a binary image into individual character crops using column projection.
    Columns with no white pixels are treated as separators.
    Segments narrower than min_width are discarded as edge noise.
    """
    col_sum = img.sum(axis=0)  # white pixel count per column
    in_char = False
    chars = []
    x_start = 0

    for x, val in enumerate(col_sum):
        if not in_char and val > 0:
            in_char = True
            x_start = x
        elif in_char and val == 0:
            in_char = False
            chars.append((x_start, x))

    if in_char:
        chars.append((x_start, len(col_sum)))

    # Merge segments that are too close together (handles thin strokes with gaps)
    merged = []
    for seg in chars:
        if merged and seg[0] - merged[-1][1] < min_gap:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(list(seg))

    # Discard edge noise (very narrow segments)
    merged = [s for s in merged if s[1] - s[0] >= min_width]

    return [img[:, x0:x1] for x0, x1 in merged]


def parse_time_labels(time_str: str) -> list[str]:
    """'4:56' → ['4', 'colon', '5', '6']"""
    labels = []
    for ch in time_str:
        if ch == ":":
            labels.append("colon")
        else:
            labels.append(ch)
    return labels


def main():
    os.makedirs(TIMER_OUT_DIR, exist_ok=True)
    saved: dict[str, str] = {}  # label → source file

    for idx, time_str in KNOWN_TIMES.items():
        path = os.path.join(TIMER_RAW_DIR, f"capture_{idx}.png")
        if not os.path.exists(path):
            print(f"  Missing: {path}")
            continue

        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        crops = find_char_crops(img)
        labels = parse_time_labels(time_str)

        if len(crops) != len(labels):
            print(f"  capture_{idx} ({time_str}): expected {len(labels)} chars, "
                  f"found {len(crops)} — skipping")
            continue

        for crop, label in zip(crops, labels):
            out_path = os.path.join(TIMER_OUT_DIR, f"{label}.png")
            if label not in saved and not os.path.exists(out_path):
                cv2.imwrite(out_path, crop)
                saved[label] = f"capture_{idx}"
                print(f"  Saved {label}.png  (from capture_{idx} / {time_str})")
            elif label not in saved:
                saved[label] = "pre-existing"

    print(f"\nExtracted {len(saved)} templates: {sorted(saved.keys())}")
    all_digits = set("0123456789") | {"colon"}
    missing = all_digits - set(saved.keys())
    if missing:
        print(f"Still missing: {sorted(missing)}")
        print("Play another session showing those digits to fill the gaps.")
    else:
        print("All digits covered!")


if __name__ == "__main__":
    main()
