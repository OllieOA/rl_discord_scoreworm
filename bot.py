"""
Discord bot — posts the score worm image when a game ends.

Required environment variables (put these in a .env file):
    DISCORD_TOKEN       — bot token from the Discord developer portal
    DISCORD_CHANNEL_ID  — ID of the channel to post images in

The bot starts the GameTracker in a background thread on login.
When a game ends, the score worm is generated and posted automatically.
"""

import asyncio
import io
import os
import threading

import discord
from dotenv import load_dotenv

from game_state import GameTracker, GoalEvent
from scoreworm import generate

load_dotenv()

TOKEN      = os.environ["DISCORD_TOKEN"]
CHANNEL_ID = int(os.environ["DISCORD_CHANNEL_ID"])

intents = discord.Intents.default()
client  = discord.Client(intents=intents)


def _to_bytes(img) -> io.BytesIO:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


async def _post_scoreworm(goals: list[GoalEvent], end_type: str) -> None:
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print(f"[bot] Channel {CHANNEL_ID} not found — check DISCORD_CHANNEL_ID")
        return

    left  = sum(1 for g in goals if g.team == "blue")
    right = sum(1 for g in goals if g.team == "orange")

    img = generate(goals, end_type=end_type)
    buf = _to_bytes(img)
    suffix = f" *({end_type})*" if end_type != "normal" else ""
    await channel.send(
        content=f"**Left {left} \u2013 {right} Right**{suffix}",
        file=discord.File(buf, filename="scoreworm.png"),
    )
    print(f"[bot] Posted score worm ({left}-{right}, {end_type})")


def _on_game_over(goals: list[GoalEvent], end_type: str) -> None:
    """Called from the tracker thread — schedules the Discord post on the bot loop."""
    future = asyncio.run_coroutine_threadsafe(
        _post_scoreworm(goals, end_type), client.loop
    )
    try:
        future.result(timeout=30)
    except Exception as e:
        print(f"[bot] Failed to post score worm: {e}")


@client.event
async def on_ready():
    print(f"[bot] Logged in as {client.user}")
    tracker = GameTracker(on_game_over=_on_game_over)
    thread  = threading.Thread(target=tracker.run, daemon=True)
    thread.start()


@client.event
async def on_disconnect():
    print("[bot] Disconnected from Discord")


if __name__ == "__main__":
    client.run(TOKEN)
