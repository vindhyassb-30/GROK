"""Market data layer: fetch NSE daily OHLCV from Stooq, with offline fallback.

Stooq serves free CSV with no API key. NSE tickers use the ".ns" suffix, e.g.
RELIANCE -> reliance.ns. If the network fetch fails (offline, blocked, unknown
ticker), a deterministic synthetic series is generated so the app always renders
-- clearly labelled as demo data.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
YAHOO_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "{symbol}?range={rng}&interval={interval}"
)

# Timeframe presets: (yahoo_range, yahoo_interval, max_bars, intraday?)
TIMEFRAMES = {
    "daily": ("1y", "1d", 180, False),
    "intraday": ("1mo", "15m", 260, True),   # ~15-min bars over the last month
}

# Currency symbols by Yahoo currency code.
CURRENCY_SYMBOL = {"INR": "\u20b9", "USD": "$", "EUR": "\u20ac", "GBP": "\u00a3"}

# A small set of well-known NSE names for the UI dropdown.
POPULAR_NSE = [
    ("RELIANCE", "Reliance Industries"),
    ("TCS", "Tata Consultancy Services"),
    ("INFY", "Infosys"),
    ("HDFCBANK", "HDFC Bank"),
    ("ICICIBANK", "ICICI Bank"),
    ("SBIN", "State Bank of India"),
    ("ITC", "ITC"),
    ("TATAMOTORS", "Tata Motors"),
]

# Lower-priced, liquid NSE names (roughly the Rs 50-150 range, a few below).
POPULAR_NSE_CHEAP = [
    ("IDFCFIRSTB", "IDFC First Bank"),   # ~Rs 80
    ("NHPC", "NHPC"),                    # ~Rs 73
    ("PNB", "Punjab National Bank"),     # ~Rs 117
    ("IOC", "Indian Oil"),               # ~Rs 126
    ("YESBANK", "Yes Bank"),             # ~Rs 20
    ("IDEA", "Vodafone Idea"),           # ~Rs 13
]

# Popular US (dollar) names. Plain tickers, no suffix.
POPULAR_US = [
    ("AAPL", "Apple"),
    ("MSFT", "Microsoft"),
    ("NVDA", "NVIDIA"),
    ("TSLA", "Tesla"),
    ("AMZN", "Amazon"),
    ("GOOGL", "Alphabet"),
    ("META", "Meta Platforms"),
    ("AMD", "AMD"),
]


@dataclass
class Bar:
    d: str      # ISO date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class PriceSeries:
    ticker: str          # user-facing, e.g. RELIANCE
    stooq_symbol: str    # e.g. reliance.ns
    bars: List[Bar] = field(default_factory=list)
    source: str = "stooq"  # "yahoo", "stooq", or "demo"
    note: str = ""
    yahoo_symbol: str = ""  # e.g. RELIANCE.NS
    currency: str = "INR"   # ISO code from the feed
    currency_symbol: str = "\u20b9"
    market: str = "NSE"     # "NSE" or "US"
    timeframe: str = "daily"

    @property
    def closes(self) -> List[float]:
        return [b.close for b in self.bars]

    @property
    def volumes(self) -> List[float]:
        return [b.volume for b in self.bars]

    @property
    def last_close(self) -> Optional[float]:
        return self.bars[-1].close if self.bars else None


def to_stooq_symbol(ticker: str) -> str:
    """Map a bare NSE ticker to a Stooq symbol. Already-suffixed input passes through."""
    t = ticker.strip().lower()
    if "." in t:
        return t
    return f"{t}.ns"


def _parse_csv(text: str) -> List[Bar]:
    bars: List[Bar] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        try:
            bars.append(
                Bar(
                    d=row["Date"],
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume") or 0.0),
                )
            )
        except (KeyError, ValueError):
            continue
    return bars


def _fetch_stooq(stooq_symbol: str, timeout: float = 8.0) -> List[Bar]:
    url = STOOQ_URL.format(symbol=stooq_symbol)
    req = urllib.request.Request(url, headers={"User-Agent": "grok-desk/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8", errors="replace")
    if "Date,Open" not in text:
        return []
    return _parse_csv(text)


_US_TICKERS = {t for t, _ in POPULAR_US}


def detect_market(ticker: str) -> str:
    """NSE if it ends with .NS or isn't a known US ticker-ish name; else US.

    Heuristic: an explicit .NS suffix -> NSE. A known US popular ticker -> US.
    Otherwise, default to NSE (this app's primary market) unless the user
    typed a .US / plain US-style symbol we recognise.
    """
    t = ticker.strip().upper()
    if t.endswith(".NS"):
        return "NSE"
    if t in _US_TICKERS or t.endswith(".US"):
        return "US"
    # Bare symbol with no suffix: treat known US names as US, else NSE.
    return "US" if t in _US_TICKERS else "NSE"


def to_yahoo_symbol(ticker: str) -> str:
    """Map a bare ticker to a Yahoo symbol. NSE names get .NS; US names stay plain."""
    t = ticker.strip().upper()
    if "." in t:
        return t.replace(".US", "")
    return f"{t}.NS" if detect_market(t) == "NSE" else t


def _market_tz(symbol: str):
    """Return the exchange timezone for correct per-bar date/time labels."""
    try:
        from zoneinfo import ZoneInfo
        if symbol.upper().endswith(".NS"):
            return ZoneInfo("Asia/Kolkata")
        return ZoneInfo("America/New_York")  # US default
    except Exception:  # noqa: BLE001
        return timezone.utc


def _fetch_yahoo(yahoo_symbol: str, rng: str = "1y", interval: str = "1d",
                 intraday: bool = False, timeout: float = 12.0):
    """Fetch OHLCV from Yahoo. Returns (bars, currency_code).

    Bar labels use the EXCHANGE timezone (IST for .NS, US Eastern otherwise), so
    an intraday bar's time and a daily bar's date match the real trading session
    rather than UTC.
    """
    url = YAHOO_URL.format(symbol=urllib.parse.quote(yahoo_symbol), rng=rng, interval=interval)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    result = (data.get("chart") or {}).get("result") or []
    if not result:
        return [], None
    res = result[0]
    currency = (res.get("meta") or {}).get("currency")
    tz = _market_tz(yahoo_symbol)
    stamps = res.get("timestamp") or []
    quote = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    vols = quote.get("volume") or []
    bars: List[Bar] = []
    for i, ts in enumerate(stamps):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue  # skip gaps rather than inventing a value
        dt = datetime.fromtimestamp(ts, tz=tz)
        label = dt.strftime("%Y-%m-%d %H:%M") if intraday else dt.date().isoformat()
        bars.append(Bar(
            d=label,
            open=float(opens[i]) if i < len(opens) and opens[i] is not None else float(c),
            high=float(highs[i]) if i < len(highs) and highs[i] is not None else float(c),
            low=float(lows[i]) if i < len(lows) and lows[i] is not None else float(c),
            close=float(c),
            volume=float(vols[i]) if i < len(vols) and vols[i] is not None else 0.0,
        ))
    return bars, currency


def _synthetic(ticker: str, days: int = 180) -> List[Bar]:
    """Deterministic pseudo-random walk so demo data is stable per ticker."""
    seed = int(hashlib.sha256(ticker.upper().encode()).hexdigest(), 16)
    price = 500.0 + (seed % 2000)
    bars: List[Bar] = []
    start = date.today() - timedelta(days=days)
    for i in range(days):
        # Deterministic "noise" from a hash of ticker+index.
        h = int(hashlib.sha256(f"{ticker}{i}".encode()).hexdigest(), 16)
        drift = math.sin(i / 18.0) * 0.6            # gentle cycles
        shock = ((h % 1000) / 1000.0 - 0.5) * 2.4   # +/- noise
        price = max(5.0, price * (1 + (drift + shock) / 100.0))
        high = price * 1.012
        low = price * 0.988
        vol = 1_000_000 + (h % 500_000)
        d = (start + timedelta(days=i)).isoformat()
        bars.append(Bar(d=d, open=price, high=high, low=low, close=price, volume=vol))
    return bars


def get_prices(ticker: str, timeframe: str = "daily", max_bars: int = None) -> PriceSeries:
    """Fetch recent bars for a ticker at the chosen timeframe.

    timeframe: "daily" (1-day bars, ~1y) or "intraday" (15-min bars, ~1 month).
    Tries Yahoo first, then Stooq (daily only), then deterministic demo data.
    Market (NSE/US) and currency are detected from the ticker and the feed.
    """
    timeframe = timeframe if timeframe in TIMEFRAMES else "daily"
    rng, interval, default_max, intraday = TIMEFRAMES[timeframe]
    cap = max_bars or default_max

    stooq_symbol = to_stooq_symbol(ticker)
    yahoo_symbol = to_yahoo_symbol(ticker)
    market = detect_market(ticker)
    series = PriceSeries(ticker=ticker.upper(), stooq_symbol=stooq_symbol)
    series.yahoo_symbol = yahoo_symbol
    series.market = market
    series.timeframe = timeframe
    # Sensible default currency before the feed confirms it.
    series.currency = "USD" if market == "US" else "INR"
    series.currency_symbol = CURRENCY_SYMBOL.get(series.currency, series.currency)
    reasons: List[str] = []

    # 1) Yahoo Finance (supports both timeframes + currency)
    try:
        bars, currency = _fetch_yahoo(yahoo_symbol, rng=rng, interval=interval, intraday=intraday)
        if bars:
            series.bars = bars[-cap:]
            series.source = "yahoo"
            if currency:
                series.currency = currency
                series.currency_symbol = CURRENCY_SYMBOL.get(currency, currency)
            series.note = (
                f"Live {'intraday 15-min' if intraday else 'daily'} data from Yahoo Finance"
                + (" (delayed)." if intraday else ".")
            )
            return series
        reasons.append("Yahoo returned no rows for this ticker")
    except Exception as exc:  # noqa: BLE001
        reasons.append(f"Yahoo fetch failed ({type(exc).__name__})")

    # 2) Stooq (daily only)
    if not intraday:
        try:
            bars = _fetch_stooq(stooq_symbol)
            if bars:
                series.bars = bars[-cap:]
                series.source = "stooq"
                series.note = "Live daily data from Stooq."
                return series
            reasons.append("Stooq returned no CSV (anti-bot page or unknown symbol)")
        except Exception as exc:  # noqa: BLE001
            reasons.append(f"Stooq fetch failed ({type(exc).__name__})")

    # 3) Demo fallback
    series.bars = _synthetic(ticker, days=default_max)
    series.source = "demo"
    series.note = "DEMO data (layout only) — " + "; ".join(reasons) + "."
    return series


def popular_all() -> List[tuple]:
    """Return (ticker, name, market) for NSE, cheaper NSE, and US popular lists."""
    out = [(t, n, "NSE") for t, n in POPULAR_NSE]
    out += [(t, n, "NSE") for t, n in POPULAR_NSE_CHEAP]
    out += [(t, n, "US") for t, n in POPULAR_US]
    return out
