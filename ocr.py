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

# Multiple binarisation thresholds tried per query image.  Templates are built
# at _THRESHOLD=128; varying the query threshold compensates for background
# transparency shifts.  170+ cleanly rejects the overtime orange panel
# (greyscale ≈158) without needing a separate blue-channel path.
_BINARIZE_THRESHOLDS = (110, 128, 150, 170, 190)

# Score digit bounding box (4× scaled space) — must match process_templates.py exactly
_SCORE_MASK_X = 62
_SCORE_MASK_Y = 62
_SCORE_MASK_W = 330
_SCORE_MASK_H = 330


def _preprocess(frame: np.ndarray, x0: int, x1: int,
                threshold: int = _THRESHOLD) -> np.ndarray:
    """Crop, greyscale, binarise, upscale, dilate — same pipeline as process_templates.py."""
    crop = frame[:, x0:x1]
    grey = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    _, bw = cv2.threshold(grey, threshold, 255, cv2.THRESH_BINARY)
    bw = cv2.resize(bw, (bw.shape[1] * _SCALE, bw.shape[0] * _SCALE),
                    interpolation=cv2.INTER_NEAREST)
    kernel = np.ones((_DILATE_K, _DILATE_K), np.uint8)
    return cv2.dilate(bw, kernel, iterations=_DILATE_I)


def _apply_score_mask(img: np.ndarray) -> np.ndarray:
    """Zero out everything outside the expected digit bounding box."""
    mask = np.zeros_like(img)
    mask[_SCORE_MASK_Y:_SCORE_MASK_Y + _SCORE_MASK_H,
         _SCORE_MASK_X:_SCORE_MASK_X + _SCORE_MASK_W] = 255
    return cv2.bitwise_and(img, mask)


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


# ── Batched NCC for scores ─────────────────────────────────────────────────────
# All score templates are the same shape (110×110 px crop → 440×440 after 4×
# scaling with mask).  Pre-normalising them into a single float32 matrix lets us
# replace 100 serial cv2.matchTemplate calls with one BLAS matmul, reducing
# score read time from ~17 ms to < 1 ms per side.

@dataclass
class _NccBatch:
    """Pre-normalised template matrix for a set of same-shape score templates."""
    labels: list[str]    # label[i] corresponds to row i of mat
    mat:    np.ndarray   # shape (N, H*W), rows are L2-normalised float32 vectors


def _build_ncc_batch(templates: dict[str, np.ndarray]) -> _NccBatch | None:
    """Normalise all templates in *templates* into a single matrix.

    Templates must all share the same shape; any that differ are skipped with a
    warning so a shape mismatch never silently corrupts results.
    """
    if not templates:
        return None

    labels = sorted(templates.keys(), key=lambda k: int(k))

    # Determine expected shape from the first template
    first_shape = next(iter(templates.values())).shape
    vecs: list[np.ndarray] = []
    kept_labels: list[str] = []

    for label in labels:
        tmpl = templates[label]
        if tmpl.shape != first_shape:
            print(f"[ocr] WARNING: score template '{label}' shape {tmpl.shape} "
                  f"!= expected {first_shape} — skipped from NCC batch")
            continue
        vec = tmpl.astype(np.float32).ravel()
        vec -= vec.mean()
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        vecs.append(vec)
        kept_labels.append(label)

    if not vecs:
        return None
    return _NccBatch(labels=kept_labels, mat=np.stack(vecs))


def _best_match_batched(img: np.ndarray, batch: _NccBatch) -> tuple[str | None, float]:
    """Return the best-matching label via a single batched NCC (matmul).

    Equivalent to running cv2.TM_CCOEFF_NORMED with a same-size template for
    each row in batch.mat, but ~34× faster because it uses one BLAS call.
    """
    q = img.astype(np.float32).ravel()
    q -= q.mean()
    norm = float(np.linalg.norm(q))
    if norm == 0:
        return None, 0.0
    q /= norm
    scores: np.ndarray = batch.mat @ q   # shape (N,)
    idx = int(scores.argmax())
    return batch.labels[idx], float(scores[idx])


