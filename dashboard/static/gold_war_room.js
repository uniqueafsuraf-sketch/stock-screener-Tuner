(() => {
  const $ = (id) => document.getElementById(id);

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s ?? "";
    return d.innerHTML;
  }

  function biasClass(bias) {
    const b = (bias || "").toLowerCase();
    if (b.includes("bull")) return "bull";
    if (b.includes("bear")) return "bear";
    return "neutral";
  }

  function renderAlerts(alerts) {
    const el = $("war-alerts");
    if (!el) return;
    if (!alerts?.length) {
      el.hidden = true;
      return;
    }
    el.hidden = false;
    el.innerHTML = alerts.map((a) =>
      `<span class="war-alert-chip">${esc(a.message)} ${Math.round(a.value)}%</span>`
    ).join("");
  }

  function renderConsensus(c) {
    $("consensus-headline").textContent = c?.headline || "";
    const rows = c?.rows || [];
    $("consensus-table").innerHTML = rows.map((r) => {
      const cls = r.view.toLowerCase().includes("bull") ? "bullish"
        : r.view.toLowerCase().includes("bear") ? "bearish"
        : r.view.toLowerCase().includes("warn") || r.view.toLowerCase().includes("risky") ? "warning"
        : "";
      return `<div class="consensus-row">
        <span>${esc(r.agent)}</span>
        <span class="consensus-view ${cls}">${esc(r.view)}</span>
        <span class="war-muted">${esc(r.detail)}</span>
      </div>`;
    }).join("");
  }

  function renderSmartMoney(sm) {
    $("smart-money-title").textContent = sm?.title || "Smart Money Intent";
    const list = sm?.ranked || [];
    $("smart-money-list").innerHTML = list.map((item) =>
      `<li>
        <span></span>
        <div>
          <strong>${esc(item.label)}</strong>
          <p class="war-muted">${esc(item.why)}</p>
        </div>
        <span class="intent-prob">${Math.round(item.probability)}%</span>
      </li>`
    ).join("") || "<li class='war-muted'>No ranked intents</li>";
  }

  function renderDetail(elId, obj, template) {
    const el = $(elId);
    if (!el || !obj) return;
    el.innerHTML = template(obj);
  }

  function renderTrade(t) {
    const el = $("trade-content");
    if (!el) return;
    if (t?.status !== "HIGH_CONVICTION") {
      el.className = "trade-box no-trade";
      el.innerHTML = `<p>NO HIGH-CONVICTION TRADE</p><p class="war-why">${esc(t?.why || "")}</p>`;
      return;
    }
    el.className = "trade-box has-trade";
    const fields = [
      ["Direction", t.direction],
      ["Entry zone", t.entry_zone],
      ["Stop loss", t.stop_loss],
      ["Target 1", t.target_1],
      ["Target 2", t.target_2],
      ["Target 3", t.target_3],
      ["Risk / Reward", t.risk_reward ? `${t.risk_reward}:1` : "—"],
      ["Invalidation", t.invalidation],
    ];
    el.innerHTML = fields.map(([label, val]) =>
      `<div class="trade-field"><label>${esc(label)}</label><span>${esc(String(val ?? "—"))}</span></div>`
    ).join("") + `<p class="war-why" style="grid-column:1/-1;margin-top:0.75rem">${esc(t.why || "")}</p>`;
  }

  function renderAgents(agents) {
    const order = ["macro", "technical", "order_flow", "sentiment", "quant", "risk", "trap"];
    const el = $("agent-cards");
    if (!el) return;
    el.innerHTML = order.map((key) => {
      const a = agents[key];
      if (!a) return "";
      let scores = "";
      if (a.bullish_score != null) {
        scores = `<div class="agent-scores"><span>Bull ${a.bullish_score}</span><span>Bear ${a.bearish_score}</span></div>`;
      } else if (a.bull_probability != null) {
        scores = `<div class="agent-scores"><span>Bull ${a.bull_probability}%</span><span>Bear ${a.bear_probability}%</span></div>`;
      } else if (a.risk_score != null) {
        scores = `<div class="agent-scores"><span>Risk ${a.risk_score}</span></div>`;
      } else if (a.manipulation_risk_score != null) {
        scores = `<div class="agent-scores"><span>Manip ${a.manipulation_risk_score}%</span></div>`;
      }
      const warns = (a.warnings || []).map((w) => `<li>${esc(w)}</li>`).join("");
      return `<article class="agent-card">
        <h3>${esc(a.name)}</h3>
        ${scores}
        <p class="war-why">${esc(a.summary || "")}</p>
        ${warns ? `<ul class="war-muted">${warns}</ul>` : ""}
      </article>`;
    }).join("");
  }

  let tvWidget = null;
  let tvInterval = "60";

  function initTradingViewChart(symbol = "OANDA:XAUUSD", interval = "60") {
    const el = $("gold-tv-chart");
    if (!el || typeof TradingView === "undefined") return false;
    tvInterval = interval;
    el.innerHTML = "";
    tvWidget = new TradingView.widget({
      autosize: true,
      symbol,
      interval,
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale: "en",
      enable_publishing: false,
      hide_top_toolbar: false,
      hide_legend: false,
      save_image: false,
      container_id: "gold-tv-chart",
      studies: ["Volume@tv-basicstudies"],
      backgroundColor: "#0d1117",
      gridColor: "rgba(255, 215, 0, 0.08)",
    });
    return true;
  }

  function waitForTradingView(symbol, interval, tries = 0) {
    if (initTradingViewChart(symbol, interval)) return;
    if (tries < 25) setTimeout(() => waitForTradingView(symbol, interval, tries + 1), 400);
  }

  function drawCanvasChart(chart) {
    const canvas = $("gold-canvas-chart");
    if (!canvas || !chart?.candles?.length) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth || 800;
    const h = 140;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const candles = chart.candles;
    const closes = candles.map((c) => c.c);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const pad = (max - min) * 0.08 || 1;
    const lo = min - pad;
    const hi = max + pad;
    const range = hi - lo || 1;

    ctx.strokeStyle = "rgba(255, 215, 0, 0.15)";
    for (let i = 0; i <= 4; i++) {
      const y = (h * i) / 4;
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }

    ctx.beginPath();
    ctx.strokeStyle = "#ffd700";
    ctx.lineWidth = 2;
    candles.forEach((c, i) => {
      const x = (i / Math.max(candles.length - 1, 1)) * (w - 8) + 4;
      const y = h - ((c.c - lo) / range) * (h - 16) - 8;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();

    const last = chart.last ?? closes[closes.length - 1];
    ctx.fillStyle = "#ffd700";
    ctx.font = "600 12px JetBrains Mono, monospace";
    ctx.fillText(`$${last} · ${chart.interval || "1H"} desk series`, 8, 16);

    if (chart.support?.length) {
      const sy = h - ((chart.support[0] - lo) / range) * (h - 16) - 8;
      ctx.strokeStyle = "rgba(0, 255, 136, 0.5)";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(0, sy);
      ctx.lineTo(w, sy);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (chart.resistance?.length) {
      const ry = h - ((chart.resistance[0] - lo) / range) * (h - 16) - 8;
      ctx.strokeStyle = "rgba(255, 68, 102, 0.5)";
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(0, ry);
      ctx.lineTo(w, ry);
      ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  function renderChart(chart) {
    if (!chart) return;
    const cap = $("chart-caption");
    if (cap) {
      cap.textContent = `TradingView live · ${chart.tv_symbol || "OANDA:XAUUSD"} · desk ${chart.interval || "1H"} overlay`;
    }
    const links = $("chart-ext-links");
    if (links && chart.chart_links) {
      const L = chart.chart_links;
      links.innerHTML = [
        ["TradingView", L.tradingview],
        ["Yahoo GC", L.yahoo],
        ["GLD", L.finviz],
      ]
        .filter(([, u]) => u)
        .map(([label, url]) =>
          `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(label)}</a>`
        )
        .join("");
    }
    drawCanvasChart(chart);
    const map = { "15M": "15", "1H": "60", "4H": "240", "1D": "D" };
    const iv = map[chart.interval] || tvInterval;
    waitForTradingView(chart.tv_symbol || "OANDA:XAUUSD", iv);
  }

  function renderNews(items) {
    const el = $("gold-news-list");
    if (!el) return;
    const list = items || [];
    if (!list.length) {
      el.innerHTML = "<li class='war-muted'>No headlines available — try Refresh.</li>";
      return;
    }
    el.innerHTML = list.map((n) => {
      const pub = n.publisher || "News";
      const when = n.published ? `<span> · ${esc(String(n.published).slice(0, 22))}</span>` : "";
      const href = n.link || "#";
      return `<li>
        <a href="${esc(href)}" target="_blank" rel="noopener">${esc(n.title)}</a>
        <div class="gold-news-meta">${esc(pub)}${when}</div>
      </li>`;
    }).join("");
  }

  function renderPerformance(p) {
    const el = $("performance-content");
    if (!el) return;
    el.innerHTML = `
      <div class="perf-stat"><div class="val">${p.total_setups ?? 0}</div><div class="lbl">Setups logged</div></div>
      <div class="perf-stat"><div class="val">${p.win_rate ?? 0}%</div><div class="lbl">Win rate</div></div>
      <div class="perf-stat"><div class="val">${p.loss_rate ?? 0}%</div><div class="lbl">Loss rate</div></div>
      <div class="perf-stat"><div class="val">${p.average_rr ?? 0}</div><div class="lbl">Avg RR</div></div>
    `;
  }

  function showStatusBanner(data) {
    let el = $("war-status-banner");
    if (!el) {
      el = document.createElement("div");
      el.id = "war-status-banner";
      el.className = "war-status-banner";
      const topbar = document.querySelector(".topbar");
      if (topbar?.parentNode) topbar.parentNode.insertBefore(el, topbar.nextSibling);
    }
    const notes = data?.fetch_notes || [];
    if (data?.data_source === "fallback" || notes.length) {
      el.hidden = false;
      el.className = "war-status-banner warn";
      el.textContent = (notes.join(" ") || "Using fallback data — Yahoo may be rate-limited. Click Refresh.") +
        (data?.error ? ` Error: ${data.error}` : "");
    } else if (data?.error) {
      el.hidden = false;
      el.className = "war-status-banner error";
      el.textContent = data.error;
    } else {
      el.hidden = true;
    }
  }

  function apply(data) {
    if (!data) {
      $("bias-why").textContent = "No response from server";
      return;
    }
    showStatusBanner(data);

    if (!data.ok && !(data.agents && Object.keys(data.agents).length)) {
      $("bias-why").textContent = data.error || "Analysis failed";
      return;
    }

    const mb = data.market_bias || {};
    const biasEl = $("bias-value");
    biasEl.textContent = mb.bias || "—";
    biasEl.className = `war-bias-value ${biasClass(mb.bias)}`;
    $("bias-why").textContent = mb.why || "";

    const cm = data.confidence_meter || {};
    $("confidence-score").textContent = `${cm.score ?? 0}%`;
    $("confidence-fill").style.width = `${Math.min(100, cm.score || 0)}%`;
    $("confidence-label").textContent = cm.label || "";

    $("war-price").textContent = data.price
      ? `$${data.price}  ${data.change_pct >= 0 ? "+" : ""}${data.change_pct}%`
      : "—";
    $("war-meta").textContent = `XAUUSD (GC) · Updated ${data.updated_at || "—"}`;

    renderConsensus(data.agent_consensus);
    renderSmartMoney(data.smart_money);
    renderAlerts(data.alerts);

    renderDetail("sweep-content", data.liquidity_sweep, (s) => `
      <p class="war-stat-big">${esc(s.direction)}</p>
      <p><strong>Target:</strong> ${esc(s.target_zone)}</p>
      <p><strong>Probability:</strong> ${Math.round(s.probability)}%</p>
      <p class="war-why">${esc(s.explanation)}</p>`);

    renderDetail("stop-hunt-content", data.stop_hunt, (s) => `
      <p class="war-stat-big">${Math.round(s.probability)}%</p>
      <p><strong>Risk level:</strong> ${esc(s.risk_level)}</p>
      <p class="war-why">${esc(s.explanation)}</p>`);

    renderDetail("fake-bo-content", data.fake_breakout, (s) => `
      <p><strong>Breakout validity:</strong> ${Math.round(s.breakout_validity_score)}</p>
      <p><strong>Fake breakout:</strong> ${Math.round(s.fake_breakout_probability)}%</p>
      <p class="war-why">${esc(s.explanation)}</p>`);

    renderDetail("reversal-content", data.reversal, (s) => `
      <p class="war-stat-big">${Math.round(s.probability)}%</p>
      <p><strong>Zone:</strong> ${esc(s.reversal_zone)}</p>
      <p><strong>Confidence:</strong> ${Math.round(s.confidence)}%</p>
      <p class="war-why">${esc(s.explanation)}</p>`);

    renderDetail("continuation-content", data.trend_continuation, (s) => `
      <p class="war-stat-big">${Math.round(s.probability)}%</p>
      <p><strong>Confidence:</strong> ${Math.round(s.confidence)}%</p>
      <p><strong>Factors:</strong> ${esc((s.supporting_factors || []).join(", "))}</p>
      <p class="war-why">${esc(s.explanation)}</p>`);

    renderTrade(data.trade_opportunity);
    renderAgents(data.agents);
    renderPerformance(data.performance);
    renderNews(data.news);
    renderChart(data.chart);
  }

  let warmPolls = 0;

  async function load(refresh = false, retries = 0) {
    const btn = $("btn-war-refresh");
    if (btn) btn.disabled = true;
    if (!refresh || warmPolls === 0) {
      $("bias-why").textContent = "Running 7 agents + master synthesis…";
      $("consensus-table").innerHTML = "<span class='war-muted'>Analyzing…</span>";
    }
    try {
      const res = await fetch(`/api/gold-war-room${refresh ? "?refresh=1" : ""}`, { cache: "no-store" });
      if (res.status === 502 || res.status === 503) {
        if (retries < 8) {
          showStatusBanner({ error: `Server ${res.status} — retrying…`, fetch_notes: [] });
          setTimeout(() => load(refresh, retries + 1), 4000);
          return;
        }
        throw new Error(`Server ${res.status}`);
      }
      if (!res.ok) throw new Error(`Server ${res.status}`);
      const json = await res.json();
      if (json.warming) {
        warmPolls += 1;
        $("bias-why").textContent = json.message || "Agents analyzing…";
        if (warmPolls < 40) {
          setTimeout(() => load(false), 3000);
        } else {
          $("bias-why").textContent = "Still loading — click Refresh.";
        }
        return;
      }
      warmPolls = 0;
      apply(json);
    } catch (e) {
      $("bias-why").textContent = `Network error: ${e.message}. Try Refresh.`;
      showStatusBanner({ error: e.message, fetch_notes: [] });
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  document.querySelectorAll(".chart-tf").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".chart-tf").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const iv = btn.getAttribute("data-interval") || "60";
      initTradingViewChart("OANDA:XAUUSD", iv);
    });
  });

  waitForTradingView("OANDA:XAUUSD", "60");

  $("btn-war-refresh")?.addEventListener("click", () => load(true));
  load(false);
  setInterval(() => load(false), 120000);
})();
