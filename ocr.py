"""OCR for the Rocket League score/timer HUD using template matching."""

import os
import re
from dataclasses import dataclass

import cv2
import numpy as np

TEMPLATES_DIR = "templates"
MATCH_THRESHOLD = 0.6   # minimum normalised cross-correlation score to accept a match

# ── Sub-regions within the HUD frame (x_start, x_end) ────────────────────────
BLUE_X   = (0,   110)
TIMER_X  = (110, 370)
ORANGE_X = (370, 480)
# ─────────────────────────────────────────────────────────────────────────────

# Pre-processing parameters — must match process_templates.py exactly
_SCALE      = 4
_THRESHOLD  = 128
_DILATE_K   = 4
_DILATE_I   = 2

# Score digit bounding box (4× scaled space) — must match process_templates.py exactly
_SCORE_MASK_X = 62
_SCORE_MASK_Y = 62
_SCORE_MASK_W = 330
_SCORE_MASK_H = 330


def _preprocess(frame: np.ndarray, x0: int, x1: int) -> np.ndarray:
    """Crop, greyscale, binarise, upscale, dilate — same pipeline as process_templates.py."""
    crop = frame[:, x0:x1]
    grey = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    _, bw = cv2.threshold(grey, _THRESHOLD, 255, cv2.THRESH_BINARY)
    bw = cv2.resize(bw, (bw.shape[1] * _SCALE, bw.shape[0] * _SCALE),
                    interpolation=cv2.INTER_NEAREST)
    kernel = np.ones((_DILATE_K, _DILATE_K), np.uint8)
    bw = cv2.dilate(bw, kernel, iterations=_DILATE_I)
    mask = np.zeros_like(bw)
    mask[_SCORE_MASK_Y:_SCORE_MASK_Y + _SCORE_MASK_H,
         _SCORE_MASK_X:_SCORE_MASK_X + _SCORE_MASK_W] = 255
    return cv2.bitwise_and(bw, mask)


