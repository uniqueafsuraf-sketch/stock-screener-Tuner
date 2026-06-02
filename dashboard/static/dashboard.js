(() => {
  const SIGNALS = [
    "VOLUME_SPIKE", "SELLOFF", "OVERSOLD", "AT_SUPPORT",
    "AT_RESISTANCE", "SELLOFF_AT_SUPPORT", "BREAKOUT_SETUP",
  ];

  const TAB_TITLES = {
    opportunities: "Setups",
    gainers: "Gainers",
    losers: "Losers",
    news: "News wire",
    all: "Full universe",
    ourbit: "Ourbit stocks",
  };

  const DATA_LIST_KEYS = [
    "opportunities", "all_stocks", "edge_plays", "gainers", "losers",
    "gaps", "high_rvol", "rel_strength", "unusual_activity", "ourbit_stocks",
  ];

  const COLS = 12;

  let data = null;
  let activeTab = "opportunities";
  let activeSignals = new Set();
  let sortKey = "score";
  let sortDir = -1;
  let prevPrices = {};
  let prevChanges = {};
  let tapeBuilt = false;
  let tapeSignature = "";
  let liveEventSource = null;
  let scanPollTimer = null;
  const LIVE_POLL_MS = 400;
  const MARKET_POLL_MS = 4000;
  const TAPE_TOP_N = 15;

  const $ = (id) => document.getElementById(id);

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }

  function fmtPrice(n) {
    return Number(n).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function defaultChartLinks(sym) {
    return {
      tradingview: `https://www.tradingview.com/chart/?symbol=${sym}`,
      yahoo: `https://finance.yahoo.com/quote/${sym}/chart/`,
      finviz: `https://finviz.com/quote.ashx?t=${sym}`,
      yahoo_news: `https://finance.yahoo.com/quote/${sym}/news/`,
    };
  }

  function gradeClass(g) {
    if (g === "A+") return "ap";
    if (g === "A") return "a";
    if (g === "B+" || g === "B") return "b";
    return "";
  }

  function updateStatusBanner() {
    const el = $("status-banner");
    if (!el) return;
    if (data?.scanning) {
      el.hidden = false;
      el.className = "status-banner scanning";
      el.textContent = "Refreshing scan in background… Your data stays visible until the update completes.";
      return;
    }
    if (data?.last_error && !data?.all_stocks?.length) {
      el.hidden = false;
      el.className = "status-banner error";
      el.textContent = `Scan issue: ${data.last_error}. Click Refresh to retry.`;
      return;
    }
    el.hidden = true;
  }

  function updateLiveBadge(live) {
    const badge = $("live-badge");
    if (!badge) return;
    const text = badge.querySelector(".status-text");
    if (live?.error) {
      badge.className = "status-pill off";
      if (text) text.textContent = "Connection error";
      return;
    }
    if (live?.count > 0) {
      badge.className = "status-pill live";
      const tick = live.tick != null ? ` #${live.tick}` : "";
      if (text) text.textContent = `Live${tick} · ${live.updated_at || "—"}`;
    } else {
      badge.className = "status-pill connecting";
      if (text) text.textContent = live?.fetching ? "Updating…" : "Connecting…";
    }
  }

  function unusualTagsHtml(tags) {
    if (!tags?.length) return '<span class="muted">—</span>';
    return tags.map((t) => `<span class="tag tag-${t}">${t.replace(/_/g, " ")}</span>`).join("");
  }

  function triggerFlash(el, dir, upClass, downClass) {
    if (!el) return;
    el.classList.remove(upClass, downClass, "flash-tick", "flash-tick-up", "flash-tick-down");
    void el.offsetWidth;
    if (dir > 0) el.classList.add(upClass, "flash-tick", "flash-tick-up");
    else if (dir < 0) el.classList.add(downClass, "flash-tick", "flash-tick-down");
    else el.classList.add("flash-tick");
    window.setTimeout(() => {
      el.classList.remove("flash-tick", "flash-tick-up", "flash-tick-down");
    }, 550);
  }

  function ourbitBadgeHtml(r) {
    if (!r?.on_ourbit) return "";
    const pair = r.ourbit_symbol ? ` (${r.ourbit_symbol})` : "";
    return `<span class="ourbit-badge" title="Listed on Ourbit${esc(pair)}">OB</span>`;
  }

  function minimalOurbitRow(ticker, info) {
    return {
      symbol: ticker,
      price: 0,
      change_pct: 0,
      volume_ratio: 0,
      rsi: 50,
      score: 0,
      edge_score: 0,
      edge_grade: "—",
      signals: [],
      unusual_activity: [],
      unusual_score: 0,
      thesis: "Ourbit-listed — refresh scan for full metrics",
      news: [],
      chart_links: defaultChartLinks(ticker),
      on_ourbit: true,
      ourbit_symbol: info.ourbit_symbol || "",
    };
  }

  /** Ensure Ourbit tab + OB badges even if server cache predates ourbit_payload (e.g. Render v3.1). */
  async function enrichOurbitPayload(payload) {
    if (!payload) return payload;
    const existing = (payload.ourbit_stocks || []).length;
    if (existing >= 20 && (payload.stats?.ourbit_count || 0) >= 20) return payload;

    let stocks = [];
    const sources = [
      "/api/ourbit-stocks",
      "/static/ourbit_stocks.json",
    ];
    for (const url of sources) {
      try {
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) continue;
        const raw = await res.json();
        stocks = raw.stocks || raw.tickers?.map((t) => ({ ticker: t })) || [];
        if (stocks.length) break;
      } catch (_) { /* try next source */ }
    }
    if (!stocks.length) return payload;

    const lookup = {};
    stocks.forEach((s) => {
      const t = (s.ticker || s).toUpperCase();
      if (t) lookup[t] = s;
    });

    const bySym = {};
    (payload.all_stocks || []).forEach((r) => {
      const sym = (r.symbol || "").toUpperCase();
      if (sym) bySym[sym] = r;
    });

    const ourbitStocks = Object.keys(lookup)
      .sort()
      .map((sym) => {
        const info = lookup[sym];
        const base = bySym[sym] ? { ...bySym[sym] } : minimalOurbitRow(sym, info);
        base.on_ourbit = true;
        base.ourbit_symbol = info.ourbit_symbol || "";
        return base;
      });

    const taggedAll = (payload.all_stocks || []).map((r) => {
      const info = lookup[(r.symbol || "").toUpperCase()];
      if (!info) return r;
      return {
        ...r,
        on_ourbit: true,
        ourbit_symbol: info.ourbit_symbol || r.ourbit_symbol || "",
      };
    });

    const lists = [
      "opportunities", "gainers", "losers", "edge_plays",
      "high_rvol", "rel_strength", "unusual_activity",
    ];
    const out = { ...payload, all_stocks: taggedAll, ourbit_stocks: ourbitStocks };
    out.ourbit_listed = stocks.length;
    out.stats = { ...(out.stats || {}), ourbit_count: ourbitStocks.length };
    lists.forEach((key) => {
      if (!Array.isArray(out[key])) return;
      out[key] = out[key].map((r) => {
        const info = lookup[(r.symbol || "").toUpperCase()];
        if (!info) return r;
        return {
          ...r,
          on_ourbit: true,
          ourbit_symbol: info.ourbit_symbol || r.ourbit_symbol || "",
        };
      });
    });
    return out;
  }

  function buildTapeFromData() {
    const stocks = data?.all_stocks || [];
    if (!stocks.length) return [];

    const gainers = stocks
      .filter((s) => Number(s.change_pct) > 0)
      .sort((a, b) => Number(b.change_pct) - Number(a.change_pct))
      .slice(0, TAPE_TOP_N)
      .map((r) => ({
        symbol: r.symbol,
        label: r.symbol,
        price: r.price,
        change_pct: r.change_pct,
        role: "gainer",
        on_ourbit: r.on_ourbit,
        ourbit_symbol: r.ourbit_symbol,
      }));

    const losers = stocks
      .filter((s) => Number(s.change_pct) < 0)
      .sort((a, b) => Number(a.change_pct) - Number(b.change_pct))
      .slice(0, TAPE_TOP_N)
      .map((r) => ({
        symbol: r.symbol,
        label: r.symbol,
        price: r.price,
        change_pct: r.change_pct,
        role: "loser",
        on_ourbit: r.on_ourbit,
        ourbit_symbol: r.ourbit_symbol,
      }));

    return [...gainers, ...losers];
  }

  function tapeRankingSignature(items) {
    return items.map((m) => `${m.symbol}:${m.change_pct?.toFixed(2)}`).join("|");
  }

  function tapeItemHtml(m) {
    const sym = m.symbol || m.label || "—";
    const up = Number(m.change_pct) >= 0;
    const role = m.role || (up ? "gainer" : "loser");
    const roleText = role === "gainer" ? "TOP GAINER" : "TOP LOSER";
    return `<div class="tape-item tape-${role}" data-tape-symbol="${esc(sym)}">
      <span class="tape-ticker">${esc(sym)}${ourbitBadgeHtml(m)}</span>
      <span class="tape-role">${roleText}</span>
      <span class="tape-price live-tape-price">$${fmtPrice(m.price)}</span>
      <span class="tape-chg live-tape-chg ${up ? "up" : "down"}">${up ? "+" : ""}${Number(m.change_pct).toFixed(2)}%</span>
    </div>`;
  }

  function renderMarketTape(pulse) {
    const track = $("tape-track");
    if (!track) return;
    const items = (pulse && pulse.length ? pulse : buildTapeFromData()) || [];
    if (!items.length) {
      if (!tapeBuilt) {
        track.classList.remove("tape-ready");
        track.innerHTML = '<span class="muted tape-loading">Loading top gainers &amp; losers…</span>';
      }
      return;
    }

    const sig = tapeRankingSignature(items);
    if (sig === tapeSignature && tapeBuilt) {
      if (data) data.market_pulse = items;
      return;
    }

    tapeSignature = sig;
    tapeBuilt = true;
    const segment = items.map(tapeItemHtml).join("");
    track.classList.remove("tape-ready");
    void track.offsetWidth;
    track.innerHTML =
      `<div class="tape-segment">${segment}</div>`
      + `<div class="tape-segment" aria-hidden="true">${segment}</div>`;
    requestAnimationFrame(() => {
      track.classList.add("tape-ready");
    });
    if (data) data.market_pulse = items;
  }

  function patchLiveTableRows(quotes) {
    if (!quotes || activeTab === "news") return;
    document.querySelectorAll("#tbody tr[data-symbol]").forEach((tr) => {
      const sym = tr.dataset.symbol;
      const q = quotes[sym];
      if (!q) return;

      const priceEl = tr.querySelector(".live-price");
      const chgEl = tr.querySelector(".live-chg");
      const volEl = tr.querySelector(".live-vol");

      const prevP = prevPrices[sym];
      const prevC = prevChanges[sym];

      if (priceEl) {
        if (prevP != null && q.price !== prevP) {
          triggerFlash(priceEl, q.price - prevP, "flash-tick-up", "flash-tick-down");
        }
        priceEl.textContent = `$${fmtPrice(q.price)}`;
      }
      if (chgEl) {
        const up = q.change_pct >= 0;
        chgEl.className = `chg-pill live-chg ${up ? "up" : "down"}`;
        chgEl.textContent = `${up ? "+" : ""}${Number(q.change_pct).toFixed(2)}%`;
        if (prevC != null && q.change_pct !== prevC) {
          triggerFlash(chgEl, q.change_pct - prevC, "flash-tick-up", "flash-tick-down");
        }
      }
      if (volEl && q.volume_ratio != null) {
        volEl.textContent = `${Number(q.volume_ratio).toFixed(1)}×`;
      }

      prevPrices[sym] = q.price;
      prevChanges[sym] = q.change_pct;
      tr.classList.add("row-live");
    });
  }

  function renderAlerts() {
    const list = $("alerts-list");
    const feed = $("alert-feed");
    const alerts = data?.alerts?.alerts || [];
    const triggered = data?.alert_feed || [];

    if (list) {
      if (!alerts.length) {
        list.innerHTML = '<span class="muted">No alerts — add one above</span>';
      } else {
        list.innerHTML = alerts.map((a) => `
          <div class="alert-row">
            <span><strong>${esc(a.symbol)}</strong> ${esc(a.alert_type.replace(/_/g, " "))} ${a.value}${a.triggered_at ? " ✓" : ""}</span>
            <button type="button" data-del="${esc(a.id)}" title="Delete">×</button>
          </div>`).join("");
        list.querySelectorAll("[data-del]").forEach((btn) => {
          btn.onclick = () => deleteAlert(btn.dataset.del);
        });
      }
    }

    if (feed) {
      feed.innerHTML = triggered.length
        ? triggered.slice(0, 8).map((t) => `
            <div class="alert-triggered">
              <strong>${esc(t.symbol)}</strong> triggered — ${esc(t.alert_type.replace(/_/g, " "))}
              ${t.triggered_value != null ? ` @ ${t.triggered_value}` : ""}
            </div>`).join("")
        : "";
    }
  }

  async function deleteAlert(id) {
    try {
      await fetch(`/api/alerts/${id}`, { method: "DELETE" });
      await loadAlertsOnly();
    } catch (_) {}
  }

  async function loadAlertsOnly() {
    try {
      const res = await fetch("/api/alerts");
      const json = await res.json();
      if (json.ok) {
        if (!data) data = {};
        data.alerts = { alerts: json.alerts };
        data.alert_feed = json.feed || [];
        renderAlerts();
      }
    } catch (_) {}
  }

  function renderRail() {
    const plays = data?.edge_plays || [];
    const pb = $("edge-playbook");
    if (pb) {
      pb.innerHTML = plays.length
        ? plays.map((r) => `
          <div class="playbook-card">
            <div class="playbook-head">
              <span class="playbook-sym">${esc(r.symbol)}</span>
              <span class="edge-grade ${gradeClass(r.edge_grade)}">${esc(r.edge_grade)}</span>
            </div>
            <div class="playbook-edge">Edge ${r.edge_score} · Unusual ${r.unusual_score ?? 0}</div>
            <p class="playbook-thesis">${esc((r.thesis || "").slice(0, 120))}…</p>
          </div>`).join("")
        : '<span class="muted">Waiting for scan…</span>';
    }

    renderNewsWire();

    renderAlerts();
  }

  function applyLive(live) {
    if (!live?.quotes) return;
    const quotes = live.quotes;
    const patch = (row) => {
      const q = quotes[row.symbol];
      if (!q) return row;
      return { ...row, price: q.price, change_pct: q.change_pct, volume_ratio: q.volume_ratio, live: true };
    };

    if (!data) data = { opportunities: [], all_stocks: [], unusual_activity: [] };

    data.live = live;
    for (const key of DATA_LIST_KEYS) {
      if (Array.isArray(data[key])) data[key] = data[key].map(patch);
    }

    updateLiveBadge(live);
    updateMeta();
    updateNavCounts();
    patchLiveTableRows(live.quotes);
  }

  function startMarketPolling() {
    if (window._marketPollTimer) clearInterval(window._marketPollTimer);
    const poll = async () => {
      try {
        const res = await fetch("/api/market");
        const json = await res.json();
        if (json.ok) renderMarketTape(json.pulse);
      } catch (_) {}
    };
    poll();
    window._marketPollTimer = setInterval(poll, MARKET_POLL_MS);
  }

  function startLivePolling() {
    if (window._livePollTimer) clearInterval(window._livePollTimer);
    const poll = async () => {
      try {
        const res = await fetch("/api/live");
        const json = await res.json();
        if (json && (json.quotes || json.count !== undefined)) applyLive(json);
      } catch (_) { /* server may still be starting */ }
    };
    poll();
    window._livePollTimer = setInterval(poll, LIVE_POLL_MS);
    startMarketPolling();
  }

  function renderFilters() {
    const el = $("signal-filters");
    if (!el) return;
    el.innerHTML = SIGNALS.map((s) =>
      `<button type="button" class="chip" data-signal="${s}">${s.replace(/_/g, " ")}</button>`
    ).join("");
    el.querySelectorAll(".chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        const sig = btn.dataset.signal;
        if (activeSignals.has(sig)) activeSignals.delete(sig);
        else activeSignals.add(sig);
        btn.classList.toggle("active", activeSignals.has(sig));
        $("btn-clear-filters").hidden = activeSignals.size === 0;
        renderTable();
      });
    });
  }

  function tagHtml(signals) {
    return (signals || []).map((s) =>
      `<span class="tag tag-${s}">${s.replace(/_/g, " ")}</span>`
    ).join("") || '<span class="muted">—</span>';
  }

  function chartLinksHtml(links, symbol) {
    const L = links || defaultChartLinks(symbol);
    return [["TV", L.tradingview], ["Yahoo", L.yahoo], ["Finviz", L.finviz], ["News", L.yahoo_news]]
      .filter(([, u]) => u)
      .map(([l, u]) => `<a class="chart-link" href="${u}" target="_blank" rel="noopener">${l}</a>`)
      .join("");
  }

  function newsHtml(news) {
    if (!news?.length) return '<span class="muted">—</span>';
    return news.slice(0, 2).map((n) => {
      const href = (n.url || "#").replace(/"/g, "%22");
      return `<a href="${href}" target="_blank" class="news-title">${esc(n.title)}</a>`;
    }).join("");
  }

  function wireItemHtml(n) {
    const href = (n.url || "#").replace(/"/g, "%22");
    const sent = n.sentiment || "neutral";
    const summary = n.summary
      ? `<p class="wire-summary">${esc(n.summary)}</p>`
      : "";
    return `<div class="wire-item wire-${sent}">
      <div class="wire-head">
        <span class="wire-sym">${esc(n.symbol)}</span>
        <span class="wire-sent wire-sent-${sent}">${esc(sent)}</span>
        <span class="wire-time">${esc(n.published || "")}</span>
      </div>
      <a href="${href}" target="_blank" rel="noopener" class="wire-title">${esc(n.title)}</a>
      ${summary}
      <div class="wire-meta">${esc(n.publisher || "News")}</div>
    </div>`;
  }

  function collectNewsWire() {
    if (data?.news_wire?.length) return data.news_wire;
    const items = [];
    for (const r of data?.all_stocks || []) {
      for (const n of r.news || []) items.push({ symbol: r.symbol, ...n });
    }
    items.sort((a, b) => (b.published_ts || 0) - (a.published_ts || 0));
    return items;
  }

  function renderNewsWire() {
    const wire = $("news-wire");
    if (!wire) return;
    const items = collectNewsWire();
    const count = $("news-wire-count");
    if (count) count.textContent = items.length ? `${items.length} articles` : "";
    wire.innerHTML = items.length
      ? items.map(wireItemHtml).join("")
      : '<span class="muted">Latest headlines load after scan completes — click Refresh scan</span>';
  }

  function rowHtml(r) {
    const sym = r.symbol;
    const chgUp = r.change_pct >= 0;
    const hot = (r.unusual_score >= 50) || r.edge_score >= 65;
    const gap = r.gap_pct != null ? `${r.gap_pct >= 0 ? "+" : ""}${r.gap_pct.toFixed(1)}%` : "—";
    const rs = r.vs_spy_5d != null ? `${r.vs_spy_5d >= 0 ? "+" : ""}${r.vs_spy_5d.toFixed(1)}%` : "—";

    return `<tr data-symbol="${esc(sym)}" class="${hot ? "row-hot" : ""}">
      <td class="col-symbol">
        <div class="sym-cell-inner">
          <div class="sym-row">
            <span class="sym-ticker">${esc(sym)}</span>
            ${ourbitBadgeHtml(r)}
            ${r.live ? '<span class="live-indicator"></span>' : ""}
          </div>
          <div class="chart-links">${chartLinksHtml(r.chart_links, sym)}</div>
        </div>
      </td>
      <td class="col-num"><span class="unusual-score">${r.unusual_score ?? 0}</span></td>
      <td class="col-num"><span class="mono live-price">$${fmtPrice(r.price)}</span></td>
      <td class="col-num"><span class="chg-pill live-chg ${chgUp ? "up" : "down"}">${chgUp ? "+" : ""}${r.change_pct.toFixed(2)}%</span></td>
      <td class="col-num"><span class="mono live-vol">${r.volume_ratio.toFixed(1)}×</span></td>
      <td class="col-signals">${unusualTagsHtml(r.unusual_activity)}</td>
      <td class="col-num"><span class="edge-meter">${r.edge_score ?? 0}</span></td>
      <td class="col-num"><span class="mono">${gap}</span></td>
      <td class="col-num"><span class="mono">${rs}</span></td>
      <td class="col-signals">${tagHtml(r.signals)}</td>
      <td class="col-thesis">${esc((r.thesis || "").slice(0, 100))}${(r.thesis || "").length > 100 ? "…" : ""}</td>
      <td class="col-news">${newsHtml(r.news)}</td>
    </tr>`;
  }

  function getRows() {
    if (!data) return [];
    let rows;
    switch (activeTab) {
      case "gainers": rows = [...(data.gainers || [])]; break;
      case "losers": rows = [...(data.losers || [])]; break;
      case "all": rows = [...(data.all_stocks || [])]; break;
      case "ourbit":
        rows = [...(data.ourbit_stocks || [])];
        if (!rows.length) {
          rows = (data.all_stocks || []).filter((r) => r.on_ourbit);
        }
        break;
      case "opportunities":
      default: rows = [...(data.opportunities || [])]; break;
    }

    const q = $("search")?.value.trim().toUpperCase();
    if (q) rows = rows.filter((r) => r.symbol.includes(q));
    if (activeSignals.size) {
      rows = rows.filter((r) => (r.signals || []).some((s) => activeSignals.has(s)));
    }

    rows.sort((a, b) => {
      const av = a[sortKey] ?? 0;
      const bv = b[sortKey] ?? 0;
      if (typeof av === "string") return sortDir * av.localeCompare(bv);
      return sortDir * (av - bv);
    });
    return rows;
  }

  function setTableHeader() {
    const thead = $("table-head");
    if (!thead) return;
    if (activeTab === "news") {
      thead.innerHTML = `<th>Time</th><th>Symbol</th><th>Headline</th><th>Publisher</th><th>Sentiment</th>`;
      return;
    }
    const cols = [
      ["symbol", "Symbol", "col-symbol"],
      ["unusual_score", "Unusual", "col-num"],
      ["price", "Price", "col-num"],
      ["change_pct", "Chg", "col-num"],
      ["volume_ratio", "Vol", "col-num"],
    ];
    thead.innerHTML = cols.map(([key, label, cls]) => {
      const sorted = sortKey === key ? " sorted" : "";
      const icon = sortKey === key ? (sortDir > 0 ? "↑" : "↓") : "↕";
      return `<th data-sort="${key}" class="${cls}${sorted}">${label}<span class="sort-icon">${icon}</span></th>`;
    }).join("")
      + `<th class="col-signals">Flow flags</th>`
      + `<th data-sort="edge_score" class="col-num${sortKey === "edge_score" ? " sorted" : ""}">Edge<span class="sort-icon">↕</span></th>`
      + `<th data-sort="gap_pct" class="col-num">Gap</th>`
      + `<th data-sort="vs_spy_5d" class="col-num">vs SPY</th>`
      + `<th class="col-signals">Setups</th>`
      + `<th class="col-thesis">Thesis</th>`
      + `<th class="col-news">News</th>`;
    bindSortHeaders();
  }

  function bindSortHeaders() {
    document.querySelectorAll("th[data-sort]").forEach((th) => {
      th.onclick = () => {
        const key = th.dataset.sort;
        if (sortKey === key) sortDir *= -1;
        else { sortKey = key; sortDir = key === "symbol" ? 1 : -1; }
        setTableHeader();
        renderTable();
      };
    });
  }

  function renderTable() {
    $("page-title").textContent = TAB_TITLES[activeTab] || "StocksTunerStation";
    $("toolbar-filters").style.display = activeTab === "news" ? "none" : "flex";
    setTableHeader();

    const tbody = $("tbody");
    if (activeTab === "news") {
      const items = collectNewsWire();
      $("row-count").textContent = items.length ? `${items.length} articles` : "";
      if (!items.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="state-cell"><div class="state-box"><p>No headlines yet — run Refresh scan</p></div></td></tr>`;
        return;
      }
      const q = $("search")?.value.trim().toUpperCase();
      const filtered = q
        ? items.filter((n) => n.symbol.includes(q) || (n.title || "").toUpperCase().includes(q))
        : items;
      tbody.innerHTML = filtered.map((n) => {
        const href = (n.url || "#").replace(/"/g, "%22");
        const sent = n.sentiment || "neutral";
        return `<tr>
          <td class="mono" style="font-size:0.8rem">${esc(n.published || "—")}</td>
          <td><span class="sym-ticker">${esc(n.symbol)}</span></td>
          <td class="col-news-wire">
            <a href="${href}" target="_blank" rel="noopener" class="news-title">${esc(n.title)}</a>
            ${n.summary ? `<div class="wire-summary-inline">${esc(n.summary.slice(0, 180))}${n.summary.length > 180 ? "…" : ""}</div>` : ""}
          </td>
          <td class="muted">${esc(n.publisher || "")}</td>
          <td><span class="wire-sent wire-sent-${sent}">${esc(sent)}</span></td>
        </tr>`;
      }).join("");
      return;
    }

    const rows = getRows();
    $("row-count").textContent = rows.length ? `${rows.length} rows` : "";

    if (!rows.length) {
      tbody.innerHTML = `<tr><td colspan="${COLS}" class="state-cell"><div class="state-box"><p>No matches — try Refresh scan</p></div></td></tr>`;
      return;
    }

    const snapP = { ...prevPrices };
    const snapC = { ...prevChanges };
    tbody.innerHTML = rows.map(rowHtml).join("");
    prevPrices = snapP;
    prevChanges = snapC;
    if (data?.live?.quotes) patchLiveTableRows(data.live.quotes);
  }

  function updateMeta() {
    if (!$("meta") || !data) return;
    const live = data.live || {};
    let t = data.scanned_at ? `Scan ${data.scanned_at}` : "Scan running…";
    if (data.scanning) t += " · updating";
    if (live.updated_at) t += ` · Live ${live.updated_at}`;
    const ob = data.ourbit_listed ?? data.stats?.ourbit_count ?? (data.ourbit_stocks || []).length;
    if (ob) t += ` · ${ob} Ourbit stocks`;
    $("meta").textContent = t;
    updateStatusBanner();
  }

  function updateNavCounts() {
    if ($("count-opps")) $("count-opps").textContent = data?.opportunities?.length ?? 0;
    if ($("count-all")) $("count-all").textContent = data?.all_stocks?.length ?? "—";
    if ($("count-ourbit")) {
      const n = (data?.ourbit_stocks || []).length
        || data?.stats?.ourbit_count
        || (data?.all_stocks || []).filter((r) => r.on_ourbit).length;
      $("count-ourbit").textContent = n || "—";
    }
  }

  function updateStats() {
    if (!data) return;
    const s = data.stats || {};
    $("stat-edge-ap").textContent = s.edge_a_plus ?? "—";
    $("stat-opps").textContent = s.total_opportunities ?? 0;
    $("stat-scanned").textContent = data.symbols_scanned ?? "—";
    $("stat-gaps").textContent = s.gaps_today ?? "—";
    $("stat-earn").textContent = s.earnings_soon ?? "—";
    $("stat-unusual").textContent = s.unusual_active ?? data?.unusual_activity?.length ?? "—";
    if ($("stat-ourbit")) {
      $("stat-ourbit").textContent = data?.ourbit_listed ?? s.ourbit_count ?? (data?.ourbit_stocks || []).length ?? "—";
    }
    updateNavCounts();
    updateMeta();
    renderMarketTape();
    renderRail();
    renderTable();
  }

  async function onDataLoaded(json) {
    if (!json) return;
    const incoming = (json.all_stocks || []).length;
    const existing = (data?.all_stocks || []).length;
    if (!incoming && !json.opportunities?.length && existing > 0) {
      if (json.scanning) data.scanning = true;
      updateStatusBanner();
      return;
    }
    const live = data?.live;
    data = await enrichOurbitPayload(json);
    if (live && !data.live) data.live = live;
    if (data.market_pulse?.length) renderMarketTape(data.market_pulse);
    updateStats();
    if (data.message && $("meta")) {
      $("meta").textContent = data.message + (data.scanned_at ? ` · Scan ${data.scanned_at}` : "");
    }
    if (data.scanning || !data.scanned_at) scheduleScanPoll();
    const ob = (data.ourbit_stocks || []).length;
    if (ob < 1) {
      const banner = $("status-banner");
      if (banner) {
        banner.hidden = false;
        banner.className = "status-banner warn";
        banner.textContent =
          "Ourbit list not loaded — push the latest code to GitHub and redeploy on Render (health should show version 3.4+ and ourbit_listed: 33).";
      }
    }
  }

  function showServerError(message) {
    const banner = $("status-banner");
    if (banner) {
      banner.hidden = false;
      banner.className = "status-banner error";
      banner.textContent = message;
    }
    if ($("meta")) $("meta").textContent = message;
    const tbody = $("table-body");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="${COLS}" class="empty">${esc(message)}</td></tr>`;
    }
  }

  async function loadStaticSeedFallback() {
    try {
      const res = await fetch("/static/seed_bootstrap.json", { cache: "no-store" });
      if (!res.ok) return null;
      const json = await res.json();
      if (json?.all_stocks?.length || json?.opportunities?.length) return json;
    } catch (_) { /* ignore */ }
    return null;
  }

  async function fetchJsonWithFallback(primary, fallback) {
    try {
      const res = await fetch(primary, { cache: "no-store" });
      if (res.ok) {
        const json = await res.json();
        if (json?.all_stocks?.length || json?.opportunities?.length) return json;
      } else if (res.status !== 404) {
        throw new Error(`Server returned ${res.status}`);
      }
    } catch (e) {
      if (!fallback) throw e;
    }
    if (fallback) {
      try {
        const res2 = await fetch(fallback, { cache: "no-store" });
        if (res2.ok) {
          const json = await res2.json();
          if (json?.all_stocks?.length || json?.opportunities?.length) return json;
        }
      } catch (_) { /* try static */ }
    }
    const seed = await loadStaticSeedFallback();
    if (seed) return seed;
    if (primary === "/api/bootstrap") {
      throw new Error("Server returned no stock data yet");
    }
    throw new Error(
      "API not found — an old dashboard is still running. Close all terminal windows, then double-click start_dashboard.bat in the stock-screener folder."
    );
  }

  async function fetchHubData() {
    const sources = [
      () => fetch("/api/bootstrap", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)),
      () => fetch("/static/seed_bootstrap.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)),
      () => fetch("/api/scan", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)),
    ];
    for (const load of sources) {
      try {
        const json = await load();
        if (json?.all_stocks?.length || json?.opportunities?.length) return json;
      } catch (_) { /* try next */ }
    }
    return null;
  }

  async function waitForServer(maxMs = 60000) {
    const seen = sessionStorage.getItem("sts-server-ok");
    const deadline = Date.now() + (seen ? 15000 : maxMs);
    while (Date.now() < deadline) {
      try {
        const res = await fetch("/api/health", { cache: "no-store" });
        if (res.ok) {
          const j = await res.json();
          if (j.ok) {
            sessionStorage.setItem("sts-server-ok", String(Date.now()));
            return true;
          }
        }
      } catch (_) {}
      const banner = $("status-banner");
      if (banner) {
        banner.hidden = false;
        banner.className = "status-banner scanning";
        banner.textContent = "Waking up server on Render… first load can take 30–60 seconds.";
      }
      await new Promise((r) => setTimeout(r, 2500));
    }
    return false;
  }

  async function loadBootstrap() {
    const staticPromise = fetch("/static/seed_bootstrap.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);

    const up = await waitForServer();
    if (!up) {
      const seed = await staticPromise;
      if (seed?.all_stocks?.length) {
        await onDataLoaded(seed);
        return true;
      }
      showServerError("Server not responding. On Render free tier, open the site once and wait ~1 minute, then refresh.");
      return false;
    }

    for (let attempt = 0; attempt < 6; attempt++) {
      try {
        const json = await Promise.race([
          fetchHubData(),
          staticPromise,
        ]);
        if (json?.all_stocks?.length || json?.opportunities?.length) {
          await onDataLoaded(json);
          return true;
        }
        if (json?.message && $("meta")) $("meta").textContent = json.message;
      } catch (e) {
        if (attempt === 5) {
          const seed = await staticPromise;
          if (seed?.all_stocks?.length) {
            await onDataLoaded(seed);
            return true;
          }
          showServerError(`Cannot load data: ${e.message}`);
          return false;
        }
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
    const seed = await staticPromise;
    if (seed?.all_stocks?.length) {
      await onDataLoaded(seed);
      return true;
    }
    showServerError("No stock data yet. Click Refresh scan or wait for the background scan to finish.");
    return false;
  }

  function scheduleScanPoll() {
    if (scanPollTimer) clearTimeout(scanPollTimer);
    scanPollTimer = setTimeout(async () => {
      try {
        const res = await fetch("/api/scan");
        const json = await res.json();
        if (json.ok !== false) await onDataLoaded(json);
      } catch (_) {}
    }, 5000);
  }

  async function loadScan(refresh = false) {
    const btn = $("btn-refresh");
    const lbl = btn?.querySelector(".btn-label");
    if (btn) btn.disabled = true;
    if (lbl) lbl.textContent = refresh ? "Refreshing…" : "Loading…";

    if (refresh && data?.all_stocks?.length) {
      data.scanning = true;
      updateStatusBanner();
    }

    try {
      const res = await fetch(`/api/scan${refresh ? "?refresh=1" : ""}`);
      const json = await res.json();
      await onDataLoaded(json);
    } catch (e) {
      const banner = $("status-banner");
      if (banner) {
        banner.hidden = false;
        banner.className = "status-banner error";
        banner.textContent = `Network error: ${e.message}. Is the server running?`;
      }
    } finally {
      if (btn) btn.disabled = false;
      if (lbl) lbl.textContent = "Refresh scan";
    }
  }

  $("alert-form")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const symbol = $("alert-symbol")?.value?.trim();
    const alert_type = $("alert-type")?.value;
    const value = parseFloat($("alert-value")?.value);
    if (!symbol || Number.isNaN(value)) return;
    try {
      const res = await fetch("/api/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, alert_type, value }),
      });
      const json = await res.json();
      if (json.ok) {
        $("alert-symbol").value = "";
        $("alert-value").value = "";
        await loadAlertsOnly();
        const res2 = await fetch("/api/scan");
        await onDataLoaded(await res2.json());
      }
    } catch (_) {}
  });

  document.querySelectorAll(".nav-item[data-tab]").forEach((item) => {
    item.addEventListener("click", () => {
      document.querySelectorAll(".nav-item[data-tab]").forEach((n) => n.classList.remove("active"));
      item.classList.add("active");
      activeTab = item.dataset.tab;
      sortKey = activeTab === "gainers" || activeTab === "losers" ? "change_pct"
        : activeTab === "all" || activeTab === "ourbit" ? "symbol"
        : "score";
      sortDir = activeTab === "ourbit" ? 1 : -1;
      renderTable();
    });
  });

  $("btn-clear-filters")?.addEventListener("click", () => {
    activeSignals.clear();
    document.querySelectorAll(".chip.active").forEach((c) => c.classList.remove("active"));
    $("btn-clear-filters").hidden = true;
    renderTable();
  });

  $("search")?.addEventListener("input", renderTable);
  $("btn-refresh")?.addEventListener("click", () => loadScan(true));

  renderFilters();
  setTableHeader();
  startLivePolling();
  loadBootstrap().then((loaded) => {
    if (!loaded) loadScan(false);
  });
})();
