"use strict";

// Grok Signal Desk frontend. Pure vanilla JS, hand-drawn SVG chart, no libraries.

const $ = (id) => document.getElementById(id);

function show(el) { el.hidden = false; }
function hide(el) { el.hidden = true; }

let currentTimeframe = "daily";
let currencySymbol = "\u20b9";

// --- live signals bar ---------------------------------------------------
const LIVE_REFRESH_MS = 60000;
let liveTimer = null;
let liveCountdown = null;

async function loadWatch() {
  const meta = $("liveMeta");
  const track = $("liveTrack");
  try {
    meta.textContent = "scanning…";
    const res = await fetch("/api/analyze?watch=1&timeframe=" + currentTimeframe + "&t=" + Date.now());
    const data = await res.json();
    const rows = (data.watch || []).filter((r) => r.ok !== false);
    renderWatch(rows);
    const when = new Date().toLocaleTimeString();
    meta.textContent = `${currentTimeframe} · updated ${when} · auto-refresh 60s (delayed data)`;
  } catch (e) {
    meta.textContent = "live feed unavailable";
  }
}

function renderWatch(rows) {
  const track = $("liveTrack");
  if (!rows || !rows.length) { track.innerHTML = `<span class="live-meta">no signals</span>`; return; }
  // Sort so actionable (BUY/SELL) show first, then WAIT.
  const rank = (a) => (a.action && a.action.startsWith("BUY") ? 0 : a.action && a.action.startsWith("SELL") ? 1 : 2);
  rows.sort((a, b) => rank(a) - rank(b));
  track.innerHTML = rows.map((r) => {
    const key = r.action && r.action.startsWith("BUY") ? "buy" : r.action && r.action.startsWith("SELL") ? "sell" : "wait";
    const shortAct = key === "buy" ? "BUY" : key === "sell" ? "SELL" : "WAIT";
    const px = r.price != null ? (r.currency_symbol || "") + r.price : "";
    return `<div class="live-pill ${key}" data-tk="${escapeHtml(r.ticker)}">
      <span class="lp-tk">${escapeHtml(r.ticker)}</span>
      <span class="lp-px">${escapeHtml(px)}</span>
      <span class="lp-act">${shortAct}</span>
    </div>`;
  }).join("");
  track.querySelectorAll(".live-pill").forEach((el) => {
    el.addEventListener("click", () => {
      const tk = el.dataset.tk;
      $("ticker").value = tk;
      analyze(tk);
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

function startLive() {
  loadWatch();
  if (liveTimer) clearInterval(liveTimer);
  liveTimer = setInterval(loadWatch, LIVE_REFRESH_MS);
}

async function loadPopular() {
  try {
    const res = await fetch("/api/analyze?list=1");
    const data = await res.json();
    const nse = $("popularNSE");
    const us = $("popularUS");
    nse.innerHTML = ""; us.innerHTML = "";
    (data.popular || []).forEach((p) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "chip";
      chip.textContent = p.ticker;
      chip.title = p.name;
      chip.onclick = () => { $("ticker").value = p.ticker; analyze(p.ticker); };
      (p.market === "US" ? us : nse).appendChild(chip);
    });
  } catch (e) { /* popular chips are optional */ }
}

function setStatus(msg, isError) {
  const s = $("status");
  s.textContent = msg;
  s.className = "status" + (isError ? " error" : "");
  show(s);
}

async function analyze(ticker) {
  ticker = (ticker || $("ticker").value || "").trim().toUpperCase();
  if (!ticker) { setStatus("Enter an NSE ticker, e.g. RELIANCE.", true); return; }
  $("analyzeBtn").disabled = true;
  hide($("result"));
  setStatus(`Running the desk on ${ticker} (${currentTimeframe})…`, false);
  try {
    const res = await fetch("/api/analyze?ticker=" + encodeURIComponent(ticker) + "&timeframe=" + currentTimeframe);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || "Request failed");
    render(data);
    hide($("status"));
    show($("result"));
  } catch (e) {
    setStatus("Could not analyze " + ticker + ": " + e.message, true);
  } finally {
    $("analyzeBtn").disabled = false;
  }
}

function render(d) {
  const v = d.verdict;
  currencySymbol = d.currency_symbol || "\u20b9";

  // Honest warning banner (intraday / losing track record)
  const warn = $("warnBanner");
  const warnText = (d.warning || "").trim();
  if (warnText) { warn.hidden = false; warn.textContent = warnText; }
  else { warn.hidden = true; warn.textContent = ""; }

  // ACTION NOW banner (the headline answer: buy / sell / wait)
  renderActionNow(d.action_now, d.performance, d.last_close);

  // Verdict badge + headline
  const badge = $("verdictBadge");
  badge.textContent = v.action;
  badge.className = "verdict-badge " + v.action;
  $("verdictTicker").textContent = d.ticker + (d.last_close ? "  ·  " + currencySymbol + d.last_close : "") + "  ·  " + (d.timeframe === "intraday" ? "15m" : "Daily");
  const dataBadge = $("dataBadge");
  const isLive = d.data_source === "yahoo" || d.data_source === "stooq";
  dataBadge.hidden = false;
  dataBadge.className = "data-badge " + (isLive ? "live" : "demo");
  dataBadge.textContent = isLive
    ? ("● LIVE · " + d.data_source)
    : "● DEMO DATA";
  $("verdictLine").textContent = verdictLine(v.action);
  const pct = Math.round((v.confidence || 0) * 100);
  $("confFill").style.width = pct + "%";
  $("confLabel").textContent = "Confidence " + pct + "%  ·  aggregate score " + v.score;

  // Indicator strip
  const ind = d.indicators || {};
  const range52 = (ind.low_52w != null && ind.high_52w != null)
    ? `${ind.low_52w} – ${ind.high_52w}` : null;
  $("indicatorStrip").innerHTML = [
    indCard("RSI (14)", ind.rsi14),
    indCard("SMA 20", ind.sma20),
    indCard("SMA 50", ind.sma50),
    indCard("Volatility %/day", ind.volatility),
    indCard("52-wk range", range52),
    indCard("Range pos %", ind.range_pos),
  ].join("");

  // Charts
  drawChart(d.chart, d.events);
  drawRsi(d.chart);
  drawMacd(d.chart);
  const note = $("sourceNote");
  note.textContent = d.data_note || "";
  note.className = "source-note" + (d.data_source === "demo" ? " demo" : "");

  // Last-updated line
  $("updatedNote").textContent = updatedText(d);

  // Near-term bias, signals log, news
  renderBias(d.bias);
  renderEvents(d.events);
  renderNews(d.news);

  // Lead desks
  $("leads").innerHTML = (d.leads || []).map(leadCard).join("");

  // Reasons + disagreements
  $("reasons").innerHTML = (v.reasons || []).map((r) => `<li>${escapeHtml(r)}</li>`).join("");
  const dis = $("disagreements");
  dis.innerHTML = (v.disagreements || []).map((x) => `⚠ ${escapeHtml(x)}`).join("<br/>");

  $("disclaimer").textContent = v.disclaimer || "";
}

function verdictLine(action) {
  if (action === "BUY") return "The desk leans bullish on current technicals.";
  if (action === "SELL") return "The desk leans bearish on current technicals.";
  return "Signals are mixed or neutral — the desk suggests waiting.";
}

function indCard(k, val) {
  return `<div class="ind"><div class="k">${k}</div><div class="v">${val == null ? "—" : val}</div></div>`;
}

function leadCard(l) {
  const sigs = (l.signals || []).map((s) => `
    <div class="sig">
      <div class="sig-top">
        <span class="sig-bot">${escapeHtml(s.bot)}</span>
        <span class="pill ${s.action}">${s.action} ${Math.round(s.confidence * 100)}%</span>
      </div>
      <div class="sig-reason">${escapeHtml(s.reason)}</div>
      <div class="sig-metric">${escapeHtml(s.metric || "")}</div>
    </div>`).join("");
  return `
    <div class="lead">
      <div class="lead-head">
        <h4>${escapeHtml(l.lead)}</h4>
        <span class="pill ${l.action}">${l.action}</span>
      </div>
      <div class="dept">${escapeHtml(l.department)} · ${escapeHtml(l.rationale)}</div>
      ${sigs}
    </div>`;
}

// --- hand-drawn SVG candlestick chart with time-aware axis -------------
function drawChart(chart, events) {
  const host = $("chart");
  if (!chart || !chart.close || chart.close.length === 0) { host.innerHTML = ""; return; }

  const W = 960, H = 340, padL = 54, padR = 14, padT = 14, padB = 28;
  const open = chart.open || chart.close;
  const high = chart.high || chart.close;
  const low = chart.low || chart.close;
  const close = chart.close;
  const sma20 = chart.sma20 || [];
  const sma50 = chart.sma50 || [];
  const dates = chart.dates || [];
  const intraday = !!chart.intraday;
  const n = close.length;

  // y-range across highs/lows and the moving averages
  let lo = Infinity, hi = -Infinity;
  const consider = (arr) => arr.forEach((v) => { if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } });
  consider(high); consider(low); consider(sma20); consider(sma50);
  if (!isFinite(lo) || !isFinite(hi) || lo === hi) { lo = Math.min(...close); hi = Math.max(...close) || lo + 1; }
  const pad = (hi - lo) * 0.06 || 1;
  lo -= pad; hi += pad;

  const plotW = W - padL - padR;
  const x = (i) => padL + (n <= 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (val) => padT + (1 - (val - lo) / (hi - lo)) * (H - padT - padB);
  const cw = Math.max(1.5, plotW / n * 0.62);  // candle body width

  const path = (arr) => {
    let d = "", started = false;
    for (let i = 0; i < arr.length; i++) {
      if (arr[i] == null) { started = false; continue; }
      d += (started ? " L" : " M") + x(i).toFixed(1) + " " + y(arr[i]).toFixed(1);
      started = true;
    }
    return d.trim();
  };

  // horizontal grid + price labels
  let grid = "";
  for (let g = 0; g <= 4; g++) {
    const val = lo + (hi - lo) * (g / 4);
    const yy = y(val).toFixed(1);
    grid += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="#26303f" stroke-width="1"/>`;
    grid += `<text x="${padL - 8}" y="${(+yy + 4).toFixed(1)}" fill="#8b97a7" font-size="11" text-anchor="end">${val.toFixed(2)}</text>`;
  }

  // candles
  let candles = "";
  for (let i = 0; i < n; i++) {
    if (close[i] == null) continue;
    const o = open[i] != null ? open[i] : close[i];
    const c = close[i];
    const hV = high[i] != null ? high[i] : Math.max(o, c);
    const lV = low[i] != null ? low[i] : Math.min(o, c);
    const up = c >= o;
    const col = up ? "#22c55e" : "#ef4444";
    const cx = x(i);
    const yO = y(o), yC = y(c);
    const bodyTop = Math.min(yO, yC);
    const bodyH = Math.max(1, Math.abs(yC - yO));
    candles += `<line x1="${cx.toFixed(1)}" y1="${y(hV).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${y(lV).toFixed(1)}" stroke="${col}" stroke-width="1"/>`;
    candles += `<rect x="${(cx - cw / 2).toFixed(1)}" y="${bodyTop.toFixed(1)}" width="${cw.toFixed(1)}" height="${bodyH.toFixed(1)}" fill="${col}" opacity="0.9"/>`;
  }

  // --- time-aware X axis ---
  let xlabels = "", daySeps = "";
  const labelAt = (i, text, bold) => {
    const col = bold ? "#c7d0dc" : "#8b97a7";
    const weight = bold ? "600" : "400";
    xlabels += `<text x="${x(i).toFixed(1)}" y="${H - 7}" fill="${col}" font-size="11" font-weight="${weight}" text-anchor="middle">${text}</text>`;
  };

  if (!intraday) {
    const picks = n <= 1 ? [0] : [0, Math.floor((n - 1) / 2), n - 1];
    picks.forEach((i) => { if (dates[i]) labelAt(i, fmtDay(dates[i])); });
  } else {
    let lastDay = null;
    let lastLabelX = -999;
    for (let i = 0; i < n; i++) {
      const d = dates[i]; if (!d) continue;
      const parts = d.split(" ");
      const datePart = parts[0], timePart = parts[1] || "";
      if (datePart !== lastDay) {
        lastDay = datePart;
        if (i > 0) daySeps += `<line x1="${x(i).toFixed(1)}" y1="${padT}" x2="${x(i).toFixed(1)}" y2="${H - padB}" stroke="#2b3a4e" stroke-width="1" stroke-dasharray="3 3"/>`;
        labelAt(i, fmtDay(datePart), true);
        lastLabelX = x(i);
      } else if (timePart && timePart.endsWith(":00") && x(i) - lastLabelX > plotW / 10) {
        labelAt(i, timePart);
        lastLabelX = x(i);
      }
    }
  }

  // BUY/SELL markers
  let markers = "";
  (events || []).forEach((e) => {
    const i = e.index;
    if (i == null || i < 0 || i >= n || close[i] == null) return;
    const cx = x(i), cy = y(close[i]);
    const tipText = `${e.date} — ${e.action} signal (${e.kind}); price ${currencySymbol}${e.price}`;
    if (e.action === "BUY") {
      const ty = cy + 18;
      markers += `<path d="M${cx.toFixed(1)} ${(ty - 9).toFixed(1)} L${(cx - 5).toFixed(1)} ${ty.toFixed(1)} L${(cx + 5).toFixed(1)} ${ty.toFixed(1)} Z" fill="#22c55e"><title>${tipText}</title></path>`;
    } else {
      const ty = cy - 18;
      markers += `<path d="M${cx.toFixed(1)} ${(ty + 9).toFixed(1)} L${(cx - 5).toFixed(1)} ${ty.toFixed(1)} L${(cx + 5).toFixed(1)} ${ty.toFixed(1)} Z" fill="#ef4444"><title>${tipText}</title></path>`;
    }
  });

  host.innerHTML = `
  <div id="ohlcHeader" class="ohlc-header"></div>
  <svg id="priceSvg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Candlestick chart">
    ${grid}
    ${daySeps}
    ${candles}
    <path d="${path(sma50)}" fill="none" stroke="#b07cff" stroke-width="1.4" opacity="0.9"/>
    <path d="${path(sma20)}" fill="none" stroke="#f0a35e" stroke-width="1.4" opacity="0.9"/>
    ${markers}
    ${xlabels}
    <line id="crosshair" x1="0" y1="${padT}" x2="0" y2="${H - padB}" stroke="#8b97a7" stroke-width="1" stroke-dasharray="4 3" visibility="hidden"/>
    <circle id="hoverClose" r="3.5" fill="#5b9dff" stroke="#0b0f17" stroke-width="1" visibility="hidden"/>
    <circle id="hoverS20" r="3" fill="#f0a35e" stroke="#0b0f17" stroke-width="1" visibility="hidden"/>
    <circle id="hoverS50" r="3" fill="#b07cff" stroke="#0b0f17" stroke-width="1" visibility="hidden"/>
    <rect id="hoverCapture" x="${padL}" y="${padT}" width="${plotW}" height="${H - padT - padB}" fill="transparent"/>
  </svg>
  <div id="chartTooltip" class="chart-tooltip" hidden></div>`;

  // Save geometry + series so the hover handler can map pixels -> data index.
  _chartState = {
    W, H, padL, padR, padT, padB, n,
    xOf: x, yOf: y,
    open, high, low, close, sma20, sma50,
    rsi: (chart.rsi14 || []),
    dates, intraday,
  };
  // Default the OHLC header to the latest bar.
  updateOhlcHeader(n - 1);
  attachHover(host);
}

// Format an ISO date "2026-10-09" -> "9 Oct 2026"; passes times through.
function fmtDay(s) {
  if (!s) return "";
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return s;
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  return `${parseInt(m[3], 10)} ${months[parseInt(m[2], 10) - 1]} ${m[1]}`;
}

// OHLC header line (like a terminal: O/H/L/C + change).
function updateOhlcHeader(i) {
  const st = _chartState;
  const el = document.getElementById("ohlcHeader");
  if (!st || !el || i == null || i < 0 || i >= st.n) return;
  const o = st.open[i], h = st.high[i], l = st.low[i], c = st.close[i];
  const prev = i > 0 ? st.close[i - 1] : o;
  const chg = (c != null && prev != null) ? c - prev : 0;
  const chgPct = prev ? (chg / prev * 100) : 0;
  const cls = chg >= 0 ? "up" : "down";
  const sign = chg >= 0 ? "+" : "";
  const cs = currencySymbol;
  const f = (v) => (v == null ? "—" : cs + Number(v).toFixed(2));
  el.innerHTML =
    `<span class="ohlc-when">${escapeHtml(fmtDay(st.dates[i]) + (st.intraday && st.dates[i] ? " " + (st.dates[i].split(" ")[1] || "") : ""))}</span>` +
    `<span class="ohlc-i">O <b>${f(o)}</b></span>` +
    `<span class="ohlc-i">H <b>${f(h)}</b></span>` +
    `<span class="ohlc-i">L <b>${f(l)}</b></span>` +
    `<span class="ohlc-i">C <b>${f(c)}</b></span>` +
    `<span class="ohlc-chg ${cls}">${sign}${chg.toFixed(2)} (${sign}${chgPct.toFixed(2)}%)</span>`;
}

// --- interactive hover tooltip -----------------------------------------
let _chartState = null;

function attachHover(host) {
  const svg = host.querySelector("#priceSvg");
  const capture = host.querySelector("#hoverCapture");
  const tip = host.querySelector("#chartTooltip");
  const cross = host.querySelector("#crosshair");
  const dotC = host.querySelector("#hoverClose");
  const dot20 = host.querySelector("#hoverS20");
  const dot50 = host.querySelector("#hoverS50");
  if (!svg || !capture) return;

  const fmt = (v) => (v == null ? "—" : currencySymbol + Number(v).toFixed(2));

  function nearestIndex(evt) {
    const rect = svg.getBoundingClientRect();
    const st = _chartState;
    // Map client X -> SVG viewBox X (viewBox width is st.W).
    const vx = (evt.clientX - rect.left) / rect.width * st.W;
    const usable = st.W - st.padL - st.padR;
    let frac = (vx - st.padL) / usable;
    frac = Math.max(0, Math.min(1, frac));
    return Math.round(frac * (st.n - 1));
  }

  function moveTo(evt) {
    const st = _chartState;
    if (!st || st.n < 2) return;
    const i = nearestIndex(evt);
    const cx = st.xOf(i);

    cross.setAttribute("x1", cx); cross.setAttribute("x2", cx);
    cross.setAttribute("visibility", "visible");

    const place = (dot, val) => {
      if (val == null) { dot.setAttribute("visibility", "hidden"); return; }
      dot.setAttribute("cx", cx); dot.setAttribute("cy", st.yOf(val));
      dot.setAttribute("visibility", "visible");
    };
    place(dotC, st.close[i]);
    place(dot20, st.sma20[i]);
    place(dot50, st.sma50[i]);

    // Drive the terminal-style OHLC header too.
    updateOhlcHeader(i);

    const rsiVal = st.rsi[i];
    tip.hidden = false;
    tip.innerHTML =
      `<div class="tt-date">${st.dates[i] || ""}</div>` +
      `<div class="tt-row"><span class="tt-k">Open</span><span>${fmt(st.open[i])}</span></div>` +
      `<div class="tt-row"><span class="tt-k">High</span><span>${fmt(st.high[i])}</span></div>` +
      `<div class="tt-row"><span class="tt-k">Low</span><span>${fmt(st.low[i])}</span></div>` +
      `<div class="tt-row"><span class="tt-k" style="color:#5b9dff">Close</span><span>${fmt(st.close[i])}</span></div>` +
      `<div class="tt-row"><span class="tt-k" style="color:#f0a35e">SMA 20</span><span>${fmt(st.sma20[i])}</span></div>` +
      `<div class="tt-row"><span class="tt-k" style="color:#b07cff">SMA 50</span><span>${fmt(st.sma50[i])}</span></div>` +
      `<div class="tt-row"><span class="tt-k" style="color:#5bd1c4">RSI</span><span>${rsiVal == null ? "—" : Number(rsiVal).toFixed(1)}</span></div>`;

    // Position the HTML tooltip near the cursor, inside the chart box.
    const rect = svg.getBoundingClientRect();
    const hostRect = host.getBoundingClientRect();
    let left = evt.clientX - hostRect.left + 14;
    let top = evt.clientY - hostRect.top + 10;
    if (left + 150 > hostRect.width) left = evt.clientX - hostRect.left - 160;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }

  function leave() {
    tip.hidden = true;
    cross.setAttribute("visibility", "hidden");
    dotC.setAttribute("visibility", "hidden");
    dot20.setAttribute("visibility", "hidden");
    dot50.setAttribute("visibility", "hidden");
    if (_chartState) updateOhlcHeader(_chartState.n - 1);  // reset to latest bar
  }

  capture.addEventListener("mousemove", moveTo);
  capture.addEventListener("mouseleave", leave);
  // Touch support
  capture.addEventListener("touchmove", (e) => {
    if (e.touches && e.touches[0]) { moveTo(e.touches[0]); e.preventDefault(); }
  }, { passive: false });
}

function renderActionNow(a, perf, lastClose) {
  const card = $("actionNow");
  if (!a) { card.hidden = true; return; }
  card.hidden = false;

  // Map "BUY NOW" / "SELL NOW" / "WAIT" to a style key.
  const key = a.action.startsWith("BUY") ? "buy" : a.action.startsWith("SELL") ? "sell" : "wait";
  card.className = "action-now card " + key;
  const badge = $("anBadge");
  badge.className = "an-badge " + key;
  badge.innerHTML = a.action.replace(" ", "<br/>");

  $("anHeadline").textContent = a.headline || "";
  const conf = Math.round((a.confidence || 0) * 100);
  $("anReason").textContent = a.reason + "  ·  confidence " + conf + "%";

  // Levels: current price, trigger, stop, target
  const cs = currencySymbol;
  const levels = [];
  if (lastClose != null) levels.push(level("Current price", cs + lastClose));
  if (a.trigger_date) levels.push(level("Signal time", a.trigger_date));
  if (a.trigger_price != null) levels.push(level("Signal price", cs + a.trigger_price));
  if (a.stop_loss != null) levels.push(level("Suggested stop", cs + a.stop_loss));
  if (a.target != null) levels.push(level("Suggested target", cs + a.target));
  $("anLevels").innerHTML = levels.join("");

  const perfEl = $("anPerf");
  if (perf && perf.note) {
    perfEl.textContent = "Signal track record: " + perf.note;
    perfEl.className = "an-perf" + (perf.verdict === "losing" ? " losing" : perf.verdict === "profitable" ? " profitable" : "");
  } else {
    perfEl.textContent = "";
    perfEl.className = "an-perf";
  }
}

function level(k, v) {
  return `<div class="an-level"><span class="k">${escapeHtml(k)}</span><span class="v">${escapeHtml(v)}</span></div>`;
}

function renderBias(bias) {
  if (!bias) return;
  const badge = $("biasBadge");
  badge.textContent = bias.direction;
  badge.className = "bias-badge " + bias.direction;
  $("biasNote").textContent = bias.note;
  $("biasConf").textContent = "Confidence " + Math.round((bias.confidence || 0) * 100) + "%  ·  horizon: " + (bias.horizon || "");
}

function renderEvents(events) {
  const host = $("eventsLog");
  if (!events || !events.length) { host.innerHTML = `<p class="empty">No buy/sell triggers in this window.</p>`; return; }
  const rows = events.slice().reverse().map((e) => `
    <div class="ev">
      <span class="ev-badge ${e.action}">${e.action}</span>
      <span class="ev-date">${escapeHtml(e.date)}</span>
      <span class="ev-kind">${escapeHtml(e.kind)}</span>
      <span class="ev-price">${currencySymbol}${e.price}</span>
    </div>`).join("");
  host.innerHTML = rows;
}

function renderNews(news) {
  const tag = $("newsTag");
  const host = $("newsList");
  if (!news || !news.available) {
    tag.textContent = "";
    host.innerHTML = `<p class="empty">${escapeHtml((news && news.note) || "News unavailable.")}</p>`;
    return;
  }
  tag.textContent = news.sentiment + " · " + news.note;
  if (!news.headlines || !news.headlines.length) {
    host.innerHTML = `<p class="empty">No recent headlines.</p>`;
    return;
  }
  host.innerHTML = news.headlines.map((h) => `
    <div class="news-item">
      <span class="news-dot ${h.sentiment}"></span>
      <div>
        <div class="news-title">${escapeHtml(h.title)}</div>
        <div class="news-when">${escapeHtml(h.published || "")}</div>
      </div>
    </div>`).join("");
}

// --- RSI sub-chart (0..100 with 30/70 guide lines) ---------------------
function drawRsi(chart) {
  const host = $("rsiChart");
  const rsi = (chart && chart.rsi14) || [];
  const n = rsi.length;
  if (!n) { host.innerHTML = ""; return; }

  const W = 960, H = 120, padL = 52, padR = 14, padT = 8, padB = 18;
  const x = (i) => padL + (i / (n - 1)) * (W - padL - padR);
  const y = (v) => padT + (1 - v / 100) * (H - padT - padB);

  let grid = "";
  [30, 50, 70].forEach((lvl) => {
    const yy = y(lvl).toFixed(1);
    const color = lvl === 50 ? "#26303f" : "#3a4557";
    const dash = lvl === 50 ? "" : 'stroke-dasharray="4 4"';
    grid += `<line x1="${padL}" y1="${yy}" x2="${W - padR}" y2="${yy}" stroke="${color}" stroke-width="1" ${dash}/>`;
    grid += `<text x="${padL - 8}" y="${(+yy + 4).toFixed(1)}" fill="#8b97a7" font-size="10" text-anchor="end">${lvl}</text>`;
  });

  let dStr = "", started = false;
  for (let i = 0; i < n; i++) {
    if (rsi[i] == null) { started = false; continue; }
    dStr += (started ? " L" : " M") + x(i).toFixed(1) + " " + y(rsi[i]).toFixed(1);
    started = true;
  }

  host.innerHTML = `
  <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="RSI">
    ${grid}
    <path d="${dStr.trim()}" fill="none" stroke="#5bd1c4" stroke-width="1.8"/>
  </svg>`;
}

// --- MACD sub-chart (histogram + line + signal) ------------------------
function drawMacd(chart) {
  const host = $("macdChart");
  const line = (chart && chart.macd_line) || [];
  const sig = (chart && chart.macd_signal) || [];
  const hist = (chart && chart.macd_hist) || [];
  const n = line.length;
  if (!n) { host.innerHTML = ""; return; }

  const W = 960, H = 130, padL = 52, padR = 14, padT = 10, padB = 18;
  let lo = Infinity, hi = -Infinity;
  [line, sig, hist].forEach((arr) => arr.forEach((v) => { if (v != null) { lo = Math.min(lo, v); hi = Math.max(hi, v); } }));
  if (!isFinite(lo) || !isFinite(hi)) { host.innerHTML = ""; return; }
  if (lo === hi) { lo -= 1; hi += 1; }
  const padv = (hi - lo) * 0.1 || 1; lo -= padv; hi += padv;

  const x = (i) => padL + (i / (n - 1)) * (W - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (H - padT - padB);
  const zeroY = y(0).toFixed(1);
  const barW = Math.max(1, (W - padL - padR) / n * 0.7);

  let bars = "";
  for (let i = 0; i < n; i++) {
    if (hist[i] == null) continue;
    const yy = y(hist[i]);
    const top = Math.min(yy, +zeroY);
    const h = Math.abs(yy - +zeroY);
    const color = hist[i] >= 0 ? "#22c55e" : "#ef4444";
    bars += `<rect x="${(x(i) - barW / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="${color}" opacity="0.55"/>`;
  }

  const path = (arr) => {
    let s = "", started = false;
    for (let i = 0; i < arr.length; i++) {
      if (arr[i] == null) { started = false; continue; }
      s += (started ? " L" : " M") + x(i).toFixed(1) + " " + y(arr[i]).toFixed(1);
      started = true;
    }
    return s.trim();
  };

  host.innerHTML = `
  <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="MACD">
    <line x1="${padL}" y1="${zeroY}" x2="${W - padR}" y2="${zeroY}" stroke="#26303f" stroke-width="1"/>
    ${bars}
    <path d="${path(sig)}" fill="none" stroke="#f0a35e" stroke-width="1.5"/>
    <path d="${path(line)}" fill="none" stroke="#5b9dff" stroke-width="1.8"/>
  </svg>`;
}

function updatedText(d) {
  const parts = [];
  if (d.last_bar_date) parts.push("Latest bar: " + d.last_bar_date);
  if (d.generated_at) {
    const t = new Date(d.generated_at);
    if (!isNaN(t)) parts.push("Analyzed: " + t.toLocaleString());
  }
  return parts.join("  ·  ");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// init
document.addEventListener("DOMContentLoaded", () => {
  loadPopular();
  startLive();
  $("searchForm").addEventListener("submit", (e) => { e.preventDefault(); analyze(); });

  const refreshBtn = $("liveRefresh");
  if (refreshBtn) refreshBtn.addEventListener("click", loadWatch);

  // Timeframe toggle: switch Daily / Intraday, refresh the live bar + current ticker.
  const toggle = $("tfToggle");
  if (toggle) {
    toggle.querySelectorAll(".tf-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        toggle.querySelectorAll(".tf-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        currentTimeframe = btn.dataset.tf;
        loadWatch();
        const t = ($("ticker").value || "").trim();
        if (t) analyze(t);
      });
    });
  }
});
