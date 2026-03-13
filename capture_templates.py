"""
Score template capture utility.

Captures the blue score region every 20 seconds.  Score goals on one side
incrementally — capture 0 = score 0, capture 1 = score 1, etc.

Each capture saves:
  templates/raw/capture_{i}.png  — full raw HUD frame (RGB) for reprocessing
  templates/score/{i}.png        — preprocessed score crop (skipped if exists)

To reprocess raw frames into score templates without going in-game:
    python capture_templates.py --from-raw

Usage:
    python capture_templates.py            # live capture, 10 captures, 20s interval
    python capture_templates.py --count 9
    python capture_templates.py --from-raw # reprocess existing raw frames
"""

import argparse
import os
import time

import cv2
import numpy as np
from PIL import Image

from capture import grab_frame

TEMPLATES_DIR = "templates"
INTERVAL = 20   # seconds between captures

BLUE_X = (0, 110)

_SCALE    = 4
_DILATE_K = 4
_DILATE_I = 2


def preprocess(frame: np.ndarray, x0: int, x1: int) -> np.ndarray:
    crop = frame[:, x0:x1]
    grey = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    _, bw = cv2.threshold(grey, 128, 255, cv2.THRESH_BINARY)
    bw = cv2.resize(bw, (bw.shape[1] * _SCALE, bw.shape[0] * _SCALE),
                    interpolation=cv2.INTER_NEAREST)
    kernel = np.ones((_DILATE_K, _DILATE_K), np.uint8)
    return cv2.dilate(bw, kernel, iterations=_DILATE_I)


def save_score_template(frame: np.ndarray, index: int, score_dir: str) -> str:
    score_path = os.path.join(score_dir, f"{index}.png")
    if not os.path.exists(score_path):
        score_img = preprocess(frame, *BLUE_X)
        cv2.imwrite(score_path, score_img)
        return "saved"
    return "skipped (already exists)"


def from_raw(raw_dir: str, score_dir: str) -> None:
    """Reprocess saved raw frames into score templates."""
    raws = sorted(f for f in os.listdir(raw_dir) if f.startswith("capture_") and f.endswith(".png"))
    if not raws:
        print(f"No raw captures found in {raw_dir}/")
        return
    os.makedirs(score_dir, exist_ok=True)
    for fname in raws:
        i = int(fname.replace("capture_", "").replace(".png", ""))
        frame = np.array(Image.open(os.path.join(raw_dir, fname)).convert("RGB"))
        result = save_score_template(frame, i, score_dir)
        print(f"  capture_{i}  score={result}")
    print(f"\nDone. Score templates saved to {score_dir}/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count",    type=int, default=10, help="number of live captures")
    parser.add_argument("--interval", type=int, default=INTERVAL, help="seconds between captures")
    parser.add_argument("--from-raw", action="store_true", help="reprocess raw frames instead of capturing live")
    args = parser.parse_args()

    raw_dir   = os.path.join(TEMPLATES_DIR, "raw")
    score_dir = os.path.join(TEMPLATES_DIR, "score")

    if args.from_raw:
        from_raw(raw_dir, score_dir)
        return

    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(score_dir, exist_ok=True)

    print("Starting in 3 seconds — alt-tab back to Rocket League!")
    time.sleep(3)

    for i in range(args.count):
        frame = grab_frame()

        # Always save the full raw frame so captures can be reprocessed later
        raw_path = os.path.join(raw_dir, f"capture_{i}.png")
        if not os.path.exists(raw_path):
            cv2.imwrite(raw_path, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))

        result = save_score_template(frame, i, score_dir)
        print(f"  Capture {i}  score={result}  (score should be {i})")

        if i < args.count - 1:
            for remaining in range(args.interval, 0, -1):
                print(f"    next capture in {remaining}s...", end="\r")
                time.sleep(1)
            print()

    print(f"\nDone. Raw frames in {raw_dir}/  |  Score templates in {score_dir}/")


if __name__ == "__main__":
    main()
