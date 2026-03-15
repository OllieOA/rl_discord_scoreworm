"""
Full-screen session recorder.

Takes a screenshot of the entire Rocket League monitor every second.
Each run creates a new timestamped session folder under sessions/.

Usage:
    uv run python tools/record_session.py          # captures every 1s
    uv run python tools/record_session.py --interval 2
    Stop with Ctrl+C.
"""

import argparse
import os
import time
from datetime import datetime

import mss
import mss.tools

SESSIONS_DIR = "sessions"


def _centre_monitor(sct: mss.base.MSSBase) -> dict:
    screens = sorted(sct.monitors[1:], key=lambda m: m["left"])
    if len(screens) != 3:
        print(f"Warning: expected 3 monitors, found {len(screens)}. Using index {len(screens) // 2}.")
    return screens[len(screens) // 2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=1.0,
                        help="seconds between captures (default: 1)")
    args = parser.parse_args()

    session_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_dir = os.path.join(SESSIONS_DIR, session_name)
    os.makedirs(session_dir, exist_ok=True)

    print(f"Recording to {session_dir}/  —  Ctrl+C to stop")

    frame_num = 0
    with mss.mss() as sct:
        monitor = _centre_monitor(sct)
        print(f"Monitor: left={monitor['left']} top={monitor['top']} "
              f"{monitor['width']}x{monitor['height']}")

        try:
            while True:
                raw = sct.grab(monitor)
                path = os.path.join(session_dir, f"{frame_num:05d}.png")
                mss.tools.to_png(raw.rgb, raw.size, output=path)
                print(f"  {frame_num:05d}.png", end="\r")
                frame_num += 1
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\nStopped. {frame_num} frames saved to {session_dir}/")


if __name__ == "__main__":
    main()
