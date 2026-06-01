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

  function readBootstrap() {
    const el = document.getElementById("war-room-bootstrap");
    if (!el?.textContent?.trim()) return null;
    try {
      return JSON.parse(el.textContent);
    } catch {
      return null;
    }
  }

  function tvChartConfig(symbol, interval) {
    return {
      autosize: true,
      symbol,
      interval,
      timezone: "Etc/UTC",
      theme: "dark",
      style: "1",
      locale: "en",
      enable_publishing: false,
      allow_symbol_change: true,
      withdateranges: true,
      hide_side_toolbar: false,
      hide_top_toolbar: false,
      details: true,
      hotlist: true,
      calendar: false,
      studies: ["STD;Volume"],
      support_host: "https://www.tradingview.com",
    };
  }

  function setChartHeight(px) {
    const embed = $("gold-tv-embed");
    const wrap = $("war-chart-wrap");
    const h = Math.min(820, Math.max(360, Number(px) || 500));
    if (embed) embed.style.height = `${h}px`;
    if (wrap) wrap.style.height = `${h}px`;
    try {
      localStorage.setItem("warChartHeight", String(h));
    } catch { /* ignore */ }
  }

  function reloadTradingViewEmbed(interval, symbol) {
    const host = $("gold-tv-embed");
    if (!host) return;
    const sym = symbol || $("chart-symbol")?.value || "OANDA:XAUUSD";
    const iv = interval || document.querySelector(".chart-tf.active")?.getAttribute("data-interval") || "60";
    const cfg = tvChartConfig(sym, iv);
    host.innerHTML = "";
    const widget = document.createElement("div");
    widget.className = "tradingview-widget-container__widget";
    widget.style.height = "100%";
    widget.style.width = "100%";
    host.appendChild(widget);
    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.text = JSON.stringify(cfg);
    host.appendChild(script);
    const cap = $("chart-caption");
    if (cap) cap.textContent = `Loading ${sym} · ${iv} — chart toolbar: zoom, pan, draw`;
  }

  function renderChart(chart) {
    const links = $("chart-ext-links");
    if (links && chart?.chart_links) {
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

  function renderLiveScan(ls, updatedAt) {
    const badge = $("live-scan-badge");
    if (!badge) return;
    const sec = ls?.interval_sec || 45;
    const t = updatedAt ? ` · ${updatedAt}` : "";
    badge.innerHTML = `<span class="live-scan-dot"></span> Agents live · ${sec}s scan${t}`;
    badge.title = ls?.message || "Continuous multi-agent gold analysis";
  }

  function renderScalping(sc) {
    const sub = $("scalp-subtitle");
    const warn = $("scalp-warning");
    const el = $("scalp-content");
    if (!el) return;
    if (!sc) {
      el.innerHTML = "<p class='war-muted'>Scalp scanner loading…</p>";
      return;
    }
    if (sub) {
      sub.textContent = sc.subtitle || sc.title || "";
      if (sc.reference_price) sub.textContent += ` · chart/live ref $${sc.reference_price}`;
    }
    if (warn) warn.textContent = sc.leverage_warning || "High leverage — extreme risk.";
    const setups = sc.setups || [];
    if (!setups.length) {
      el.innerHTML = `<p class="scalp-empty">No scalp meeting criteria right now (${sc.criteria || "agents watching"}). Next scan in ~45s.</p>`;
      return;
    }
    el.innerHTML = setups.map((s) => {
      const cls = s.direction === "LONG" ? "long" : "short";
      const st = s.status === "ACTIVE" ? "active" : "watch";
      return `<article class="scalp-card ${cls} ${st}">
        <header>
          <span class="scalp-dir">${esc(s.direction)}</span>
          <span class="scalp-status">${esc(s.status)}</span>
          <span class="scalp-conf">${s.confidence}%</span>
        </header>
        <p class="scalp-live-ref">Live gold: <strong>$${s.market_price ?? s.entry}</strong></p>
        <div class="scalp-levels">
          <div><label>Entry</label><span>${s.entry}</span></div>
          <div><label>Stop</label><span>${s.stop}</span></div>
          <div><label>Target</label><span>${s.target}</span></div>
          <div><label>T2</label><span>${s.target_2}</span></div>
          <div><label>RR</label><span>${s.risk_reward}:1</span></div>
          <div><label>${s.leverage}x</label><span>~${s.margin_at_risk_pct}% margin @ stop</span></div>
        </div>
        <p class="scalp-thesis">${esc(s.thesis)}</p>
        <p class="war-muted scalp-votes">${s.agent_votes}/5 agents: ${esc((s.agents_aligned || []).join(", "))} · ${esc(s.timeframe)}</p>
      </article>`;
    }).join("");
  }

  function renderPerformance(p) {
    const el = $("performance-content");
    if (!el) return;
    const scans = p.recent_scans || [];
    const scalps = p.recent_scalps || [];
    el.innerHTML = `
      <div class="perf-grid-inner">
      <div class="perf-stat"><div class="val">${p.total_scans_logged ?? 0}</div><div class="lbl">Agent scans logged</div></div>
      <div class="perf-stat"><div class="val">${p.total_scalps_logged ?? 0}</div><div class="lbl">Scalps logged</div></div>
      <div class="perf-stat"><div class="val">${p.average_scalp_rr ?? 0}</div><div class="lbl">Avg scalp RR</div></div>
      <div class="perf-stat"><div class="val">${p.last_scan_at ? "✓" : "—"}</div><div class="lbl">Last scan</div></div>
      </div>
      <p class="war-muted perf-log-note">Logged to <code>${esc(p.log_file || "data/gold_war_room_history.json")}</code></p>
      <h4 class="perf-log-title">Recent scans</h4>
      <div class="perf-log-table">${scans.length ? scans.map((s) =>
        `<div class="perf-log-row"><span>${esc(s.logged_at || "")}</span><span>$${s.price}</span><span>${esc(s.bias)}</span><span>${s.scalps_found} scalps</span></div>`
      ).join("") : "<span class='war-muted'>No scans logged yet</span>"}</div>
      <h4 class="perf-log-title">Recent scalps lodged</h4>
      <div class="perf-log-table">${scalps.length ? scalps.map((s) =>
        `<div class="perf-log-row"><span>${esc(s.logged_at || "")}</span><span>${esc(s.direction)} @ $${s.market_price}</span><span>E ${s.entry} S ${s.stop} T ${s.target}</span><span>RR ${s.risk_reward}</span></div>`
      ).join("") : "<span class='war-muted'>No scalps logged yet</span>"}</div>
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

    const agentKeys = data.agents ? Object.keys(data.agents) : [];
    if (!data.ok && agentKeys.length === 0) {
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
    renderScalping(data.scalping);
    renderLiveScan(data.live_scan, data.updated_at);
  }

  let warmPolls = 0;
  let scalpLeverage = Number($("scalp-leverage")?.value) || 30;

  async function load(refresh = false, retries = 0) {
    const btn = $("btn-war-refresh");
    if (btn) btn.disabled = true;
    if (!refresh || warmPolls === 0) {
      $("bias-why").textContent = "Running 7 agents + master synthesis…";
      $("consensus-table").innerHTML = "<span class='war-muted'>Analyzing…</span>";
    }
    try {
      const q = new URLSearchParams();
      if (refresh) q.set("refresh", "1");
      q.set("leverage", String(scalpLeverage));
      const res = await fetch(`/api/gold-war-room?${q}`, { cache: "no-store" });
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

  const heightRange = $("chart-height-range");
  const savedH = localStorage.getItem("warChartHeight");
  if (heightRange && savedH) heightRange.value = savedH;
  setChartHeight(heightRange?.value || 500);
  heightRange?.addEventListener("input", () => setChartHeight(heightRange.value));

  $("chart-symbol")?.addEventListener("change", (e) => {
    reloadTradingViewEmbed(null, e.target.value);
  });

  document.querySelectorAll(".chart-tf").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelectorAll(".chart-tf").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const iv = btn.getAttribute("data-interval") || "60";
      reloadTradingViewEmbed(iv, $("chart-symbol")?.value);
    });
  });

  $("scalp-leverage")?.addEventListener("change", (e) => {
    scalpLeverage = Number(e.target.value) || 30;
    load(true);
  });

  const boot = readBootstrap();
  if (boot?.ok && boot.agents && Object.keys(boot.agents).length) {
    apply(boot);
  }

  $("btn-war-refresh")?.addEventListener("click", () => load(true));
  load(false);
  setInterval(() => load(false), 45000);
})();
