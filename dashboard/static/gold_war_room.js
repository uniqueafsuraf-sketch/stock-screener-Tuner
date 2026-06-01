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

  function stationStatusClass(status) {
    const s = (status || "").toLowerCase();
    if (s === "active") return "st-active";
    if (s === "warning" || s === "error") return "st-warn";
    return "st-idle";
  }

  function renderCrewmate(st) {
    const cls = stationStatusClass(st.status);
    const activity = st.activity || (cls === "st-active" ? "working" : "patrol");
    const color = st.crew_color || "#7f8c8d";
    const x = st.map_x != null ? st.map_x : 50;
    const y = st.map_y != null ? st.map_y : 70;
    const room = st.map_room || st.id;
    const isBoss = st.tier === "command" || st.id === "boss";
    return `
      <div class="au-crew ${cls} activity-${activity}${isBoss ? " au-crew-boss" : ""}"
           data-room="${esc(room)}"
           data-agent="${esc(st.id)}"
           style="--crew-color:${color};left:${x}%;top:${y}%"
           title="${esc(st.character)} — ${esc(st.task_label)}">
        <div class="au-speech">
          <strong>${esc(st.task_label)}</strong>
          <span>${esc(st.intel || st.working_on)}</span>
        </div>
        <div class="au-crewmate" aria-hidden="true">
          <div class="au-body"></div>
          <div class="au-visor"></div>
          <div class="au-backpack"></div>
          ${activity === "working" ? '<div class="au-sparkles"></div>' : ""}
        </div>
        <span class="au-crew-label">${esc(st.character || st.name)}</span>
        <span class="au-crew-stance ${(st.stance || "").toLowerCase()}">${esc(st.stance)}</span>
      </div>`;
  }

  function renderMapRoom(room, crewInRoom) {
    const busy = crewInRoom.some((c) => stationStatusClass(c.status) === "st-active");
    return `
      <div class="au-room ${busy ? "au-room-busy" : ""}" data-room-id="${esc(room.id)}"
           style="left:${room.x}%;top:${room.y}%;width:${room.w}%;height:${room.h}%">
        <span class="au-room-label">${esc(room.label)}</span>
        <div class="au-room-console">
          <span class="au-console-line"></span>
          <span class="au-console-line"></span>
          <span class="au-console-line"></span>
        </div>
      </div>`;
  }

  function renderHudCard(st) {
    const cls = stationStatusClass(st.status);
    return `
      <article class="au-hud-card ${cls}" data-agent="${esc(st.id)}">
        <header>
          <span class="au-hud-dot" style="background:${st.crew_color || '#888'}"></span>
          <strong>${esc(st.character || st.name)}</strong>
          <span class="au-hud-status">${esc(st.status)}</span>
        </header>
        <p class="au-hud-task">${esc(st.task_label)}</p>
        <p class="au-hud-intel">${esc(st.intel || st.working_on)}</p>
        <p class="au-hud-detail">${esc(st.working_on)}</p>
        <p class="au-hud-report">${esc(st.output)}</p>
      </article>`;
  }

  function renderAgentStations(ops) {
    const sub = $("stations-subtitle");
    const head = $("stations-headline");
    const mapRooms = $("ops-map-rooms");
    const mapCrew = $("ops-map-crew");
    const hudList = $("ops-hud-list");
    const chip = $("ops-floor-status-chip");
    const meta = $("ops-meta");

    const crew = ops?.crew || [...(ops?.overseers || []), ...(ops?.stations || [])];
    const rooms = ops?.map_rooms || [];

    if (!crew.length) {
      if (mapCrew) mapCrew.innerHTML = "";
      if (mapRooms) mapRooms.innerHTML = "<p class='au-map-loading'>Deploying crew to floor…</p>";
      if (hudList) hudList.innerHTML = "";
      return;
    }
    if (sub) sub.textContent = ops.subtitle || "";
    if (head) head.textContent = ops.headline || "";
    if (chip) chip.textContent = ops.floor_status || "Floor status";
    const updated = document.querySelector("#war-meta")?.textContent || "";
    if (meta) meta.textContent = updated.includes("Updated") ? updated : `XAUUSD desk · ${ops.scan_interval_sec || 45}s refresh`;

    if (mapRooms && rooms.length) {
      mapRooms.innerHTML = rooms.map((room) => {
        const inRoom = crew.filter((c) => c.map_room === room.id);
        return renderMapRoom(room, inRoom);
      }).join("");
    }

    if (mapCrew) {
      mapCrew.innerHTML = crew.map((st) => renderCrewmate(st)).join("");
    }

    if (hudList) {
      const order = ["boss", "ops", "macro", "technical", "order_flow", "sentiment", "quant", "risk", "trap"];
      const sorted = [...crew].sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
      hudList.innerHTML = sorted.map((st) => renderHudCard(st)).join("");
    }
  }

  function setWarView(view) {
    const desk = $("view-desk");
    const ops = $("view-ops");
    const navDesk = $("nav-war-desk");
    const navOps = $("nav-war-ops");
    const isOps = view === "ops";
    if (desk) desk.hidden = isOps;
    if (ops) ops.hidden = !isOps;
    navDesk?.classList.toggle("active", !isOps);
    navOps?.classList.toggle("active", isOps);
    if (isOps) {
      document.title = "Agent Operations — Gold War Room";
    } else {
      document.title = "Gold AI War Room";
    }
    try {
      localStorage.setItem("warRoomView", view);
    } catch { /* ignore */ }
    const wantHash = isOps ? "#operations" : "";
    if (location.hash !== wantHash) {
      history.replaceState(null, "", location.pathname + wantHash);
    }
  }

  function initWarNavigation() {
    document.querySelectorAll("[data-war-view]").forEach((el) => {
      el.addEventListener("click", (e) => {
        const view = el.getAttribute("data-war-view");
        if (!view) return;
        if (el.tagName === "A") e.preventDefault();
        setWarView(view);
      });
    });
    $("btn-ops-refresh")?.addEventListener("click", () => load(true));
    const saved = localStorage.getItem("warRoomView");
    const hashOps = location.hash === "#operations";
    setWarView(hashOps || saved === "ops" ? "ops" : "desk");
    window.addEventListener("hashchange", () => {
      setWarView(location.hash === "#operations" ? "ops" : "desk");
    });
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
      allow_symbol_change: false,
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
      const tv = L.tradingview || "https://www.tradingview.com/chart/?symbol=OANDA:XAUUSD";
      links.innerHTML = `<a href="${esc(tv)}" target="_blank" rel="noopener">Open XAUUSD on TradingView</a>`;
    }
  }

  function renderMarketBias(mb, cm) {
    const headlineEl = $("bias-headline");
    const meaningEl = $("bias-meaning");
    const agentsEl = $("bias-agents");
    const probEl = $("bias-prob-detail");
    if (!headlineEl) return;

    const bias = mb.bias || "—";
    const headline = mb.headline || (
      bias.toLowerCase() === "bullish" ? "Gold is leaning BULLISH"
        : bias.toLowerCase() === "bearish" ? "Gold is leaning BEARISH"
          : bias.toLowerCase() === "neutral" ? "Gold looks NEUTRAL"
            : bias
    );
    headlineEl.textContent = headline;
    headlineEl.className = `war-bias-headline ${biasClass(bias)}`;

    if (meaningEl) {
      meaningEl.textContent = mb.meaning || mb.why || "";
    }
    if (agentsEl) {
      agentsEl.textContent = mb.agents_summary || "";
      agentsEl.hidden = !mb.agents_summary;
    }
    if (probEl) {
      probEl.textContent = mb.probability_detail || "";
      probEl.hidden = !mb.probability_detail;
    }

    const label = mb.confidence_label || cm?.label || "";
    const score = cm?.score ?? mb.confidence ?? 0;
    if ($("confidence-label")) $("confidence-label").textContent = label || "—";
    if ($("confidence-score")) $("confidence-score").textContent = `${Math.round(score)}%`;
    if ($("confidence-fill")) {
      $("confidence-fill").style.width = `${Math.min(100, score || 0)}%`;
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

  let lastScalpSpot = null;

  function renderSpotFeeds(spot) {
    const feeds = $("scalp-feeds");
    if (!feeds) return;
    feeds.hidden = true;
    if (spot?.price == null) return;
    feeds.hidden = false;
    feeds.textContent = `XAUUSD spot $${Number(spot.price).toFixed(2)}`;
  }

  function patchScalpLivePrices(price, label) {
    document.querySelectorAll(".scalp-live-ref strong").forEach((el) => {
      el.textContent = `$${Number(price).toFixed(2)}`;
    });
    document.querySelectorAll(".scalp-live-ref").forEach((el) => {
      const rest = el.textContent.split("·").slice(1).join("·").trim();
      el.innerHTML = `${label || "XAUUSD spot"}: <strong>$${Number(price).toFixed(2)}</strong>${rest ? ` · ${rest}` : ""}`;
    });
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
    const spot = sc.live_spot || lastScalpSpot;
    if (sc.live_spot) lastScalpSpot = sc.live_spot;
    renderSpotFeeds(spot);
    if (sub) sub.textContent = sc.subtitle || sc.title || "";
    if (warn) warn.textContent = sc.leverage_warning || "High leverage — extreme risk.";
    const setups = sc.setups || [];
    if (!setups.length) {
      el.innerHTML = `<p class="scalp-empty">No scalp meeting criteria right now (${sc.criteria || "agents watching"}). Next scan in ~45s.</p>`;
      return;
    }
    el.innerHTML = setups.map((s) => {
      const cls = s.direction === "LONG" ? "long" : "short";
      const st = s.status === "ACTIVE" ? "active" : "watch";
      const risk = s.risk_profile || "HIGH";
      const gain = s.gain_at_target_pct != null ? `+${s.gain_at_target_pct}%` : "—";
      const loss = s.loss_at_stop_pct != null ? `-${s.loss_at_stop_pct}%` : "—";
      return `<article class="scalp-card ${cls} ${st}">
        <header>
          <span class="scalp-dir">${esc(s.direction)}</span>
          <span class="scalp-risk-badge">${esc(risk)}</span>
          <span class="scalp-status">${esc(s.status)}</span>
          <span class="scalp-conf">${s.confidence}%</span>
        </header>
        <p class="scalp-live-ref">${esc(sc.reference_label || "XAUUSD spot")}: <strong>$${s.market_price ?? s.entry}</strong> · ${s.leverage}x</p>
        <div class="scalp-levels">
          <div><label>Entry</label><span>${s.entry}</span></div>
          <div><label>Stop</label><span>${s.stop}</span></div>
          <div><label>Target</label><span>${s.target}</span></div>
          <div><label>T2</label><span>${s.target_2}</span></div>
          <div><label>RR</label><span>${s.risk_reward}:1</span></div>
          <div><label>@ ${s.leverage}x</label><span class="scalp-rr-pct">Win ${gain} / Lose ${loss}</span></div>
        </div>
        <p class="scalp-thesis">${esc(s.thesis)}</p>
        <p class="war-muted scalp-votes">${s.agent_votes}/5 agents: ${esc((s.agents_aligned || []).join(", "))} · ${esc(s.timeframe)}</p>
      </article>`;
    }).join("");
  }

  function outcomeBadge(outcome) {
    const o = (outcome || "open").toLowerCase();
    if (o === "win") return '<span class="perf-outcome win">WIN</span>';
    if (o === "loss") return '<span class="perf-outcome loss">LOSS</span>';
    if (o === "expired") return '<span class="perf-outcome expired">EXPIRED</span>';
    return '<span class="perf-outcome open">OPEN</span>';
  }

  function verdictBadge(verdict, agentsCorrect) {
    if (agentsCorrect === true) return '<span class="perf-verdict correct">Agents ✓</span>';
    if (agentsCorrect === false || verdict === "incorrect") {
      return '<span class="perf-verdict wrong">Agents ✗</span>';
    }
    const v = (verdict || "open").toLowerCase();
    if (v === "correct") return '<span class="perf-verdict correct">Bias ✓</span>';
    if (v === "incorrect") return '<span class="perf-verdict wrong">Bias ✗</span>';
    if (v === "neutral") return '<span class="perf-verdict neutral">Neutral</span>';
    return '<span class="perf-verdict open">Pending</span>';
  }

  function renderPerformance(p) {
    const el = $("performance-content");
    if (!el) return;
    const scans = p.recent_scans || [];
    const scalps = p.recent_scalps || [];
    el.innerHTML = `
      <div class="perf-grid-inner">
      <div class="perf-stat"><div class="val">${p.scalp_win_rate ?? 0}%</div><div class="lbl">Scalp win rate</div></div>
      <div class="perf-stat win-stat"><div class="val">${p.scalp_wins ?? 0}</div><div class="lbl">Wins</div></div>
      <div class="perf-stat loss-stat"><div class="val">${p.scalp_losses ?? 0}</div><div class="lbl">Losses</div></div>
      <div class="perf-stat"><div class="val">${p.agent_scalp_accuracy ?? 0}%</div><div class="lbl">Agents right (closed)</div></div>
      <div class="perf-stat"><div class="val">${p.bias_call_accuracy ?? 0}%</div><div class="lbl">Bias calls right</div></div>
      <div class="perf-stat"><div class="val">${p.open_scalps ?? 0}</div><div class="lbl">Open scalps</div></div>
      </div>
      <p class="war-muted perf-log-note">Wins/losses when price hits target or stop · bias verdict after ~2 min. Log: <code>${esc(p.log_file || "data/gold_war_room_history.json")}</code></p>
      <h4 class="perf-log-title">Recent scalps — result & agents</h4>
      <div class="perf-log-table perf-log-scalps">${scalps.length ? scalps.map((s) =>
        `<div class="perf-log-row perf-log-row-scalp">
          <span>${esc(s.logged_at || "")}</span>
          <span>${esc(s.direction)} ${s.leverage || ""}x</span>
          <span>E ${s.entry} → T ${s.target}</span>
          ${outcomeBadge(s.outcome)}
          ${verdictBadge(s.agent_verdict, s.agents_correct)}
        </div>`
      ).join("") : "<span class='war-muted'>No scalps logged yet — runs build as scans complete</span>"}</div>
      <h4 class="perf-log-title">Recent agent scans — bias correct?</h4>
      <div class="perf-log-table">${scans.length ? scans.map((s) =>
        `<div class="perf-log-row">
          <span>${esc(s.logged_at || "")}</span>
          <span>$${s.price}</span>
          <span>${esc(s.bias)}</span>
          ${verdictBadge(s.agent_verdict)}
          <span class="war-muted">${s.price_delta_pct != null ? s.price_delta_pct + "%" : s.scalps_found + " scalps"}</span>
        </div>`
      ).join("") : "<span class='war-muted'>No scans logged yet</span>"}</div>
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
      renderMarketBias({ headline: "No data", meaning: "No response from server." }, {});
      return;
    }
    showStatusBanner(data);

    const agentKeys = data.agents ? Object.keys(data.agents) : [];
    if (!data.ok && agentKeys.length === 0) {
      renderMarketBias({ headline: "Analysis failed", meaning: data.error || "Try Refresh." }, {});
      return;
    }

    const mb = data.market_bias || {};
    const cm = data.confidence_meter || {};
    renderMarketBias(mb, cm);

    const px = data.price != null ? Number(data.price) : null;
    $("war-price").textContent = px != null
      ? `$${px.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}  ${data.change_pct >= 0 ? "+" : ""}${data.change_pct}%`
      : "—";
    const sym = data.price_symbol || "XAUUSD spot";
    $("war-meta").textContent = `${sym} · Updated ${data.updated_at || "—"}`;
    if (data.live_spot) lastScalpSpot = data.live_spot;

    renderAgentStations(data.agent_stations);
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
  let scalpLeverage = Number($("scalp-leverage")?.value) || 100;

  async function load(refresh = false, retries = 0) {
    const btn = $("btn-war-refresh");
    if (btn) btn.disabled = true;
    if (!refresh || warmPolls === 0) {
      renderMarketBias({
        headline: "Analyzing gold…",
        meaning: "Running 7 agents + master synthesis…",
      }, {});
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
        renderMarketBias({
          headline: "Analyzing gold…",
          meaning: json.message || "Agents analyzing…",
        }, {});
        if (warmPolls < 40) {
          setTimeout(() => load(false), 3000);
        } else {
          renderMarketBias({
            headline: "Still loading",
            meaning: "Click Refresh analysis.",
          }, {});
        }
        return;
      }
      warmPolls = 0;
      apply(json);
    } catch (e) {
      renderMarketBias({
        headline: "Connection issue",
        meaning: `Network error: ${e.message}. Try Refresh.`,
      }, {});
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

  async function refreshLiveSpot() {
    try {
      const res = await fetch("/api/gold-spot?force=1", { cache: "no-store" });
      const j = await res.json();
      if (!j.ok || j.price == null) return;
      lastScalpSpot = j;
      const el = $("war-price");
      if (el) {
        el.textContent = `$${Number(j.price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}  ${j.change_pct >= 0 ? "+" : ""}${j.change_pct}%`;
      }
      const meta = $("war-meta");
      if (meta) {
        const cur = meta.textContent || "";
        const tail = cur.includes("· Updated") ? cur.slice(cur.indexOf("· Updated")) : "";
        meta.textContent = `XAUUSD spot ${tail}`.trim();
      }
      renderSpotFeeds(j);
      patchScalpLivePrices(j.price, "XAUUSD spot");
    } catch { /* ignore */ }
  }

  $("btn-war-refresh")?.addEventListener("click", () => load(true));
  initWarNavigation();
  load(false);
  refreshLiveSpot();
  setInterval(refreshLiveSpot, 15000);
  setInterval(() => load(false), 45000);
})();