_SCORE_LEFT_BATCH  = _build_ncc_batch(_SCORE_LEFT_TEMPLATES)
_SCORE_RIGHT_BATCH = _build_ncc_batch(_SCORE_RIGHT_TEMPLATES)
# ──────────────────────────────────────────────────────────────────────────────


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
                batch: _NccBatch | None) -> int | None:
    """Read a single team's score from the given x region using batched NCC.

    Tries each threshold in _BINARIZE_THRESHOLDS and accepts the highest-
    confidence result.  High thresholds (170+) naturally reject the overtime
    orange panel background (greyscale ≈158) without needing a separate
    blue-channel path.
    """
    if batch is None:
        return None
    best_label, best_score = None, -1.0
    for thresh in _BINARIZE_THRESHOLDS:
        img = _apply_score_mask(_preprocess(frame, *x_range, thresh))
        label, score = _best_match_batched(img, batch)
        if label is not None and score > best_score:
            best_score = score
            best_label = label
    if best_label is None or best_score < MATCH_THRESHOLD:
        return None
    return int(best_label)


_PLUS_TEMPLATE  = _TIMER_TEMPLATES.get("plus")
_COLON_TEMPLATE = _TIMER_TEMPLATES.get("colon")

# Minimum NCC score to accept a + template hit as an overtime indicator.
# Overtime frames score 0.925-1.000; regular-time spurious hits score ≤ 0.62.
_PLUS_MATCH_THRESHOLD = 0.75

# Minimum colon NCC score required to confirm a regular-time M:SS reading.
# Real timers score 0.75-1.00; the "OVERTIME" text frame scores ≈0.55 because
# no colon is present in the timer strip.  This gate replaces the digit-level
# min_score that was previously needed to reject spurious '1' hits from the
# OVERTIME text.
_TIMER_COLON_MIN_SCORE = 0.65


def _read_timer(frame: np.ndarray) -> int | None:
    """Read the timer; returns seconds.

    Regular time counts down from 5:00 (returns remaining seconds).
    Overtime counts up with a '+' prefix; returns elapsed seconds.
    Returns None when the display is unreadable (e.g. the 'OVERTIME' text
    frame, or when any required zone has no confident digit match).

    Zone layout — regular time (M:SS):
      minute: x < 380   tens: 380-580   ones: 580-900

    Zone layout — overtime single-digit minute (+M:SS):
      minute: x < 520   sec_tens: 540-710   sec_ones: 710-960

    Zone layout — overtime double-digit minute (+MM:SS):
      min_tens: x < 380   min_ones: 380-560
      sec_tens: 620-820   sec_ones: 820-1040

    The timer uses a single binarisation threshold (standard 128).  The colon
    gate rejects the "OVERTIME" text frame before digit zones are checked, so
    multi-threshold is not needed here (unlike scores, where the orange panel
    requires a high threshold to avoid background flooding).
    """
    if not _TIMER_TEMPLATES:
        return None
    digit_pool = {k: v for k, v in _TIMER_TEMPLATES.items()
                  if k not in ("colon", "plus")}

    img = _preprocess(frame, *TIMER_X)

    # Build x_center -> (score, label) map across the full strip.
    # Key on template centre so wide glyphs are assigned to the zone that
    # contains the actual digit content, not where the left edge happens to be.
    best: dict[int, tuple[float, str]] = {}
    for label, tmpl in digit_pool.items():
        if tmpl.shape[0] > img.shape[0] or tmpl.shape[1] > img.shape[1]:
            continue
        result = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
        half_w = tmpl.shape[1] // 2
        rows, cols = np.where(result >= MATCH_THRESHOLD)
        for row, x in zip(rows, cols):
            score = float(result[row, x])
            x_center = x + half_w
            if x_center not in best or score > best[x_center][0]:
                best[x_center] = (score, label)

    def best_in_zone(x0: int, x1: int, min_score: float = MATCH_THRESHOLD) -> str | None:
        candidates = [(s, l) for x, (s, l) in best.items()
                      if x0 <= x < x1 and s >= min_score]
        return max(candidates, default=(None, None))[1]

    # ── Detect overtime via + template ────────────────────────────────────────
    in_overtime = bool(
        _PLUS_TEMPLATE is not None
        and cv2.matchTemplate(img, _PLUS_TEMPLATE, cv2.TM_CCOEFF_NORMED).max()
            >= _PLUS_MATCH_THRESHOLD
    )

    if in_overtime:
        # Determine 1-digit vs 2-digit minute by checking for a strong genuine
        # digit match in the min_ones zone (380-560).  In +M:SS the tens zone
        # only receives a low-confidence spill from the minute digit (~0.75),
        # whereas in +MM:SS it contains a real digit scoring ~0.97.
        min_ones_score = max(
            (s for x, (s, _) in best.items() if 380 <= x < 560),
            default=0.0,
        )
        if min_ones_score >= 0.85:
            # ── Double-digit minute: +MM:SS ───────────────────────────────────
            min_tens = best_in_zone(0,   380)
            min_ones = best_in_zone(380, 560)
            sec_tens = best_in_zone(620, 820)
            sec_ones = best_in_zone(820, 1040)
            if None in (min_tens, min_ones, sec_tens, sec_ones):
                return None
            try:
                minutes = int(min_tens) * 10 + int(min_ones)
                seconds = int(sec_tens) * 10 + int(sec_ones)
                if not (0 <= seconds <= 59):
                    return None
                return minutes * 60 + seconds
            except (ValueError, TypeError):
                return None
        else:
            # ── Single-digit minute: +M:SS ────────────────────────────────────
            minute   = best_in_zone(0,   520)
            sec_tens = best_in_zone(540, 710)
            sec_ones = best_in_zone(710, 960)
            if None in (minute, sec_tens, sec_ones):
                return None
            match = re.fullmatch(r"(\d):([0-5]\d)", f"{minute}:{sec_tens}{sec_ones}")
            if match:
                return int(match.group(1)) * 60 + int(match.group(2))
            return None
    else:
        # ── Regular time: M:SS (counts down from 5:00) ───────────────────────
        # Gate on the colon: real timers score ≥0.75; the "OVERTIME" text frame
        # has no colon and scores ≈0.55, so it is correctly rejected here.
        colon_score = 0.0
        if (_COLON_TEMPLATE is not None
                and _COLON_TEMPLATE.shape[0] <= img.shape[0]
                and _COLON_TEMPLATE.shape[1] <= img.shape[1]):
            colon_score = float(
                cv2.matchTemplate(img, _COLON_TEMPLATE, cv2.TM_CCOEFF_NORMED).max()
            )
        if colon_score < _TIMER_COLON_MIN_SCORE:
            return None

        minute = best_in_zone(0,   380)
        tens   = best_in_zone(380, 580)
        ones   = best_in_zone(580, 900)
        if None in (minute, tens, ones):
            return None
        match = re.fullmatch(r"(\d):([0-5]\d)", f"{minute}:{tens}{ones}")
        if match:
            return int(match.group(1)) * 60 + int(match.group(2))
        return None


