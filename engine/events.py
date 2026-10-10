"""Dated BUY/SELL trigger detection and a near-term bias read.

Scans the price history and marks the specific dates where a signal fired:
- MACD line crossing its signal line
- RSI leaving oversold (<30 -> up) or overbought (>70 -> down)
- SMA20 crossing SMA50 (golden / death cross)

It also produces a near-term BIAS -- a statement of current tendency with a
confidence, NOT a guaranteed prediction of future price or timing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .signals import Indicators


@dataclass
class SignalEvent:
    date: str
    index: int          # position in the trimmed chart series
    action: str         # BUY / SELL
    kind: str           # e.g. "MACD cross", "RSI oversold exit"
    price: float
    note: str


def _crossed_up(prev_a, prev_b, a, b) -> bool:
    return (prev_a is not None and prev_b is not None and a is not None and b is not None
            and prev_a <= prev_b and a > b)


def _crossed_down(prev_a, prev_b, a, b) -> bool:
    return (prev_a is not None and prev_b is not None and a is not None and b is not None
            and prev_a >= prev_b and a < b)


def _filter_whipsaw(events: List["SignalEvent"], min_move_pct: float,
                    cooldown_bars: int) -> List["SignalEvent"]:
    """Remove noisy flip-flop signals.

    Rules:
    - Drop a signal in the same direction as the last kept one (no stacking).
    - Require the price to have moved at least `min_move_pct` since the last kept
      signal, otherwise it's just chop.
    - Enforce a `cooldown_bars` gap (by chart index) between kept signals.
    """
    kept: List[SignalEvent] = []
    for e in events:
        if kept:
            last = kept[-1]
            if e.action == last.action:
                continue  # same direction -> redundant
            if (e.index - last.index) < cooldown_bars:
                continue  # too soon after the last flip
            move = abs(e.price - last.price) / last.price * 100.0 if last.price else 0.0
            if move < min_move_pct:
                continue  # move too small to be meaningful -> whipsaw
        kept.append(e)
    return kept


def detect_events(ix: Indicators, dates: List[str], tail: int = 120,
                  min_move_pct: float = 0.0, cooldown_bars: int = 0) -> List[SignalEvent]:
    """Return BUY/SELL events within the last `tail` bars (aligned to the chart).

    If min_move_pct / cooldown_bars are set, apply a whipsaw filter that drops
    noisy flip-flop signals (used for the choppy intraday view).
    """
    n = len(ix.closes)
    start = max(1, n - tail)
    events: List[SignalEvent] = []

    for i in range(start, n):
        d = dates[i] if i < len(dates) else ""
        price = ix.closes[i]
        chart_index = i - max(0, n - tail)  # index within the trimmed chart arrays

        # MACD cross
        if _crossed_up(ix.macd_line[i - 1], ix.macd_signal[i - 1], ix.macd_line[i], ix.macd_signal[i]):
            events.append(SignalEvent(d, chart_index, "BUY", "MACD cross up", price,
                                      "MACD line crossed above its signal line."))
        elif _crossed_down(ix.macd_line[i - 1], ix.macd_signal[i - 1], ix.macd_line[i], ix.macd_signal[i]):
            events.append(SignalEvent(d, chart_index, "SELL", "MACD cross down", price,
                                      "MACD line crossed below its signal line."))

        # RSI oversold/overbought exits
        r_prev, r = ix.rsi14[i - 1], ix.rsi14[i]
        if r_prev is not None and r is not None:
            if r_prev < 30 <= r:
                events.append(SignalEvent(d, chart_index, "BUY", "RSI oversold exit", price,
                                          "RSI climbed back above 30 (leaving oversold)."))
            elif r_prev > 70 >= r:
                events.append(SignalEvent(d, chart_index, "SELL", "RSI overbought exit", price,
                                          "RSI dropped back below 70 (leaving overbought)."))

        # SMA20 vs SMA50 cross
        if _crossed_up(ix.sma20[i - 1], ix.sma50[i - 1], ix.sma20[i], ix.sma50[i]):
            events.append(SignalEvent(d, chart_index, "BUY", "Golden cross", price,
                                      "SMA20 crossed above SMA50 (bullish trend shift)."))
        elif _crossed_down(ix.sma20[i - 1], ix.sma50[i - 1], ix.sma20[i], ix.sma50[i]):
            events.append(SignalEvent(d, chart_index, "SELL", "Death cross", price,
                                      "SMA20 crossed below SMA50 (bearish trend shift)."))

    if min_move_pct > 0 or cooldown_bars > 0:
        events = _filter_whipsaw(events, min_move_pct, cooldown_bars)
    return events


@dataclass
class NearTermBias:
    direction: str      # bullish / bearish / neutral
    confidence: float   # 0..1
    horizon: str        # e.g. "next 1-2 weeks"
    note: str


def near_term_bias(ix: Indicators, verdict_score: float, news_score: Optional[float] = None) -> NearTermBias:
    """Blend recent technical slope + current verdict + (optional) news into a
    short-horizon tendency. This is a bias, not a guaranteed forecast.
    """
    closes = ix.closes
    # Recent slope of SMA20 over last 5 bars.
    slope = 0.0
    s = [v for v in ix.sma20[-6:] if v is not None]
    if len(s) >= 2 and s[0]:
        slope = (s[-1] - s[0]) / s[0]

    score = verdict_score * 0.6 + max(-1, min(1, slope * 25)) * 0.4
    if news_score is not None:
        score = score * 0.75 + news_score * 0.25

    if score >= 0.2:
        direction, note = "bullish", "Trend and momentum currently lean up."
    elif score <= -0.2:
        direction, note = "bearish", "Trend and momentum currently lean down."
    else:
        direction, note = "neutral", "No clear short-term edge right now."

    confidence = max(0.1, min(0.9, abs(score)))
    return NearTermBias(
        direction=direction,
        confidence=round(confidence, 2),
        horizon="next 1-2 weeks",
        note=note + " This is a tendency, not a guaranteed forecast.",
    )


@dataclass
class ActionNow:
    action: str          # BUY NOW / SELL NOW / WAIT
    headline: str        # short imperative line
    reason: str
    trigger_date: Optional[str]
    trigger_price: Optional[float]
    days_since: Optional[int]
    stop_loss: Optional[float]
    target: Optional[float]
    confidence: float


def _days_between(iso_a: str, iso_b: str) -> Optional[int]:
    from datetime import date as _date
    try:
        a = _date.fromisoformat(iso_a[:10])
        b = _date.fromisoformat(iso_b[:10])
        return (b - a).days
    except Exception:  # noqa: BLE001
        return None


def _recent_atr(ix: Indicators, period: int = 14) -> Optional[float]:
    """Average absolute daily move over the last `period` bars (volatility proxy)."""
    closes = ix.closes
    if len(closes) < period + 1:
        return None
    moves = [abs(closes[i] - closes[i - 1]) for i in range(len(closes) - period, len(closes))]
    return sum(moves) / len(moves) if moves else None


def decide_action_now(
    ix: Indicators,
    dates: List[str],
    events: List[SignalEvent],
    verdict_action: str,
    verdict_conf: float,
    bias_direction: str,
    fresh_days: int = 5,
) -> ActionNow:
    """Turn history + current verdict into a single, present-tense recommendation.

    Logic (transparent, not a guarantee):
    - If the most recent signal fired within `fresh_days`, surface it as the
      live action (BUY NOW / SELL NOW).
    - Otherwise fall back to the desk verdict + near-term bias: a confident BUY/
      SELL verdict becomes the action; anything weak or mixed becomes WAIT.
    - Suggest a stop-loss and target from recent volatility (ATR-like).
    """
    last_close = ix.closes[-1] if ix.closes else None
    today = dates[-1] if dates else ""
    atr = _recent_atr(ix)

    last_event = events[-1] if events else None
    days_since = _days_between(last_event.date, today) if last_event else None

    # Decide the action.
    if last_event is not None and days_since is not None and days_since <= fresh_days:
        action = f"{last_event.action} NOW"
        reason = f"Fresh {last_event.kind} signal {days_since} day(s) ago. {last_event.note}"
        trigger_date, trigger_price = last_event.date, round(last_event.price, 2)
        confidence = max(verdict_conf, 0.5)
        base_action = last_event.action
    else:
        # No fresh trigger -> use verdict + bias.
        if verdict_action == "BUY" and verdict_conf >= 0.35 and bias_direction != "bearish":
            action, base_action = "BUY NOW", "BUY"
            reason = "No fresh trigger, but the desk verdict leans buy with support from the near-term bias."
        elif verdict_action == "SELL" and verdict_conf >= 0.35 and bias_direction != "bullish":
            action, base_action = "SELL NOW", "SELL"
            reason = "No fresh trigger, but the desk verdict leans sell with the near-term bias."
        else:
            action, base_action = "WAIT", "WAIT"
            reason = "No fresh buy/sell trigger and the verdict is mixed or low-confidence. Waiting is the lower-risk choice."
        trigger_date = last_event.date if last_event else None
        trigger_price = round(last_event.price, 2) if last_event else None
        confidence = verdict_conf

    # Stop-loss / target suggestions from volatility (only meaningful for BUY/SELL).
    stop = target = None
    if last_close is not None and atr is not None and base_action in ("BUY", "SELL"):
        if base_action == "BUY":
            stop = round(last_close - 2 * atr, 2)
            target = round(last_close + 3 * atr, 2)
        else:
            stop = round(last_close + 2 * atr, 2)
            target = round(last_close - 3 * atr, 2)

    headline = {
        "BUY NOW": "Signals favour buying.",
        "SELL NOW": "Signals favour selling / taking profit.",
        "WAIT": "No clear signal — hold and wait.",
    }.get(action, "")

    return ActionNow(
        action=action,
        headline=headline,
        reason=reason,
        trigger_date=trigger_date,
        trigger_price=trigger_price,
        days_since=days_since,
        stop_loss=stop,
        target=target,
        confidence=round(confidence, 2),
    )


@dataclass
class TradeResult:
    buy_date: str
    buy_price: float
    sell_date: str
    sell_price: float
    pct: float


@dataclass
class Performance:
    trades: List[TradeResult]
    wins: int
    total: int
    avg_pct: float
    net_pct: float          # cumulative result of compounding every round-trip
    verdict: str            # "profitable" / "losing" / "flat" / "untested"
    note: str


def pair_trades(events: List[SignalEvent]) -> Performance:
    """Pair each BUY with the next SELL into round-trips and score the % result.

    Reports a NET cumulative result (compounded) so a losing strategy is obvious.
    This is an honest backtest over the visible window -- NOT a forecast.
    """
    trades: List[TradeResult] = []
    open_buy: Optional[SignalEvent] = None
    for e in events:
        if e.action == "BUY" and open_buy is None:
            open_buy = e
        elif e.action == "SELL" and open_buy is not None:
            pct = (e.price - open_buy.price) / open_buy.price * 100.0 if open_buy.price else 0.0
            trades.append(TradeResult(open_buy.date, open_buy.price, e.date, e.price, round(pct, 2)))
            open_buy = None

    wins = sum(1 for t in trades if t.pct > 0)
    total = len(trades)
    avg = round(sum(t.pct for t in trades) / total, 2) if total else 0.0

    # Net = compound every round-trip as if fully reinvested (before costs).
    equity = 1.0
    for t in trades:
        equity *= (1 + t.pct / 100.0)
    net = round((equity - 1) * 100.0, 2)

    if total == 0:
        verdict, note = "untested", "No completed buy→sell round-trips in this window yet."
    else:
        if net > 0.5:
            verdict = "profitable"
        elif net < -0.5:
            verdict = "losing"
        else:
            verdict = "flat"
        tail = {
            "profitable": "the signals net positive here, but past results don't predict the future.",
            "losing": "following every signal would have LOST money here — treat these as study, not trades.",
            "flat": "the signals roughly broke even here (before costs).",
        }[verdict]
        note = (f"{wins}/{total} round-trips profitable · net {net:+.2f}% compounded "
                f"(before brokerage/taxes) · {tail}")
    return Performance(trades=trades, wins=wins, total=total, avg_pct=avg,
                       net_pct=net, verdict=verdict, note=note)
