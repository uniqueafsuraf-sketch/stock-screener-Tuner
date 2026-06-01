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
  }

  async function load(refresh = false) {
    const btn = $("btn-war-refresh");
    if (btn) btn.disabled = true;
    $("bias-why").textContent = "Running 7 agents + master synthesis…";
    $("consensus-table").innerHTML = "<span class='war-muted'>Analyzing…</span>";
    try {
      const res = await fetch(`/api/gold-war-room${refresh ? "?refresh=1" : ""}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`Server ${res.status}`);
      const json = await res.json();
      apply(json);
    } catch (e) {
      $("bias-why").textContent = `Network error: ${e.message}. Try Refresh.`;
      showStatusBanner({ error: e.message, fetch_notes: [] });
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  $("btn-war-refresh")?.addEventListener("click", () => load(true));
  load(false);
  setInterval(() => load(false), 120000);
})();
