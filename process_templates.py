"""
Score template processor.

Converts raw HUD captures in templates/raw/ into preprocessed score digit
templates in templates/score/. Safe to run multiple times — output is always
fully regenerated from the raw inputs.

Preprocessing pipeline (must match ocr.py exactly):
  greyscale → binarise at THRESHOLD → 4× upscale → dilate

Tune THRESHOLD, SCALE, DILATE_K, DILATE_I here and re-run to experiment.

Usage:
    python process_templates.py
"""

import os
import re

import cv2
import numpy as np
from PIL import Image

TEMPLATES_DIR = "templates"

SIDE_X = {
    "left":  (0, 110),
    "right": (370, 480),
}

THRESHOLD = 128
SCALE     = 4
DILATE_K  = 4
DILATE_I  = 2

# Bounding box (in 4× scaled space) within which digits are expected.
# Everything outside is zeroed out to reduce border noise. Tune as needed.
MASK_X  = 62
MASK_Y  = 62
MASK_W  = 330
MASK_H  = 330


def preprocess(frame: np.ndarray, x0: int, x1: int) -> np.ndarray:
    crop = frame[:, x0:x1]
    grey = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    _, bw = cv2.threshold(grey, THRESHOLD, 255, cv2.THRESH_BINARY)
    bw = cv2.resize(bw, (bw.shape[1] * SCALE, bw.shape[0] * SCALE),
                    interpolation=cv2.INTER_NEAREST)
    kernel = np.ones((DILATE_K, DILATE_K), np.uint8)
    bw = cv2.dilate(bw, kernel, iterations=DILATE_I)
    return apply_score_mask(bw)


def apply_score_mask(img: np.ndarray) -> np.ndarray:
    """Zero out everything outside the expected digit bounding box."""
    mask = np.zeros_like(img)
    mask[MASK_Y:MASK_Y + MASK_H, MASK_X:MASK_X + MASK_W] = 255
    return cv2.bitwise_and(img, mask)


def main():
    raw_dir   = os.path.join(TEMPLATES_DIR, "raw")
    score_dir = os.path.join(TEMPLATES_DIR, "score")

    pattern = re.compile(r"^capture_(\d+)_(left|right)\.png$")
    raws = sorted(f for f in os.listdir(raw_dir) if pattern.match(f))

    if not raws:
        print(f"No raw captures found in {raw_dir}/")
        return

    os.makedirs(score_dir, exist_ok=True)
    existing = [f for f in os.listdir(score_dir) if f.endswith(".png")]
    if existing:
        print(f"Aborting: {len(existing)} file(s) already exist in {score_dir}/.")
        print("Delete all templates/score/*.png files before re-running.")
        return

    count = 0
    for fname in raws:
        m = pattern.match(fname)
        i, side = int(m.group(1)), m.group(2)
        x0, x1 = SIDE_X[side]

        frame = np.array(Image.open(os.path.join(raw_dir, fname)).convert("RGB"))
        processed = preprocess(frame, x0, x1)

        score_path = os.path.join(score_dir, f"{i}_{side}.png")
        cv2.imwrite(score_path, processed)
        print(f"  {fname}  -> {i}_{side}.png")
        count += 1

    print(f"\nDone. {count} templates written to {score_dir}/")
    print(f"Parameters used: THRESHOLD={THRESHOLD}, SCALE={SCALE}, "
          f"DILATE_K={DILATE_K}, DILATE_I={DILATE_I}")


if __name__ == "__main__":
    main()
