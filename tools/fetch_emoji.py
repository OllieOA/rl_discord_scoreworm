"""Download Twemoji PNG assets by emoji character or codepoint.

Usage:
    uv run python tools/fetch_emoji.py 🏆 ❌ 🇧🇷
    uv run python tools/fetch_emoji.py 1f3c6 274c 1f1e7-1f1f7

Assets are saved to assets/emoji/<codepoint>.png.
Twemoji is the open-source emoji set used by Discord (Apache 2.0).
"""

import os
import sys
import urllib.request
from pathlib import Path

TWEMOJI_CDN = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/{codepoint}.png"
ASSETS_DIR  = Path(__file__).parent.parent / "assets" / "emoji"


def codepoint_for(emoji_char: str) -> str:
    """Convert an emoji character to its Twemoji codepoint filename stem.

    Strips variation selectors (U+FE0F) which Twemoji omits from filenames.
    Multi-codepoint sequences (e.g. flags) are joined with hyphens.
    """
    return "-".join(f"{ord(c):x}" for c in emoji_char if ord(c) != 0xFE0F)


def fetch(codepoint: str) -> Path:
    """Download one emoji PNG; returns the saved path."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    url  = TWEMOJI_CDN.format(codepoint=codepoint)
    dest = ASSETS_DIR / f"{codepoint}.png"
    print(f"  {url}")
    print(f"  -> {dest}")
    urllib.request.urlretrieve(url, dest)
    return dest


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: fetch_emoji.py <emoji_or_codepoint> [...]")
        print("  e.g.  fetch_emoji.py 🏆 ❌ 🇧🇷")
        print("  e.g.  fetch_emoji.py 1f3c6 274c 1f1e7-1f1f7")
        sys.exit(1)

    for arg in sys.argv[1:]:
        # Treat as raw codepoint string if it looks like hex (with optional hyphens)
        is_codepoint = all(c in "0123456789abcdefABCDEF-" for c in arg)
        cp = arg if is_codepoint else codepoint_for(arg)
        print(f"Fetching {arg!r} ({cp})...")
        try:
            fetch(cp)
            print("  OK")
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
