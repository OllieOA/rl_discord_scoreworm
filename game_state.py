"""
Game state machine for Rocket League score tracking.

States:
    IDLE      — waiting for a new game (score 0-0, timer 5:00)
    IN_GAME   — game in progress; recording goal timestamps
    OVERTIME  — timer counting up from 0:00; ends when scores become uneven
    GAME_OVER — end condition met; fires on_game_over callback

End conditions:
    Any state   — 3 consecutive all-None frames (post-match scoreboard replacing HUD)
    OT entry    — timer 0:00 with level scores sets _ot_pending; first frame where
                  scores are readable but timer is None triggers OVERTIME transition

Usage:
    def handle_game_over(goals):
        print(goals)  # list of GoalEvent

    tracker = GameTracker(on_game_over=handle_game_over)
    tracker.run()   # blocking loop; Ctrl-C to stop
"""

import glob
import os
import time
from dataclasses import dataclass, field
from enum import Enum, auto

import cv2

from capture import grab_frame
from ocr import HudReading, read_hud

POLL_INTERVAL  = 0.5    # seconds between HUD reads
GAME_DURATION  = 300    # seconds (5:00)
LOG_DIR        = "logs"
LOG_MAX_FRAMES = 50


class State(Enum):
    IDLE     = auto()
    IN_GAME  = auto()
    OVERTIME = auto()


@dataclass
class GoalEvent:
    team:           str   # "blue" or "orange"
    time_remaining: int   # seconds left (0 during overtime)
    game_time:      int   # elapsed seconds since kick-off; >300 means overtime


@dataclass
class GameTracker:
    on_game_over: callable   # called with (goals: list[GoalEvent], end_type: str) when game ends

    _state:              State      = field(default=State.IDLE, init=False)
    _goals:              list       = field(default_factory=list, init=False)
    _prev:               HudReading = field(default=None, init=False)
    _none_streak:        int        = field(default=0, init=False)
    _ot_pending:         bool       = field(default=False, init=False)
    _timer_reached_zero: bool       = field(default=False, init=False)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _transition(self, new_state: State) -> None:
        print(f"[state] {self._state.name} → {new_state.name}")
        self._state = new_state

    def _end_game(self) -> None:
        if self._state is State.OVERTIME:
            end_type = "overtime"
        elif self._timer_reached_zero:
            end_type = "normal"
        else:
            end_type = "forfeit"
        self.on_game_over(list(self._goals), end_type)
        self._goals              = []
        self._prev               = None
        self._ot_pending         = False
        self._timer_reached_zero = False
        self._transition(State.IDLE)

    def _detect_goal(self, reading: HudReading, game_time: int) -> None:
        """Compare current reading to previous; record any score increment."""
        if self._prev is None:
            return
        if reading.blue == self._prev.blue + 1:
            goal = GoalEvent("blue", reading.time or 0, game_time)
            self._goals.append(goal)
            print(f"[goal] BLUE   — {reading.blue}-{reading.orange}  game_time={game_time}s")
        elif reading.orange == self._prev.orange + 1:
            goal = GoalEvent("orange", reading.time or 0, game_time)
            self._goals.append(goal)
            print(f"[goal] ORANGE — {reading.blue}-{reading.orange}  game_time={game_time}s")

    # ── per-tick logic ───────────────────────────────────────────────────────

    def _tick(self, reading: HudReading) -> None:
        # All-None: track streak; end game at threshold from any non-IDLE state
        if reading.blue is None and reading.orange is None and reading.time is None:
            self._none_streak += 1
            if self._none_streak >= 3 and self._state is not State.IDLE:
                print("[probe] 3 consecutive None readings — scoreboard likely gone, ending game")
                self._end_game()
            return
        self._none_streak = 0

        # Any-one-None: partial read — check for OVERTIME banner; skip without updating _prev
        if reading.blue is None or reading.orange is None or reading.time is None:
            if (self._ot_pending and reading.time is None
                    and reading.blue is not None and reading.orange is not None):
                self._ot_pending = False
                self._transition(State.OVERTIME)
            return

        # Full reading available
        if self._state is State.IDLE:
            if reading.blue == 0 and reading.orange == 0 and reading.time == GAME_DURATION:
                self._goals = []
                self._prev  = reading
                self._transition(State.IN_GAME)

        elif self._state is State.IN_GAME:
            # Corrupt-read guard: discard impossible score transitions
            if self._prev is not None and (
                reading.blue < self._prev.blue
                or reading.orange < self._prev.orange
                or reading.blue > self._prev.blue + 1
                or reading.orange > self._prev.orange + 1
            ):
                return

            game_time = GAME_DURATION - reading.time
            self._detect_goal(reading, game_time)
            self._prev = reading

            if reading.time == 0:
                self._timer_reached_zero = True
                if reading.blue == reading.orange:
                    self._ot_pending = True   # wait for OVERTIME banner
                else:
                    self._ot_pending = False  # juggling goal — scores uneven at buzzer

        elif self._state is State.OVERTIME:
            # Corrupt-read guard
            if self._prev is not None and (
                reading.blue < self._prev.blue
                or reading.orange < self._prev.orange
                or reading.blue > self._prev.blue + 1
                or reading.orange > self._prev.orange + 1
            ):
                return

            # Timer counts UP; game_time = regulation duration + overtime elapsed
            game_time = GAME_DURATION + reading.time
            self._detect_goal(reading, game_time)
            self._prev = reading

    # ── logging ──────────────────────────────────────────────────────────────

    @staticmethod
    def _save_frame(frame) -> None:
        """Save frame to logs/ and delete oldest if over LOG_MAX_FRAMES."""
        os.makedirs(LOG_DIR, exist_ok=True)
        filename = os.path.join(LOG_DIR, f"{time.strftime('%H%M%S')}_{int(time.time() * 1000) % 1000:03d}.png")
        cv2.imwrite(filename, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        frames = sorted(glob.glob(os.path.join(LOG_DIR, "*.png")))
        for old in frames[:-LOG_MAX_FRAMES]:
            os.remove(old)

    @staticmethod
    def _log_reading(reading: HudReading) -> None:
        t = f"{reading.time // 60}:{reading.time % 60:02d}" if reading.time is not None else "None"
        print(f"[probe] state — blue={reading.blue}  orange={reading.orange}  time={t}")

    # ── replay ───────────────────────────────────────────────────────────────

    def replay(self, readings) -> None:
        """Drive the state machine from a pre-recorded sequence of HudReadings."""
        for reading in readings:
            self._log_reading(reading)
            self._tick(reading)

    # ── main loop ────────────────────────────────────────────────────────────

    def run(self) -> None:
        print("Tracker started — waiting for a game (looking for 0-0 at 5:00)…")
        try:
            while True:
                frame   = grab_frame()
                reading = read_hud(frame)
                self._log_reading(reading)
                self._save_frame(frame)
                self._tick(reading)
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("\nTracker stopped.")


if __name__ == "__main__":
    def _print_results(goals: list[GoalEvent], end_type: str) -> None:
        print(f"\n── Game over ({end_type}) ──")
        for g in goals:
            mins, secs = divmod(g.game_time, 60)
            ot = " (OT)" if g.game_time > GAME_DURATION else ""
            print(f"  {g.team.upper():6s}  {mins}:{secs:02d}{ot}")
        print(f"  Total goals: {len(goals)}")

    GameTracker(on_game_over=_print_results).run()
