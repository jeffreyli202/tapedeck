from datetime import datetime, timedelta

import pytest

from app.core.types import ET, Bar

T0 = datetime(2024, 3, 15, 9, 30, tzinfo=ET)


def make_bar(i: int, o: float, h: float, low: float, c: float, start: datetime = T0) -> Bar:
    return Bar(start + timedelta(minutes=i), o, h, low, c, 1000)


@pytest.fixture
def bar():
    return make_bar
