"""OCC option symbology, e.g. SPY240315C00500000."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

_OCC_RE = re.compile(r"^([A-Z]{1,6})(\d{6})([CP])(\d{8})$")
OPTION_MULTIPLIER = 100


@dataclass(frozen=True, slots=True)
class OptionSpec:
    underlying: str
    expiry: date
    right: str  # "C" or "P"
    strike: float

    @property
    def symbol(self) -> str:
        return occ_symbol(self.underlying, self.expiry, self.right, self.strike)


def occ_symbol(underlying: str, expiry: date, right: str, strike: float) -> str:
    return f"{underlying}{expiry:%y%m%d}{right}{int(round(strike * 1000)):08d}"


def parse_occ(symbol: str) -> OptionSpec | None:
    m = _OCC_RE.match(symbol)
    if not m:
        return None
    root, ymd, right, strike = m.groups()
    expiry = datetime.strptime(ymd, "%y%m%d").date()
    return OptionSpec(root, expiry, right, int(strike) / 1000)


def is_option(symbol: str) -> bool:
    return _OCC_RE.match(symbol) is not None


def multiplier(symbol: str) -> int:
    return OPTION_MULTIPLIER if is_option(symbol) else 1


def underlying_of(symbol: str) -> str:
    spec = parse_occ(symbol)
    return spec.underlying if spec else symbol
