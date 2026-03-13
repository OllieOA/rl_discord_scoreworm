"""Screen capture for the Rocket League score/timer HUD."""

import mss
import mss.tools
import numpy as np
from PIL import Image

# ── HUD crop (relative to the target monitor's top-left corner) ───────────────
# Rocket League (2560×1440): the score + timer HUD sits centred at the very top.
# Adjust these if the capture misses digits or grabs extra noise.
HUD_LEFT   = 1040   # x offset from the monitor's left edge
HUD_TOP    = 0      # y offset from the monitor's top edge
HUD_WIDTH  = 480    # pixels wide
HUD_HEIGHT = 110    # pixels tall
# ─────────────────────────────────────────────────────────────────────────────


def _centre_monitor(sct: mss.base.MSSBase) -> dict:
    """Return the mss monitor dict for the centre screen (by horizontal position)."""
    # monitors[0] is the combined virtual screen; [1:] are individual monitors.
    screens = sorted(sct.monitors[1:], key=lambda m: m["left"])
    if len(screens) != 3:
        print(f"Warning: expected 3 monitors, found {len(screens)}. Using index {len(screens) // 2}.")
    return screens[len(screens) // 2]


def _hud_region(monitor: dict) -> dict:
    """Translate HUD offsets to absolute virtual-desktop coordinates."""
    return {
        "left":   monitor["left"] + HUD_LEFT,
        "top":    monitor["top"]  + HUD_TOP,
        "width":  HUD_WIDTH,
        "height": HUD_HEIGHT,
    }


def grab_frame() -> np.ndarray:
    """Capture the HUD region and return it as an RGB numpy array."""
    with mss.mss() as sct:
        region = _hud_region(_centre_monitor(sct))
        raw = sct.grab(region)
    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    return np.array(img)


def save_frame(path: str = "hud_preview.png") -> None:
    """Capture the HUD region and save it to *path* for visual calibration."""
    with mss.mss() as sct:
        monitor = _centre_monitor(sct)
        region = _hud_region(monitor)
        print(f"Centre monitor: left={monitor['left']} top={monitor['top']} "
              f"{monitor['width']}x{monitor['height']}")
        print(f"Capturing region: {region}")
        raw = sct.grab(region)
    mss.tools.to_png(raw.rgb, raw.size, output=path)
    print(f"Saved HUD capture to {path}")


if __name__ == "__main__":
    save_frame()
