"""
Score template raw capture utility.

Captures the HUD score region once per goal, incrementally.
Score goals one at a time — capture 0 = score 0, capture 1 = score 1, etc.

Use --side to specify which side of the HUD the score appears on:
  left  — score is in BLUE_X  (0–110),   player is on Blue team
  right — score is in ORANGE_X (370–480), player is on Orange team

Each capture saves:
  templates/raw/capture_{i}_{side}.png  — full raw HUD frame (RGB)

To convert raw captures into score templates, run:
    python process_templates.py

IMPORTANT: Will abort if ANY raw capture for the given side already exists.
Delete all templates/raw/capture_*_{side}.png files before re-running.

Usage:
    python capture_templates.py --side right           # blue score on right
    python capture_templates.py --side left --count 9
"""

import argparse
import glob
import os
import time

import cv2

from capture import grab_frame

TEMPLATES_DIR = "templates"
INTERVAL = 20   # seconds between captures

SIDE_X = {
    "left":  (0, 110),
    "right": (370, 480),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--side",     choices=["left", "right"], default="left",
                        help="which HUD side the score appears on (default: left)")
    parser.add_argument("--count",    type=int, default=10, help="number of captures (default: 10)")
    parser.add_argument("--interval", type=int, default=INTERVAL, help="seconds between captures")
    args = parser.parse_args()

    raw_dir = os.path.join(TEMPLATES_DIR, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    existing = glob.glob(os.path.join(raw_dir, f"capture_*_{args.side}.png"))
    if existing:
        print(f"Aborting: {len(existing)} raw capture(s) already exist for side='{args.side}'.")
        print(f"Delete all templates/raw/capture_*_{args.side}.png files before re-running.")
        return

    print(f"Side: {args.side} — capturing from X={SIDE_X[args.side]}")
    print("Starting in 3 seconds — alt-tab back to Rocket League!")
    time.sleep(3)

    for i in range(args.count):
        frame = grab_frame()
        raw_path = os.path.join(raw_dir, f"capture_{i}_{args.side}.png")
        cv2.imwrite(raw_path, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        print(f"  Saved capture_{i}_{args.side}.png  (score should be {i})")

        if i < args.count - 1:
            for remaining in range(args.interval, 0, -1):
                print(f"    next capture in {remaining}s...", end="\r")
                time.sleep(1)
            print()

    print(f"\nDone. {args.count} raw frames saved to {raw_dir}/")
    print("Run: python process_templates.py")


if __name__ == "__main__":
    main()
