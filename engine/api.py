"""Thin orchestration + JSON serialization used by the serverless function.

analyze(ticker) returns a plain dict ready to json.dumps -> the frontend.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from . import indicators as ind
from .events import decide_action_now, detect_events, near_term_bias, pair_trades
from .marketdata import POPULAR_NSE, get_prices, popular_all
from .news import get_news
from .signals import compute_indicators, run_analysis

MAX_POINTS = 120


def _r2(xs):
    """Round a series, keeping None holes."""
    return [None if v is None else round(v, 2) for v in xs]


def _tail(xs, n: int):
    return xs[max(0, len(xs) - n):]


def _series_for_chart(ix, dates, series, max_points: int = MAX_POINTS) -> Dict:
    """Trim price + indicator + OHLC series to the most recent max_points, aligned."""
    bars = series.bars
    return {
        "dates": _tail(dates, max_points),
        "open": _r2(_tail([b.open for b in bars], max_points)),
        "high": _r2(_tail([b.high for b in bars], max_points)),
        "low": _r2(_tail([b.low for b in bars], max_points)),
        "close": _r2(_tail(ix.closes, max_points)),
        "sma20": _r2(_tail(ix.sma20, max_points)),
        "sma50": _r2(_tail(ix.sma50, max_points)),
        "rsi14": _r2(_tail(ix.rsi14, max_points)),
        "macd_line": _r2(_tail(ix.macd_line, max_points)),
        "macd_signal": _r2(_tail(ix.macd_signal, max_points)),
        "macd_hist": _r2(_tail(ix.macd_hist, max_points)),
        "intraday": series.timeframe == "intraday",
    }


def analyze(ticker: str, timeframe: str = "daily") -> Dict:
    series = get_prices(ticker, timeframe=timeframe)
    ix = compute_indicators(series)
    dates = [b.d for b in series.bars]
    intraday = series.timeframe == "intraday"

    # News sentiment feeds the daily view; intraday is price-driven only.
    if intraday:
        from .news import NewsResult
        news = NewsResult(query="", available=False, note="News applies to the daily view.")
        news_score = None
    else:
        news = get_news(ticker)
        news_score = news.score if news.available and news.headlines else None

    verdict = run_analysis(series, news_score=news_score, news_note=news.note)
    bias = near_term_bias(ix, verdict.score, news_score)
    # Intraday is choppy -> apply a whipsaw filter (min move + cooldown) so we
    # don't surface noisy flip-flop signals. Daily keeps raw crossovers.
    if intraday:
        events = detect_events(ix, dates, tail=MAX_POINTS, min_move_pct=0.8, cooldown_bars=3)
    else:
        events = detect_events(ix, dates, tail=MAX_POINTS)
    action = decide_action_now(ix, dates, events, verdict.action, verdict.confidence,
                               bias.direction, fresh_days=(5 if not intraday else 2))
    perf = pair_trades(events)

    chart = _series_for_chart(ix, dates, series)
    last_bar_date = dates[-1] if dates else None

    # OHLC header for the latest bar + change vs previous close.
    bars = series.bars
    ohlc = None
    if bars:
        lb = bars[-1]
        prev_close = bars[-2].close if len(bars) >= 2 else lb.open
        chg = lb.close - prev_close
        chg_pct = (chg / prev_close * 100.0) if prev_close else 0.0
        ohlc = {
            "o": round(lb.open, 2), "h": round(lb.high, 2),
            "l": round(lb.low, 2), "c": round(lb.close, 2),
            "change": round(chg, 2), "change_pct": round(chg_pct, 2),
        }

    return {
        "ticker": series.ticker,
        "stooq_symbol": series.stooq_symbol,
        "yahoo_symbol": getattr(series, "yahoo_symbol", ""),
        "market": series.market,
        "currency": series.currency,
        "currency_symbol": series.currency_symbol,
        "timeframe": series.timeframe,
        "data_source": series.source,          # "yahoo", "stooq" or "demo"
        "data_note": series.note,
        "last_close": round(series.last_close, 2) if series.last_close else None,
        "last_bar_date": last_bar_date,
        "ohlc": ohlc,
        "warning": _build_warning(intraday, perf),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action_now": {
            "action": action.action,
            "headline": action.headline,
            "reason": action.reason,
            "trigger_date": action.trigger_date,
            "trigger_price": action.trigger_price,
            "days_since": action.days_since,
            "stop_loss": action.stop_loss,
            "target": action.target,
            "confidence": action.confidence,
        },
        "performance": {
            "wins": perf.wins,
            "total": perf.total,
            "avg_pct": perf.avg_pct,
            "net_pct": perf.net_pct,
            "verdict": perf.verdict,
            "note": perf.note,
            "trades": [
                {
                    "buy_date": t.buy_date, "buy_price": t.buy_price,
                    "sell_date": t.sell_date, "sell_price": t.sell_price,
                    "pct": t.pct,
                }
                for t in perf.trades
            ],
        },
        "bias": {
            "direction": bias.direction,
            "confidence": bias.confidence,
            "horizon": bias.horizon,
            "note": bias.note,
        },
        "events": [
            {
                "date": e.date,
                "index": e.index,
                "action": e.action,
                "kind": e.kind,
                "price": round(e.price, 2),
                "note": e.note,
            }
            for e in events
        ],
        "news": {
            "available": news.available,
            "sentiment": news.sentiment,
            "score": round(news.score, 2),
            "note": news.note,
            "query": news.query,
            "headlines": [
                {"title": h.title, "published": h.published, "sentiment": h.sentiment}
                for h in news.headlines
            ],
        },
        "verdict": {
            "action": verdict.action,
            "confidence": verdict.confidence,
            "score": verdict.score,
            "reasons": verdict.reasons,
            "disagreements": verdict.disagreements,
            "disclaimer": verdict.disclaimer,
        },
        "indicators": {
            "rsi14": _round(ind.last_non_none(ix.rsi14)),
            "sma20": _round(ind.last_non_none(ix.sma20)),
            "sma50": _round(ind.last_non_none(ix.sma50)),
            "volatility": _round(ind.last_non_none(ix.vol20)),
            "range_pos": _round(ix.range_pos),
            "low_52w": _round(ix.low_52w),
            "high_52w": _round(ix.high_52w),
        },
        "leads": [
            {
                "lead": lv.lead,
                "department": lv.department,
                "action": lv.action,
                "confidence": lv.confidence,
                "rationale": lv.rationale,
                "signals": [
                    {
                        "bot": s.bot,
                        "action": s.action,
                        "confidence": round(s.confidence, 2),
                        "reason": s.reason,
                        "metric": s.metric,
                    }
                    for s in lv.signals
                ],
            }
            for lv in verdict.lead_verdicts
        ],
        "chart": chart,
    }


def popular() -> List[Dict]:
    return [{"ticker": t, "name": n, "market": m} for t, n, m in popular_all()]


def quick_signal(ticker: str, timeframe: str = "daily") -> Dict:
    """Lightweight current signal for one ticker (no news) -- used by the live bar."""
    try:
        series = get_prices(ticker, timeframe=timeframe)
        if not series.bars:
            raise ValueError("no data")
        ix = compute_indicators(series)
        dates = [b.d for b in series.bars]
        verdict = run_analysis(series)  # no news for speed
        bias = near_term_bias(ix, verdict.score, None)
        events = detect_events(ix, dates, tail=MAX_POINTS)
        action = decide_action_now(
            ix, dates, events, verdict.action, verdict.confidence, bias.direction,
            fresh_days=(5 if series.timeframe == "daily" else 2),
        )
        return {
            "ticker": series.ticker,
            "market": series.market,
            "currency_symbol": series.currency_symbol,
            "price": round(series.last_close, 2) if series.last_close else None,
            "action": action.action,                 # BUY NOW / SELL NOW / WAIT
            "confidence": action.confidence,
            "source": series.source,
            "ok": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ticker": ticker.upper(), "ok": False, "error": type(exc).__name__}


def scan_watchlist(timeframe: str = "daily") -> List[Dict]:
    """Scan all popular NSE + US tickers (in parallel) and return their signals."""
    from concurrent.futures import ThreadPoolExecutor

    tickers = [t for t, _n, _m in popular_all()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda t: quick_signal(t, timeframe=timeframe), tickers))
    return results


def _build_warning(intraday: bool, perf) -> Optional[str]:
    """Surface an honest caution banner when relevant."""
    msgs = []
    if intraday:
        msgs.append(
            "Intraday signals use lagging indicators on ~15-min delayed data — they "
            "whipsaw in choppy markets and are unreliable for real trading. Use for study."
        )
    if getattr(perf, "verdict", "") == "losing":
        msgs.append(
            f"Backtest shows these signals LOST money here (net {perf.net_pct:+.2f}% over "
            f"{perf.total} round-trips). Do not follow them blindly."
        )
    return " ".join(msgs) if msgs else None


def _round(v):
    return None if v is None else round(v, 2)
