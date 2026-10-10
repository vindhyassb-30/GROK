"""Technical indicators, pure standard library (no numpy/pandas).

Each function takes a list of floats (oldest -> newest) and returns a list of the
same length, with None where there isn't enough history yet. This keeps indices
aligned with the price series for charting and signal logic.
"""

from __future__ import annotations

from typing import List, Optional


def sma(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0:
        return out
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values: List[float], period: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    k = 2.0 / (period + 1)
    # Seed with SMA of the first `period` values.
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    """Wilder's RSI."""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains += max(change, 0.0)
        losses += max(-change, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period

    def rsi_from(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1 + rs))

    out[period] = rsi_from(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = rsi_from(avg_gain, avg_loss)
    return out


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """Return (macd_line, signal_line, histogram), each aligned to values."""
    ema_fast = ema(values, fast)
    ema_slow = ema(values, slow)
    macd_line: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]
    # Signal line = EMA of the macd_line's non-None tail.
    present = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    signal_line: List[Optional[float]] = [None] * len(values)
    hist: List[Optional[float]] = [None] * len(values)
    if len(present) >= signal:
        tail_vals = [v for _, v in present]
        tail_sig = ema(tail_vals, signal)
        for (idx_in_tail, (orig_i, _)) in enumerate(present):
            s = tail_sig[idx_in_tail]
            signal_line[orig_i] = s
            if s is not None and macd_line[orig_i] is not None:
                hist[orig_i] = macd_line[orig_i] - s
    return macd_line, signal_line, hist


def rolling_volatility(values: List[float], period: int = 20) -> List[Optional[float]]:
    """Annualised-ish volatility: stdev of daily returns over a window (percent)."""
    rets: List[Optional[float]] = [None] * len(values)
    for i in range(1, len(values)):
        if values[i - 1]:
            rets[i] = (values[i] - values[i - 1]) / values[i - 1]
    out: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        window = [r for r in rets[max(0, i - period + 1): i + 1] if r is not None]
        if len(window) >= period // 2 and len(window) > 1:
            mean = sum(window) / len(window)
            var = sum((r - mean) ** 2 for r in window) / (len(window) - 1)
            out[i] = (var ** 0.5) * 100.0
    return out


def pct_change(values: List[float], lookback: int) -> Optional[float]:
    """Percent change over the last `lookback` bars."""
    if len(values) <= lookback or values[-lookback - 1] == 0:
        return None
    return (values[-1] - values[-lookback - 1]) / values[-lookback - 1] * 100.0


def last_non_none(series: List[Optional[float]]) -> Optional[float]:
    for v in reversed(series):
        if v is not None:
            return v
    return None


def stdev(values: List[float], period: int) -> List[Optional[float]]:
    """Rolling sample standard deviation over `period` values."""
    out: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if i >= period - 1:
            window = values[i - period + 1: i + 1]
            mean = sum(window) / period
            var = sum((v - mean) ** 2 for v in window) / (period - 1)
            out[i] = var ** 0.5
    return out


def bollinger(values: List[float], period: int = 20, mult: float = 2.0):
    """Return (middle, upper, lower) Bollinger bands aligned to values."""
    mid = sma(values, period)
    sd = stdev(values, period)
    upper: List[Optional[float]] = [None] * len(values)
    lower: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if mid[i] is not None and sd[i] is not None:
            upper[i] = mid[i] + mult * sd[i]
            lower[i] = mid[i] - mult * sd[i]
    return mid, upper, lower


def roc(values: List[float], period: int = 12) -> List[Optional[float]]:
    """Rate of change (percent) over `period` bars."""
    out: List[Optional[float]] = [None] * len(values)
    for i in range(len(values)):
        if i >= period and values[i - period]:
            out[i] = (values[i] - values[i - period]) / values[i - period] * 100.0
    return out


def range_position(values: List[float], lookback: int = 252) -> Optional[float]:
    """Where the latest price sits in its recent high-low range, as 0..100.

    0 = at the period low, 100 = at the period high. A rough value/positioning
    proxy (think "distance from 52-week high/low").
    """
    if not values:
        return None
    window = values[-lookback:] if len(values) >= 2 else values
    lo = min(window)
    hi = max(window)
    if hi == lo:
        return 50.0
    return (values[-1] - lo) / (hi - lo) * 100.0


def high_low(values: List[float], lookback: int = 252):
    """Return (low, high) over the last `lookback` bars."""
    if not values:
        return None, None
    window = values[-lookback:]
    return min(window), max(window)
