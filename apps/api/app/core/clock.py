"""Replay cursor logic. The clock only ever reveals completed bars up to the
cursor; everything after it is invisible to the client and to the fill engine."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.core.types import BAR_SECONDS, Bar, et

MIN_SPEED = 1.0
MAX_SPEED = 60.0


class ClockStatus(StrEnum):
    PAUSED = "paused"
    PLAYING = "playing"
    FINISHED = "finished"


@dataclass
class ReplayClock:
    bars: list[Bar]
    index: int = 0
    speed: float = 10.0
    status: ClockStatus = ClockStatus.PAUSED
    _times: list[datetime] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.bars:
            raise ValueError("replay needs at least one bar")
        self._times = [b.ts for b in self.bars]
        self.index = min(max(self.index, 0), len(self.bars) - 1)
        self.speed = clamp_speed(self.speed)

    @property
    def cursor(self) -> Bar:
        return self.bars[self.index]

    @property
    def interval_seconds(self) -> float:
        """Wall-clock seconds between bars; 1x is real time."""
        return BAR_SECONDS / self.speed

    @property
    def at_end(self) -> bool:
        return self.index >= len(self.bars) - 1

    def visible(self) -> list[Bar]:
        return self.bars[: self.index + 1]

    def advance(self) -> Bar | None:
        if self.at_end:
            self.status = ClockStatus.FINISHED
            return None
        self.index += 1
        if self.at_end:
            self.status = ClockStatus.FINISHED
        return self.bars[self.index]

    def index_at(self, ts: datetime) -> int:
        """Index of the last bar starting at or before `ts`."""
        return max(0, bisect.bisect_right(self._times, ts) - 1)

    def is_day_end(self, i: int | None = None) -> bool:
        i = self.index if i is None else i
        if i >= len(self.bars) - 1:
            return True
        return et(self.bars[i].ts).date() != et(self.bars[i + 1].ts).date()

    def next_day_index(self) -> int | None:
        """Index of the first bar of the next trading day, if the replay spans one."""
        today = et(self.cursor.ts).date()
        for i in range(self.index + 1, len(self.bars)):
            if et(self.bars[i].ts).date() != today:
                return i
        return None

    def set_speed(self, speed: float) -> None:
        self.speed = clamp_speed(speed)

    def state(self) -> dict:
        return {
            "cursor_ts": int(self.cursor.ts.timestamp()),
            "index": self.index,
            "total": len(self.bars),
            "speed": self.speed,
            "status": self.status.value,
        }


def clamp_speed(speed: float) -> float:
    return min(MAX_SPEED, max(MIN_SPEED, float(speed)))