def _load_templates(region: str) -> dict[str, np.ndarray]:
    """Load all saved templates for a region, keyed by filename stem."""
    path = os.path.join(TEMPLATES_DIR, region)
    templates = {}
    if not os.path.isdir(path):
        return templates
    for fname in os.listdir(path):
        label, ext = os.path.splitext(fname)
        if ext.lower() == ".png":
            img = cv2.imread(os.path.join(path, fname), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                templates[label] = img
    return templates


def _load_score_templates(side: str) -> dict[str, np.ndarray]:
    """Load score templates for one side, keyed by digit string ("0"–"9")."""
    path = os.path.join(TEMPLATES_DIR, "score")
    templates = {}
    if not os.path.isdir(path):
        return templates
    suffix = f"_{side}"
    for fname in os.listdir(path):
        stem, ext = os.path.splitext(fname)
        if ext.lower() == ".png" and stem.endswith(suffix):
            digit = stem[: -len(suffix)]
            img = cv2.imread(os.path.join(path, fname), cv2.IMREAD_GRAYSCALE)
            if img is not None:
                templates[digit] = img
    return templates


# Load templates once at import time
_TIMER_TEMPLATES        = _load_templates("timer")
_SCORE_LEFT_TEMPLATES  = _load_score_templates("left")
_SCORE_RIGHT_TEMPLATES = _load_score_templates("right")


def _best_match(region_img: np.ndarray, templates: dict[str, np.ndarray]) -> tuple[str | None, float]:
    """Slide each template over the region and return the label with the highest match score."""
    best_label, best_score = None, -1.0
    for label, tmpl in templates.items():
        if tmpl.shape[0] > region_img.shape[0] or tmpl.shape[1] > region_img.shape[1]:
            continue
        result = cv2.matchTemplate(region_img, tmpl, cv2.TM_CCOEFF_NORMED)
        score = float(result.max())
        if score > best_score:
            best_score = score
            best_label = label
    return best_label, best_score


def _find_all_digits(region_img: np.ndarray, templates: dict[str, np.ndarray],
                     min_spacing: int = 80) -> list[tuple[int, str]]:
    """
    Find all digit occurrences in a region using template matching.
    Returns a list of (x_position, label) sorted left to right.

    For each pixel position, only the highest-scoring template is kept,
    then non-maximum suppression removes duplicates within min_spacing.
    """
    # Build a score map: x -> (score, label)
    best: dict[int, tuple[float, str]] = {}
    for label, tmpl in templates.items():
        if tmpl.shape[0] > region_img.shape[0] or tmpl.shape[1] > region_img.shape[1]:
            continue
        result = cv2.matchTemplate(region_img, tmpl, cv2.TM_CCOEFF_NORMED)
        rows, cols = np.where(result >= MATCH_THRESHOLD)
        for row, x in zip(rows, cols):
            score = float(result[row, x])
            if x not in best or score > best[x][0]:
                best[x] = (score, label)

    # Sort by position, then suppress duplicates within min_spacing (keep highest score)
    hits = sorted(best.items())   # [(x, (score, label)), ...]
    suppressed: list[tuple[int, str]] = []
    for x, (score, label) in hits:
        if suppressed and x - suppressed[-1][0] < min_spacing:
            # Replace if this hit scores higher than the current winner in this window
            prev_x = suppressed[-1][0]
            prev_score = best[prev_x][0]
            if score > prev_score:
                suppressed[-1] = (x, label)
        else:
            suppressed.append((x, label))

    return suppressed


def _read_score(frame: np.ndarray, x_range: tuple[int, int],
                templates: dict[str, np.ndarray]) -> int | None:
    """Read a single team's score from the given x region."""
    if not templates:
        return None
    img = _preprocess(frame, *x_range)
    digits = _find_all_digits(img, templates)
    if not digits:
        return None
    number = "".join(label for _, label in digits if label.isdigit())
    return int(number) if number else None


def _read_timer(frame: np.ndarray) -> int | None:
    """Read the timer and return remaining seconds, e.g. '3:46' → 226.

    Uses fixed character slots rather than sliding window — the M:SS layout
    is always in the same position within the scaled timer strip.
    Slot boundaries were determined empirically from capture data.
    """
    if not _TIMER_TEMPLATES:
        return None
    img = _preprocess(frame, *TIMER_X)

    # Fixed x-slots for each character in the scaled (4×) timer image
    slots = [
        (0,   400,  "digit"),   # minute (M)
        (380, 465,  "colon"),   # colon  (:)
        (440, 670,  "digit"),   # tens of seconds (S1)
        (640, 900,  "digit"),   # ones of seconds (S2)
    ]

    chars = []
    for x0, x1, kind in slots:
        slot_img = img[:, x0:x1]
        pool = {k: v for k, v in _TIMER_TEMPLATES.items()
                if (kind == "colon") == (k == "colon")}
        label, score = _best_match(slot_img, pool)
        if label is None or score < MATCH_THRESHOLD:
            return None
        chars.append(label)

    minute, _, tens, ones = chars
    token = f"{minute}:{tens}{ones}"
    match = re.fullmatch(r"(\d):([0-5]\d)", token)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2))
    return None


@dataclass
class HudReading:
    blue:   int | None   # Blue team score  (None if templates not yet captured)
    orange: int | None   # Orange team score
    time:   int | None   # Remaining time in seconds


def read_hud(frame: np.ndarray) -> HudReading:
    """Read blue score, orange score, and remaining time from a HUD frame."""
    return HudReading(
        blue=_read_score(frame, BLUE_X, _SCORE_LEFT_TEMPLATES),
        orange=_read_score(frame, ORANGE_X, _SCORE_RIGHT_TEMPLATES),
        time=_read_timer(frame),
    )


if __name__ == "__main__":
    from capture import grab_frame, save_frame

    save_frame()
    frame = grab_frame()
    reading = read_hud(frame)
    print(f"Blue: {reading.blue}  Orange: {reading.orange}  Time: {reading.time}s")
    if not _TIMER_TEMPLATES and not _SCORE_LEFT_TEMPLATES and not _SCORE_RIGHT_TEMPLATES:
        print("\nNo templates found. Run capture_templates.py first:")
        print("  python capture_templates.py --region timer")
        print("  python capture_templates.py --region score")