@dataclass
class HudReading:
    blue:   int | None   # Blue team score  (None if templates not yet captured)
    orange: int | None   # Orange team score
    time:   int | None   # Remaining time in seconds


def detect_left_colour(hud_frame: np.ndarray) -> str:
    """Detect which team colour is on the left side of the HUD.

    Args:
        hud_frame: RGB numpy array of shape (110, 480) — the full HUD crop.

    Returns:
        "blue" or "orange"
    """
    left_region = hud_frame[:, 0:110, :]        # shape (110, 110, 3), RGB
    mean_rgb = left_region.mean(axis=(0, 1))    # [R, G, B]
    # Blue panel: B channel dominant. Orange panel: R channel dominant.
    return "blue" if mean_rgb[2] > mean_rgb[0] else "orange"


def detect_winner(frame: np.ndarray) -> tuple[str | None, bool]:
    """Detect the winner and forfeit flag from a full-screen result card frame.

    Args:
        frame: RGB numpy array of the full screen (2560x1440).

    Returns:
        (winner, is_forfeit) where winner is "blue" (left side of HUD wins),
        "orange" (right side wins), or None if the result screen is not
        detected.  is_forfeit is True when a forfeit indicator is visible.

    Stub: always returns (None, False) until result-screen templates are built.
    """
    return (None, False)


def read_hud(frame: np.ndarray) -> HudReading:
    """Read blue score, orange score, and remaining time from a HUD frame."""
    return HudReading(
        blue=_read_score(frame, BLUE_X, _SCORE_LEFT_BATCH),
        orange=_read_score(frame, ORANGE_X, _SCORE_RIGHT_BATCH),
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
