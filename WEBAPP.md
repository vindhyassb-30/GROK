# Grok Signal Desk — Buy/Sell/Hold Web App

A browser app where a research desk of bots reads a stock's chart and votes
**BUY / SELL / HOLD**. Built for Vercel (serverless Python + static frontend),
with **zero third-party dependencies** and a **hand-drawn SVG chart** (no
external scripts).

> Research and education only. These are technical-analysis signals, not
> financial advice, and they cannot guarantee outcomes.

## What it does

1. You enter an NSE ticker (e.g. `RELIANCE`, `TCS`, `INFY`).
2. The backend fetches daily price history from **Stooq** (free, no API key).
   If the fetch fails it falls back to clearly-labelled demo data.
3. Specialist bots each compute one signal from the price action:
   - **Stock Movement Analyst** — trend (SMA 20 vs SMA 50)
   - **Research Analyst** — momentum (RSI 14)
   - **Sentiment Analyst** — MACD crossover
   - **Geopolitical Risk Analyst** — volatility / risk
   - **Market Volume Intelligence Analyst** — volume confirmation
4. Each department Lead combines its specialists; the Chief combines the Leads
   into a single verdict with a confidence score and plain-English reasons.
5. The page shows the verdict badge, a price + moving-average chart, the
   indicator readouts, each desk's vote, and the reasoning.

## Run it locally

```powershell
python devserver.py
```

Then open <http://localhost:8000> in your browser. Enter a ticker and click
Analyze (or click one of the suggestion chips).

Use a different port with `python devserver.py 5000`.

> Note: on some networks Stooq may be blocked, so local runs can show DEMO data
> (the chart and verdict still work; they're just computed on synthetic prices).
> On Vercel, the cloud function reaches Stooq and returns live data.

## Deploy to Vercel

The repo is already Vercel-ready:

```
api/analyze.py      serverless function  -> GET /api/analyze?ticker=RELIANCE
public/             static frontend (index.html, app.js, style.css)
engine/             the indicator + signal engine (pure stdlib)
vercel.json         routes /api + static, Python + static builders
requirements.txt    empty (standard library only)
```

Steps:

1. Push this folder to a Git repo (GitHub/GitLab/Bitbucket).
2. In Vercel, "New Project" → import the repo → deploy. No env vars needed.
3. Vercel detects `vercel.json`, builds the Python function and serves the
   static files. Your app is live at the assigned URL.

(Or run `vercel` with the Vercel CLI from this folder.)

## API

`GET /api/analyze?ticker=RELIANCE` → JSON:

```json
{
  "ticker": "RELIANCE",
  "data_source": "stooq",
  "last_close": 2910.5,
  "verdict": { "action": "BUY", "confidence": 0.62, "score": 0.41,
               "reasons": ["..."], "disagreements": [], "disclaimer": "..." },
  "indicators": { "rsi14": 58.2, "sma20": 2890.1, "sma50": 2805.4, "volatility": 1.3 },
  "leads": [ { "lead": "...", "action": "BUY", "signals": [ ... ] } ],
  "chart": { "dates": [...], "close": [...], "sma20": [...], "sma50": [...] }
}
```

`GET /api/analyze?list=1` → the popular-ticker suggestions.

## Note on the "23 bots" and daily routines

The full 23-bot desk (with scheduled daily routines) lives in the `grok_desk`
package. Vercel is serverless, so there's no always-on process to run daily
schedules — this app runs the analysis **on demand** each time you ask. The bots
you see voting here are the market-analysis specialists whose signals can be
computed from price data; news/ownership bots that need live filings are not
wired to a data feed yet.

## How to read the buy / sell / hold signal

The big badge at the top is the desk's combined verdict. Each bot votes and the
Chief blends the votes into one call plus a confidence score.

- **BUY** — more indicators point up than down. Historically-constructive setup
  (uptrend, positive momentum, price in a lower/cheaper part of its range).
- **SELL** — more indicators point down (downtrend, overbought, weakening
  momentum, price stretched near its highs).
- **HOLD** — signals conflict or are neutral; the desk suggests waiting for a
  clearer setup rather than acting.

**Confidence** matters as much as the label. A BUY at 20% confidence is weak and
basically a HOLD; a BUY at 70%+ means several bots agree.

### What each bot looks for

| Bot | Buy hint | Sell hint |
|---|---|---|
| Trend (SMA 20 vs 50) | short avg above long avg | short avg below long avg |
| Momentum (RSI 14) | RSI below ~30 (oversold) | RSI above ~70 (overbought) |
| MACD | MACD line crosses above signal | MACD line crosses below signal |
| Bollinger | price near lower band | price near upper band |
| Rate of change | positive 2-week momentum | negative 2-week momentum |
| Value (52-wk range) | price in lower quarter of range | price near 52-wk high |
| Trend strength | price holding above 20-day EMA | price slipping below 20-day EMA |
| Volatility | calm conditions | elevated risk → caution |
| Volume | rising volume confirms a rising price | rising volume confirms a falling price |

### A sane way to use it

1. Check the **verdict + confidence**. Ignore low-confidence calls.
2. Look at the **desk cards** — do the departments agree, or is one bullish and
   another bearish? Agreement is stronger.
3. Glance at the **RSI panel** (is it stretched above 70 / below 30?) and the
   **MACD panel** (is the histogram flipping from red to green or vice versa?).
4. Note the **52-week range position** — buying near the bottom of the range has
   more room than buying near the top.

> Reminder: this is a technical-analysis indicator for research and education.
> It is **not financial advice** and cannot guarantee outcomes. It does not know
> about company news, earnings, or fundamentals. Use it as one input, size
> positions responsibly, and never trade money you can't afford to lose.
