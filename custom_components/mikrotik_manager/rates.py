"""Bit-rate computation from interface byte counters (pure python, no HA imports).

The upstream endpoint is assumed to return cumulative counters. If it turns out to
return per-interval deltas instead, set COUNTERS_ARE_CUMULATIVE = False and nothing
else needs to change.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

COUNTERS_ARE_CUMULATIVE = True


def parse_time(value: Any) -> float | None:
    """ISO timestamp (or epoch number) to epoch seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def byte_delta(prev: Any, cur: Any) -> int | float | None:
    """Bytes transferred between two samples of one counter; None if unusable."""
    if not isinstance(cur, (int, float)):
        return None
    if not COUNTERS_ARE_CUMULATIVE:
        return cur if cur >= 0 else None
    if not isinstance(prev, (int, float)):
        return None
    delta = cur - prev
    return delta if delta >= 0 else None  # negative = counter reset


def compute_rates(prev: dict | None, cur: dict | None) -> tuple[float | None, float | None]:
    """(rx_bps, tx_bps) between two samples; None where it cannot be determined."""
    if not prev or not cur:
        return None, None
    t0, t1 = parse_time(prev.get("time")), parse_time(cur.get("time"))
    if t0 is None or t1 is None or t1 <= t0:
        return None, None
    dt = t1 - t0
    out = []
    for key in ("rx_bytes", "tx_bytes"):
        delta = byte_delta(prev.get(key), cur.get(key))
        out.append(None if delta is None else delta * 8 / dt)
    return out[0], out[1]


class RateTracker:
    """Keeps the previous sample per (device, interface) and the latest rates."""

    def __init__(self) -> None:
        self._samples: dict[tuple[str, str], dict] = {}
        self.rates: dict[tuple[str, str], tuple[float | None, float | None]] = {}

    def update(self, latest: dict[str, dict[str, dict]]) -> None:
        new_rates = {}
        for dev, ifaces in latest.items():
            for name, sample in (ifaces or {}).items():
                key = (str(dev), name)
                prev = self._samples.get(key)
                if prev is not None and prev.get("time") == sample.get("time"):
                    # No new sample since last poll: keep the previous rate.
                    new_rates[key] = self.rates.get(key, (None, None))
                    continue
                new_rates[key] = compute_rates(prev, sample)
                self._samples[key] = sample
        self.rates = new_rates
