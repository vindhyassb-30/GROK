"""News headlines + lightweight sentiment (guide-safe, free, no API key).

Pulls recent headlines for a company from Google News RSS and scores each as
bullish / bearish / neutral using a transparent keyword lexicon. This is a
coarse signal, NOT deep NLP, and is clearly labelled as such.

The news bot feeds one more vote into the desk ("News Credibility" / sentiment),
but headline sentiment can be noisy -- it is weighted modestly, not treated as
proof, in keeping with the no-unsupported-conclusions rule.
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"

# Company-name map for the popular tickers; falls back to the ticker itself.
TICKER_NAMES = {
    "RELIANCE": "Reliance Industries",
    "TCS": "Tata Consultancy Services",
    "INFY": "Infosys",
    "HDFCBANK": "HDFC Bank",
    "ICICIBANK": "ICICI Bank",
    "SBIN": "State Bank of India",
    "ITC": "ITC Limited",
    "WIPRO": "Wipro",
    "TATAMOTORS": "Tata Motors",
    "BHARTIARTL": "Bharti Airtel",
}

_BULLISH = [
    "surge", "surges", "jump", "jumps", "rally", "rallies", "gain", "gains", "rise",
    "rises", "soar", "soars", "upgrade", "outperform", "beat", "beats", "record high",
    "profit", "profits", "strong", "buy", "bullish", "growth", "wins", "win", "order win",
    "high", "boost", "positive", "optimistic", "expansion", "approval", "approved",
]
_BEARISH = [
    "fall", "falls", "drop", "drops", "plunge", "plunges", "slump", "decline", "declines",
    "downgrade", "underperform", "miss", "misses", "loss", "losses", "weak", "sell",
    "bearish", "cut", "cuts", "probe", "fraud", "penalty", "fine", "lawsuit", "concern",
    "concerns", "warning", "warns", "slowdown", "layoff", "layoffs", "negative", "risk",
]


@dataclass
class Headline:
    title: str
    published: str
    sentiment: str      # bullish / bearish / neutral
    score: int          # per-headline net keyword score


@dataclass
class NewsResult:
    query: str
    headlines: List[Headline] = field(default_factory=list)
    sentiment: str = "neutral"      # overall
    score: float = 0.0              # -1..+1 overall
    available: bool = True
    note: str = ""


def company_name(ticker: str) -> str:
    return TICKER_NAMES.get(ticker.strip().upper(), ticker.strip().upper())


def _score_title(title: str) -> (str, int):
    t = title.lower()
    pos = sum(1 for w in _BULLISH if w in t)
    neg = sum(1 for w in _BEARISH if w in t)
    net = pos - neg
    if net > 0:
        return "bullish", net
    if net < 0:
        return "bearish", net
    return "neutral", 0


def _parse_rss(xml: str, limit: int) -> List[Headline]:
    items = re.findall(r"<item>(.*?)</item>", xml, re.S)
    out: List[Headline] = []
    for it in items[:limit]:
        tm = re.search(r"<title>(.*?)</title>", it, re.S)
        pm = re.search(r"<pubDate>(.*?)</pubDate>", it, re.S)
        if not tm:
            continue
        title = html.unescape(re.sub(r"<.*?>", "", tm.group(1)).strip())
        published = (pm.group(1).strip() if pm else "")
        sentiment, score = _score_title(title)
        out.append(Headline(title=title, published=published, sentiment=sentiment, score=score))
    return out


def get_news(ticker: str, limit: int = 10, timeout: float = 10.0) -> NewsResult:
    name = company_name(ticker)
    query = f"{name} stock"
    result = NewsResult(query=query)
    url = GOOGLE_NEWS_RSS.format(q=urllib.parse.quote(query))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            xml = resp.read().decode("utf-8", errors="replace")
        result.headlines = _parse_rss(xml, limit)
    except Exception as exc:  # noqa: BLE001
        result.available = False
        result.note = f"News unavailable ({type(exc).__name__})."
        return result

    if not result.headlines:
        result.note = "No recent headlines found."
        return result

    total = sum(h.score for h in result.headlines)
    bull = sum(1 for h in result.headlines if h.sentiment == "bullish")
    bear = sum(1 for h in result.headlines if h.sentiment == "bearish")
    denom = max(1, len(result.headlines))
    result.score = max(-1.0, min(1.0, total / denom))
    if result.score > 0.1:
        result.sentiment = "bullish"
    elif result.score < -0.1:
        result.sentiment = "bearish"
    else:
        result.sentiment = "neutral"
    result.note = f"{bull} bullish / {bear} bearish of {len(result.headlines)} headlines."
    return result
