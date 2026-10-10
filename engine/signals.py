"""Per-bot analysis signals and the Lead -> Chief aggregation.

Each specialist analyst reads the price series + indicators and emits a single
Signal (BUY / SELL / HOLD) with a human-readable reason and an evidence-based
confidence (0..1). Department Leads average their specialists; the Chief combines
the Leads into one verdict.

Research and education only -- not financial advice, no guaranteed outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import indicators as ind
from .marketdata import PriceSeries

BUY = "BUY"
SELL = "SELL"
HOLD = "HOLD"

# Numeric score per action for averaging: BUY=+1, HOLD=0, SELL=-1.
_SCORE = {BUY: 1.0, HOLD: 0.0, SELL: -1.0}


def _action_from_score(score: float) -> str:
    if score >= 0.33:
        return BUY
    if score <= -0.33:
        return SELL
    return HOLD


@dataclass
class Signal:
    bot: str
    department: str
    action: str          # BUY / SELL / HOLD
    confidence: float    # 0..1
    reason: str
    metric: str = ""     # short metric readout, e.g. "RSI 72.3"

    @property
    def score(self) -> float:
        return _SCORE[self.action] * self.confidence


@dataclass
class LeadVerdict:
    lead: str
    department: str
    action: str
    confidence: float
    signals: List[Signal] = field(default_factory=list)
    rationale: str = ""


@dataclass
class ChiefVerdict:
    ticker: str
    action: str
    confidence: float
    score: float                     # -1..+1 aggregate
    lead_verdicts: List[LeadVerdict] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    disagreements: List[str] = field(default_factory=list)
    disclaimer: str = (
        "Research and education only. This is a technical-analysis signal, not "
        "financial advice. It cannot guarantee outcomes. Do your own research."
    )


# --- individual analyst functions --------------------------------------
# Each returns a Signal. They receive the PriceSeries and the computed indicator
# bundle so they don't recompute.

@dataclass
class Indicators:
    closes: List[float]
    sma20: List[Optional[float]]
    sma50: List[Optional[float]]
    ema20: List[Optional[float]]
    rsi14: List[Optional[float]]
    macd_line: List[Optional[float]]
    macd_signal: List[Optional[float]]
    macd_hist: List[Optional[float]]
    vol20: List[Optional[float]]
    volumes: List[float]
    boll_mid: List[Optional[float]]
    boll_up: List[Optional[float]]
    boll_low: List[Optional[float]]
    roc12: List[Optional[float]]
    range_pos: Optional[float]
    low_52w: Optional[float]
    high_52w: Optional[float]


def compute_indicators(series: PriceSeries) -> Indicators:
    closes = series.closes
    macd_line, macd_signal, macd_hist = ind.macd(closes)
    boll_mid, boll_up, boll_low = ind.bollinger(closes, 20, 2.0)
    low_52w, high_52w = ind.high_low(closes, 252)
    return Indicators(
        closes=closes,
        sma20=ind.sma(closes, 20),
        sma50=ind.sma(closes, 50),
        ema20=ind.ema(closes, 20),
        rsi14=ind.rsi(closes, 14),
        macd_line=macd_line,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        vol20=ind.rolling_volatility(closes, 20),
        volumes=series.volumes,
        boll_mid=boll_mid,
        boll_up=boll_up,
        boll_low=boll_low,
        roc12=ind.roc(closes, 12),
        range_pos=ind.range_position(closes, 252),
        low_52w=low_52w,
        high_52w=high_52w,
    )


def _trend_analyst(ix: Indicators) -> Signal:
    """Trend via SMA20 vs SMA50 (golden/death cross) and price vs SMA50."""
    s20 = ind.last_non_none(ix.sma20)
    s50 = ind.last_non_none(ix.sma50)
    price = ix.closes[-1] if ix.closes else None
    if s20 is None or s50 is None or price is None:
        return Signal("Stock Movement Analyst", "Market News Research", HOLD, 0.3,
                      "Not enough history for a reliable trend read.", "trend n/a")
    spread = (s20 - s50) / s50 * 100.0
    if s20 > s50 and price > s50:
        conf = min(0.9, 0.5 + abs(spread) / 10.0)
        return Signal("Stock Movement Analyst", "Market News Research", BUY, conf,
                      "Short-term average is above the long-term average (uptrend).",
                      f"SMA20>{'SMA50'} by {spread:+.1f}%")
    if s20 < s50 and price < s50:
        conf = min(0.9, 0.5 + abs(spread) / 10.0)
        return Signal("Stock Movement Analyst", "Market News Research", SELL, conf,
                      "Short-term average is below the long-term average (downtrend).",
                      f"SMA20<SMA50 by {spread:+.1f}%")
    return Signal("Stock Movement Analyst", "Market News Research", HOLD, 0.45,
                  "Averages are mixed; trend is unclear.", f"SMA spread {spread:+.1f}%")


def _momentum_analyst(ix: Indicators) -> Signal:
    """Momentum via RSI(14)."""
    r = ind.last_non_none(ix.rsi14)
    if r is None:
        return Signal("Research Analyst", "Market News Research", HOLD, 0.3,
                      "Not enough history for RSI.", "RSI n/a")
    if r >= 70:
        return Signal("Research Analyst", "Market News Research", SELL,
                      min(0.9, 0.5 + (r - 70) / 30.0),
                      "RSI is in overbought territory; momentum may reverse down.",
                      f"RSI {r:.1f}")
    if r <= 30:
        return Signal("Research Analyst", "Market News Research", BUY,
                      min(0.9, 0.5 + (30 - r) / 30.0),
                      "RSI is in oversold territory; momentum may reverse up.",
                      f"RSI {r:.1f}")
    # Neutral zone: lean slightly with where RSI sits around 50.
    lean = (r - 50) / 50.0
    action = BUY if lean > 0.15 else SELL if lean < -0.15 else HOLD
    return Signal("Research Analyst", "Market News Research", action,
                  0.4 + abs(lean) * 0.3,
                  "RSI is in the neutral band.", f"RSI {r:.1f}")


def _macd_analyst(ix: Indicators) -> Signal:
    """MACD line vs signal line crossover."""
    m = ind.last_non_none(ix.macd_line)
    s = ind.last_non_none(ix.macd_signal)
    h = ind.last_non_none(ix.macd_hist)
    if m is None or s is None or h is None:
        return Signal("Sentiment Analyst", "Market News Research", HOLD, 0.3,
                      "Not enough history for MACD.", "MACD n/a")
    if m > s and h > 0:
        return Signal("Sentiment Analyst", "Market News Research", BUY,
                      min(0.85, 0.5 + abs(h) / (abs(m) + 1e-9)),
                      "MACD line is above its signal line (bullish momentum).",
                      f"MACD {m:.2f} > signal {s:.2f}")
    if m < s and h < 0:
        return Signal("Sentiment Analyst", "Market News Research", SELL,
                      min(0.85, 0.5 + abs(h) / (abs(m) + 1e-9)),
                      "MACD line is below its signal line (bearish momentum).",
                      f"MACD {m:.2f} < signal {s:.2f}")
    return Signal("Sentiment Analyst", "Market News Research", HOLD, 0.45,
                  "MACD is flat around its signal line.", f"hist {h:+.2f}")


def _volatility_analyst(ix: Indicators) -> Signal:
    """Risk read via rolling volatility -- high vol tempers conviction to HOLD."""
    v = ind.last_non_none(ix.vol20)
    if v is None:
        return Signal("Geopolitical Risk Analyst", "Industry and Geopolitical Research",
                      HOLD, 0.3, "Not enough history to gauge volatility.", "vol n/a")
    if v >= 3.0:
        return Signal("Geopolitical Risk Analyst", "Industry and Geopolitical Research",
                      HOLD, 0.6, "Volatility is elevated; prefer caution.", f"vol {v:.1f}%/day")
    if v <= 1.0:
        return Signal("Geopolitical Risk Analyst", "Industry and Geopolitical Research",
                      BUY, 0.5, "Volatility is low; conditions are calmer.", f"vol {v:.1f}%/day")
    return Signal("Geopolitical Risk Analyst", "Industry and Geopolitical Research",
                  HOLD, 0.4, "Volatility is moderate.", f"vol {v:.1f}%/day")


def _volume_analyst(ix: Indicators) -> Signal:
    """Volume confirmation: rising volume + rising price supports the move."""
    if len(ix.volumes) < 25 or len(ix.closes) < 25:
        return Signal("Market Volume Intelligence Analyst", "Market Activity and Ownership",
                      HOLD, 0.3, "Not enough volume history.", "volume n/a")
    recent = sum(ix.volumes[-5:]) / 5.0
    base = sum(ix.volumes[-25:-5]) / 20.0
    price_chg = ind.pct_change(ix.closes, 5) or 0.0
    if base <= 0:
        return Signal("Market Volume Intelligence Analyst", "Market Activity and Ownership",
                      HOLD, 0.3, "Volume data unusable.", "volume n/a")
    vol_ratio = recent / base
    if vol_ratio > 1.2 and price_chg > 0:
        return Signal("Market Volume Intelligence Analyst", "Market Activity and Ownership",
                      BUY, min(0.8, 0.5 + (vol_ratio - 1) * 0.5),
                      "Rising volume is confirming a rising price.",
                      f"vol x{vol_ratio:.2f}, price {price_chg:+.1f}%")
    if vol_ratio > 1.2 and price_chg < 0:
        return Signal("Market Volume Intelligence Analyst", "Market Activity and Ownership",
                      SELL, min(0.8, 0.5 + (vol_ratio - 1) * 0.5),
                      "Rising volume is confirming a falling price.",
                      f"vol x{vol_ratio:.2f}, price {price_chg:+.1f}%")
    return Signal("Market Volume Intelligence Analyst", "Market Activity and Ownership",
                  HOLD, 0.4, "Volume is not confirming a strong move.",
                  f"vol x{vol_ratio:.2f}")


def _bollinger_analyst(ix: Indicators) -> Signal:
    """Mean-reversion read: price near the lower band is a dip, upper band is stretched."""
    price = ix.closes[-1] if ix.closes else None
    up = ind.last_non_none(ix.boll_up)
    low = ind.last_non_none(ix.boll_low)
    mid = ind.last_non_none(ix.boll_mid)
    if price is None or up is None or low is None or mid is None or up == low:
        return Signal("News Credibility Analyst", "Market News Research", HOLD, 0.3,
                      "Not enough history for Bollinger Bands.", "bands n/a")
    pos = (price - low) / (up - low)  # 0 at lower band, 1 at upper
    if pos <= 0.15:
        return Signal("News Credibility Analyst", "Market News Research", BUY, 0.6,
                      "Price is hugging the lower band (possible oversold bounce).",
                      f"band pos {pos*100:.0f}%")
    if pos >= 0.85:
        return Signal("News Credibility Analyst", "Market News Research", SELL, 0.6,
                      "Price is hugging the upper band (possible overbought pullback).",
                      f"band pos {pos*100:.0f}%")
    return Signal("News Credibility Analyst", "Market News Research", HOLD, 0.4,
                  "Price is mid-band; no stretch.", f"band pos {pos*100:.0f}%")


def _roc_analyst(ix: Indicators) -> Signal:
    """Pure momentum via 12-day rate of change."""
    r = ind.last_non_none(ix.roc12)
    if r is None:
        return Signal("Market Impact Analyst", "Market News Research", HOLD, 0.3,
                      "Not enough history for rate-of-change.", "ROC n/a")
    if r > 3:
        return Signal("Market Impact Analyst", "Market News Research", BUY,
                      min(0.85, 0.45 + r / 30.0),
                      "Positive momentum over the last two weeks.", f"ROC {r:+.1f}%")
    if r < -3:
        return Signal("Market Impact Analyst", "Market News Research", SELL,
                      min(0.85, 0.45 + abs(r) / 30.0),
                      "Negative momentum over the last two weeks.", f"ROC {r:+.1f}%")
    return Signal("Market Impact Analyst", "Market News Research", HOLD, 0.4,
                  "Momentum is flat.", f"ROC {r:+.1f}%")


def _value_analyst(ix: Indicators) -> Signal:
    """Fundamentals-style positioning: where price sits in its 52-week range.

    This is a technical proxy for 'cheap vs expensive within its own range',
    NOT a valuation from financial statements -- labelled as such.
    """
    rp = ix.range_pos
    if rp is None:
        return Signal("Fundamental Research Analyst", "Equity Research", HOLD, 0.3,
                      "Not enough history for 52-week positioning.", "range n/a")
    if rp <= 25:
        return Signal("Fundamental Research Analyst", "Equity Research", BUY, 0.55,
                      "Price is in the lower quarter of its 52-week range (relatively cheap).",
                      f"range pos {rp:.0f}%")
    if rp >= 80:
        return Signal("Fundamental Research Analyst", "Equity Research", SELL, 0.5,
                      "Price is near its 52-week high (relatively expensive, less upside room).",
                      f"range pos {rp:.0f}%")
    return Signal("Fundamental Research Analyst", "Equity Research", HOLD, 0.4,
                  "Price is mid-range in its 52-week band.", f"range pos {rp:.0f}%")


def _trend_strength_analyst(ix: Indicators) -> Signal:
    """Trend strength via price vs EMA20 slope and distance."""
    price = ix.closes[-1] if ix.closes else None
    e = ind.last_non_none(ix.ema20)
    if price is None or e is None or e == 0:
        return Signal("Pre-Earnings Intelligence Analyst", "Equity Research", HOLD, 0.3,
                      "Not enough history for trend strength.", "ema n/a")
    dist = (price - e) / e * 100.0
    if dist > 1.5:
        return Signal("Pre-Earnings Intelligence Analyst", "Equity Research", BUY,
                      min(0.8, 0.45 + abs(dist) / 15.0),
                      "Price is holding above its 20-day EMA (constructive).",
                      f"{dist:+.1f}% vs EMA20")
    if dist < -1.5:
        return Signal("Pre-Earnings Intelligence Analyst", "Equity Research", SELL,
                      min(0.8, 0.45 + abs(dist) / 15.0),
                      "Price is slipping below its 20-day EMA (weak).",
                      f"{dist:+.1f}% vs EMA20")
    return Signal("Pre-Earnings Intelligence Analyst", "Equity Research", HOLD, 0.4,
                  "Price is sitting on its 20-day EMA.", f"{dist:+.1f}% vs EMA20")


def news_sentiment_signal(news_score: Optional[float], note: str) -> Optional[Signal]:
    """Build a Sentiment Analyst vote from a news sentiment score (-1..+1).

    Headline sentiment is noisy, so confidence is kept modest and the reason
    makes clear it reflects published headlines, not verified events.
    """
    if news_score is None:
        return None
    if news_score > 0.1:
        action = BUY
    elif news_score < -0.1:
        action = SELL
    else:
        action = HOLD
    conf = max(0.2, min(0.6, abs(news_score)))  # deliberately capped
    return Signal(
        "News Sentiment Analyst", "Market News Research", action, conf,
        "Recent published headlines lean " +
        ("positive." if action == BUY else "negative." if action == SELL else "mixed/neutral."),
        note or "headline sentiment",
    )


# Ordered list of analyst callables grouped by department Lead.
ANALYSTS_BY_LEAD: Dict[str, List[Callable[[Indicators], Signal]]] = {
    "Market News Research Lead": [
        _trend_analyst, _momentum_analyst, _macd_analyst,
        _bollinger_analyst, _roc_analyst,
    ],
    "Equity Research Lead": [_value_analyst, _trend_strength_analyst],
    "Head of Industry & Geopolitical Research": [_volatility_analyst],
    "Head of Market Activity & Ownership Research": [_volume_analyst],
}


def _aggregate(signals: List[Signal]) -> (str, float):
    """Confidence-weighted average of signal scores -> (action, confidence)."""
    if not signals:
        return HOLD, 0.0
    total_score = sum(s.score for s in signals)
    avg_score = total_score / len(signals)
    action = _action_from_score(avg_score)
    confidence = min(1.0, abs(avg_score) if action != HOLD else
                     1.0 - sum(abs(s.score) for s in signals) / len(signals))
    confidence = max(0.1, min(0.95, confidence if action != HOLD else 0.4 + confidence * 0.2))
    return action, confidence


def run_analysis(series: PriceSeries, news_score: Optional[float] = None,
                 news_note: str = "") -> ChiefVerdict:
    """Full pipeline: specialists -> Leads -> Chief verdict for one ticker.

    If a news sentiment score is supplied, a News Sentiment Analyst vote is added
    to the Market News Research desk.
    """
    ix = compute_indicators(series)
    lead_verdicts: List[LeadVerdict] = []

    lead_departments = {
        "Market News Research Lead": "Market News Research",
        "Equity Research Lead": "Equity Research",
        "Head of Industry & Geopolitical Research": "Industry and Geopolitical Research",
        "Head of Market Activity & Ownership Research": "Market Activity and Ownership",
    }

    news_sig = news_sentiment_signal(news_score, news_note)

    for lead_name, analysts in ANALYSTS_BY_LEAD.items():
        signals = [fn(ix) for fn in analysts]
        if lead_name == "Market News Research Lead" and news_sig is not None:
            signals.append(news_sig)
        action, conf = _aggregate(signals)
        buys = sum(1 for s in signals if s.action == BUY)
        sells = sum(1 for s in signals if s.action == SELL)
        rationale = f"{buys} buy / {sells} sell among {len(signals)} signal(s)."
        lead_verdicts.append(LeadVerdict(
            lead=lead_name,
            department=lead_departments[lead_name],
            action=action,
            confidence=round(conf, 2),
            signals=signals,
            rationale=rationale,
        ))

    # Chief combines Leads (weighted by each Lead's confidence).
    all_signals = [s for lv in lead_verdicts for s in lv.signals]
    chief_score = (sum(s.score for s in all_signals) / len(all_signals)) if all_signals else 0.0
    chief_action = _action_from_score(chief_score)
    chief_conf = max(0.1, min(0.95, abs(chief_score) + 0.1))

    reasons = [f"{s.bot}: {s.reason} ({s.metric})" for s in all_signals]
    actions_present = {lv.action for lv in lead_verdicts}
    disagreements = []
    if BUY in actions_present and SELL in actions_present:
        disagreements.append("Departments disagree: some bullish, some bearish signals.")

    return ChiefVerdict(
        ticker=series.ticker,
        action=chief_action,
        confidence=round(chief_conf, 2),
        score=round(chief_score, 3),
        lead_verdicts=lead_verdicts,
        reasons=reasons,
        disagreements=disagreements,
    )
