// Growth Ops Console - plain JavaScript, no framework.
// Data comes from the Flask API (web/server.py), which reads the pipeline's SQLite db.

const state = { leads: [], config: null, summary: null };
const ACCENT = "#5B4BDB", MUTED = "#C9C3F2", GRID = "#E6E6EE";
const CHANNEL_LABELS = {
  partner_accountant: "Accountant partner", referral: "Referral",
  paid_google: "Paid search", seo: "SEO", paid_meta: "Paid social (Meta)",
};

// ---------- helpers ----------
const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, options) => {
  const res = await fetch(path, options);
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || res.statusText);
  return body;
};
const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
const channelLabel = (c) => CHANNEL_LABELS[c] || c;

function ratingPill(lead) {
  if (lead.routed_to !== "crm") return `<span class="pill cold">${lead.score}</span>`;
  return `<span class="pill ${lead.Rating === "Hot" ? "hot" : "warm"}">${lead.score} · ${esc(lead.Rating)}</span>`;
}

// ---------- tabs ----------
document.querySelectorAll("#tabs button").forEach((btn) =>
  btn.addEventListener("click", () => showView(btn.dataset.view)));

function showView(name) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === `view-${name}`));
  if (name === "overview") window.dispatchEvent(new Event("resize")); // let Plotly re-measure
  history.replaceState(null, "", `#${name}`);
}

// ---------- overview ----------
function renderKpis(s) {
  const kpis = [
    ["Sign-ups", s.events, "Segment track events"],
    ["Enriched", `${pct(s.enriched, s.events)}%`, `${s.partial} with a missing field`],
    ["Leads to Sales", s.crm, `${pct(s.crm, s.events)}% · ${s.hot} rated Hot`],
    ["To nurture", s.braze, "Braze user import"],
    ["AI notes flagged", s.notes_flagged, `of ${s.crm} notes (${s.notes_llm} by LLM)`],
  ];
  $("#kpis").innerHTML = kpis.map(([label, value, sub]) =>
    `<div class="card kpi"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub}</div></div>`).join("");
}

function renderFlow(s) {
  const step = (n, t, d) => `<div class="step"><div class="n">${n}</div><div class="t">${t}</div><div class="d">${d}</div></div>`;
  const arrow = `<div class="arrow">→</div>`;
  $("#flow").innerHTML = [
    step(s.events, "Sign-up events", "Segment · Account Signed Up"), arrow,
    step(s.enriched, "Enriched", "api.gouv.fr by SIREN"), arrow,
    step(s.scored, "Scored", "rules: size · age · sector · channel"), arrow,
    `<div class="step split">
       <div class="crm"><b>${s.crm}</b> → Salesforce lead</div>
       <div><b>${s.braze}</b> → Braze nurture</div>
     </div>`, arrow,
    step(s.notes_llm, "AI sales notes", `${s.notes_flagged} flagged for review`),
  ].join("");
}

function renderSimulator() {
  const slider = $("#sim-slider");
  const current = state.config.scoring.threshold;
  slider.value = current;
  const update = () => {
    const t = Number(slider.value);
    const total = state.leads.length;
    const toSales = state.leads.filter((l) => l.score >= t);
    $("#sim-t").textContent = t;
    $("#sim-result").innerHTML =
      `Sales would receive <b>${toSales.length}</b> of ${total} sign-ups (<b>${pct(toSales.length, total)}%</b>)` +
      (t === current ? ` <span class="muted">· current setting in config.yaml</span>`
                     : ` <span class="muted">· today: ${state.leads.filter((l) => l.score >= current).length} at ${current}</span>`);

    const byChannel = {};
    state.leads.forEach((l) => {
      const c = (byChannel[l.source_channel] ||= { total: 0, sales: 0 });
      c.total += 1;
      if (l.score >= t) c.sales += 1;
    });
    $("#sim-channels").innerHTML = Object.entries(byChannel)
      .sort((a, b) => b[1].sales / b[1].total - a[1].sales / a[1].total)
      .map(([ch, c]) => `<div class="sim-row"><span>${channelLabel(ch)}</span>
        <div class="sim-bar"><span style="width:${pct(c.sales, c.total)}%"></span></div>
        <span class="muted">${c.sales}/${c.total}</span></div>`).join("");
  };
  slider.addEventListener("input", update);
  update();
}

const layout = (title, extra = {}) => ({
  title: { text: title, x: 0, font: { size: 14 } }, height: 330,
  margin: { l: 10, r: 30, t: 44, b: 10 }, paper_bgcolor: "white", plot_bgcolor: "white",
  font: { family: "Inter, Segoe UI, sans-serif", size: 12, color: "#1C1B29" },
  xaxis: { gridcolor: GRID, automargin: true }, yaxis: { gridcolor: GRID, automargin: true },
  legend: { orientation: "h", y: 1.12, x: 1, xanchor: "right" }, ...extra,
});
const plot = (id, data, lay) => Plotly.newPlot(id, data, lay, { displayModeBar: false, responsive: true });

async function renderCharts() {
  const [ch, sec, dist, age] = await Promise.all([
    api("/api/sql/01_hot_leads_by_channel"), api("/api/sql/02_top_sectors"),
    api("/api/sql/03_score_distribution"), api("/api/sql/04_signups_by_company_age"),
  ]);
  const t = state.config.scoring.threshold;

  ch.sort((a, b) => a.hot_rate_pct - b.hot_rate_pct);
  plot("chart-channel", [{
    type: "bar", orientation: "h", x: ch.map((r) => r.hot_rate_pct), y: ch.map((r) => channelLabel(r.source_channel)),
    marker: { color: ACCENT }, text: ch.map((r) => `${r.hot_rate_pct}%`), textposition: "outside", cliponaxis: false,
    customdata: ch.map((r) => [r.hot_leads, r.signups]),
    hovertemplate: "%{y}: %{customdata[0]} of %{customdata[1]} sign-ups to Sales<extra></extra>",
  }], layout("Share of sign-ups sent to Sales, by channel", { xaxis: { gridcolor: GRID, ticksuffix: "%", range: [0, 100], automargin: true } }));

  sec.sort((a, b) => a.signups - b.signups);
  plot("chart-sector", [
    { type: "bar", orientation: "h", name: "Nurture (Braze)", x: sec.map((r) => r.signups - r.hot_leads), y: sec.map((r) => r.sector), marker: { color: MUTED } },
    { type: "bar", orientation: "h", name: "Sales (CRM)", x: sec.map((r) => r.hot_leads), y: sec.map((r) => r.sector), marker: { color: ACCENT } },
  ], layout("Top sectors - sign-ups by route", { barmode: "stack" }));

  plot("chart-score", [{
    type: "bar", x: dist.map((r) => r.bucket_label), y: dist.map((r) => r.leads),
    marker: { color: dist.map((r) => (r.score_bucket >= t ? ACCENT : MUTED)) },
    customdata: dist.map((r) => r.leads_at_or_above),
    hovertemplate: "Score %{x}: %{y} leads<br>%{customdata} at or above<extra></extra>",
  }], layout(`Lead score distribution (threshold ${t})`));

  plot("chart-age", [
    { type: "bar", name: "Sales (CRM)", x: age.map((r) => r.age_bucket.slice(3)), y: age.map((r) => r.hot_leads), marker: { color: ACCENT } },
    { type: "bar", name: "Nurture (Braze)", x: age.map((r) => r.age_bucket.slice(3)), y: age.map((r) => r.nurture), marker: { color: MUTED } },
  ], layout("Sign-ups by company age", { barmode: "stack" }));
}

// ---------- leads ----------
function setupLeadFilters() {
  const channels = [...new Set(state.leads.map((l) => l.source_channel))].sort();
  $("#f-channel").innerHTML += channels.map((c) => `<option value="${c}">${channelLabel(c)}</option>`).join("");
  ["#f-search", "#f-route", "#f-channel", "#f-rating", "#f-flagged"].forEach((id) =>
    $(id).addEventListener("input", renderLeads));
}

function renderLeads() {
  const q = $("#f-search").value.trim().toLowerCase();
  const route = $("#f-route").value, channel = $("#f-channel").value, rating = $("#f-rating").value;
  const flaggedOnly = $("#f-flagged").checked;

  const rows = state.leads.filter((l) =>
    (!q || [l.company_name, l.city, l.siren, l.sector_label, l.naf_label].join(" ").toLowerCase().includes(q)) &&
    (!route || l.routed_to === route) &&
    (!channel || l.source_channel === channel) &&
    (!rating || l.Rating === rating) &&
    (!flaggedOnly || l.note_flags));

  $("#f-count").textContent = `${rows.length} of ${state.leads.length}`;
  $("#leads-body").innerHTML = rows.map((l) => `
    <tr data-siren="${esc(l.siren)}">
      <td>${ratingPill(l)}</td>
      <td><b>${esc(l.company_name)}</b><br><span class="muted">${esc(l.legal_form)} · ${esc(l.siren)}</span></td>
      <td>${esc(l.sector_label)}<br><span class="muted">${esc(l.naf_label)}</span></td>
      <td>${esc(l.headcount_label ?? "Unknown")}</td>
      <td>${esc(l.city ?? "-")}</td>
      <td>${esc(channelLabel(l.source_channel))}</td>
      <td>${l.routed_to === "crm" ? `<span class="tag crm">${esc(l.OwnerQueue)}</span>` : `<span class="tag">${esc(l.nurture_track)}</span>`}</td>
      <td class="note">${l.note ? `<div class="clip">${esc(l.note)}</div>${l.note_flags ? `<span class="flag">⚠ flagged</span>` : ""}` : `<span class="muted">-</span>`}</td>
    </tr>`).join("") || `<tr><td colspan="8" class="muted">No leads match these filters.</td></tr>`;
}

$("#leads-body").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-siren]");
  if (tr) openLead(tr.dataset.siren);
});

// ---------- lead detail drawer ----------
function openLead(siren) {
  const l = state.leads.find((x) => x.siren === siren);
  const max = state.config.max_points;
  const bar = (label, pts, m) => `<div class="bd-row"><span>${label}</span>
    <div class="sim-bar"><span style="width:${pct(pts, m)}%"></span></div><span class="pts">${pts} / ${m}</span></div>`;

  const segmentEvent = {
    type: "track", event: l.event, messageId: l.message_id, anonymousId: l.anonymous_id, timestamp: l.timestamp,
    properties: { siren: l.siren, company_name: l.company_name, source_channel: l.source_channel,
      utm_source: l.utm_source, utm_medium: l.utm_medium, utm_campaign: l.utm_campaign, plan_chosen: l.plan_chosen },
  };

  const routing = l.routed_to === "crm"
    ? `<dl class="facts">
         <dt>Destination</dt><dd><span class="tag crm">Salesforce lead</span></dd>
         <dt>Rating</dt><dd>${esc(l.Rating)}</dd>
         <dt>Owner queue</dt><dd>${esc(l.OwnerQueue)}</dd>
         <dt>Lead source</dt><dd>${esc(l.LeadSource)}</dd>
       </dl>`
    : `<dl class="facts">
         <dt>Destination</dt><dd><span class="tag">Braze nurture</span></dd>
         <dt>Nurture track</dt><dd>${esc(l.nurture_track)}</dd>
         <dt>Why not Sales</dt><dd>Score ${l.score} is below ${state.config.scoring.threshold}</dd>
       </dl>`;

  const note = l.note
    ? `<section><h4>AI sales note <span class="tag">${esc(l.note_source)}</span></h4>
         <div class="note-box ${l.note_flags ? "flagged" : ""}">${esc(l.note)}</div>
         ${l.note_flags ? `<p class="flag">⚠ Held for review: ${esc(l.note_flags)}</p>`
                        : `<p class="ok">✓ Validated: only uses facts from the enriched data</p>`}
       </section>`
    : "";

  $("#drawer").innerHTML = `
    <button class="close" aria-label="Close">×</button>
    <h3>${esc(l.company_name)}</h3>
    <div class="muted">SIREN ${esc(l.siren)} · ${esc(l.city ?? "city unknown")} ·
      <a href="https://annuaire-entreprises.data.gouv.fr/entreprise/${encodeURIComponent(l.siren)}" target="_blank" rel="noopener">public record ↗</a></div>

    <section>
      <h4>Lead score</h4>
      <div class="score-big"><span class="n">${l.score}</span><span class="muted">/ 100 · ${l.routed_to === "crm" ? "sent to Sales" : "nurture"}</span></div>
      ${bar("Headcount", l.pts_headcount, max.headcount)}
      ${bar("Company age", l.pts_age, max.age)}
      ${bar("Sector", l.pts_sector, max.sector)}
      ${bar("Channel", l.pts_channel, max.channel)}
    </section>

    ${note}

    <section><h4>Routing</h4>${routing}</section>

    <section>
      <h4>Enriched data</h4>
      <dl class="facts">
        <dt>Activity (NAF)</dt><dd>${esc(l.naf_code)} · ${esc(l.naf_label)}</dd>
        <dt>Sector</dt><dd>${esc(l.sector_label)} (section ${esc(l.sector_section)})</dd>
        <dt>Employees</dt><dd>${esc(l.headcount_label ?? "Unknown")}</dd>
        <dt>Created</dt><dd>${esc(l.creation_date)} · ${esc(l.company_age_years)} years</dd>
        <dt>City</dt><dd>${esc(l.city ?? "-")} ${esc(l.postal_code ?? "")}</dd>
        <dt>Legal form</dt><dd>${esc(l.legal_form)}</dd>
        <dt>Enrichment</dt><dd>${l.enrichment_status === "ok" ? `<span class="ok">complete</span>`
          : `<span class="flag">${esc(l.enrichment_status)}: missing ${esc(l.missing_fields)}</span>`}</dd>
      </dl>
    </section>

    <section>
      <h4>Source event (Segment)</h4>
      <pre class="json">${esc(JSON.stringify(segmentEvent, null, 2))}</pre>
    </section>`;

  $("#drawer").classList.add("open");
  $("#scrim").classList.add("open");
  $("#drawer .close").addEventListener("click", closeLead);
}

function closeLead() {
  $("#drawer").classList.remove("open");
  $("#scrim").classList.remove("open");
}
$("#scrim").addEventListener("click", closeLead);
document.addEventListener("keydown", (e) => e.key === "Escape" && closeLead());

// ---------- SQL ----------
async function setupSql() {
  const files = await api("/api/sql");
  const pretty = (name) => name.replace(/^\d+_/, "").replaceAll("_", " ");
  $("#sql-list").innerHTML =
    files.map((f) => `<button data-name="${f.name}">${esc(pretty(f.name))}</button>`).join("") +
    `<div class="sep"></div><button data-name="__custom">✎ Write your own</button>`;

  const select = (name) => {
    document.querySelectorAll("#sql-list button").forEach((b) => b.classList.toggle("active", b.dataset.name === name));
    if (name === "__custom") {
      $("#sql-title").textContent = "Custom query";
      $("#sql-text").value = "SELECT Company, City, Lead_Score__c, Sales_Note__c\nFROM crm_leads\nWHERE OwnerQueue = 'Partnerships'\nORDER BY Lead_Score__c DESC;";
    } else {
      const f = files.find((x) => x.name === name);
      $("#sql-title").textContent = `${f.name}.sql`;
      $("#sql-text").value = f.sql;
    }
    runSql();
  };
  $("#sql-list").addEventListener("click", (e) => e.target.dataset.name && select(e.target.dataset.name));
  $("#sql-run").addEventListener("click", runSql);
  $("#sql-text").addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") runSql();
  });
  select(files[0].name);
}

async function runSql() {
  const out = $("#sql-result");
  try {
    const t0 = performance.now();
    const rows = await api("/api/query", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sql: $("#sql-text").value }),
    });
    const ms = Math.round(performance.now() - t0);
    if (!rows.length) { out.innerHTML = `<div class="result-meta">0 rows · ${ms} ms</div>`; return; }
    const cols = Object.keys(rows[0]);
    const isNum = (c) => rows.every((r) => r[c] === null || typeof r[c] === "number");
    out.innerHTML = `<div class="result-meta">${rows.length} rows · ${ms} ms</div>
      <table><thead><tr>${cols.map((c) => `<th class="${isNum(c) ? "num" : ""}">${esc(c)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map((r) => `<tr>${cols.map((c) => `<td class="${isNum(c) ? "num" : ""}">${esc(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  } catch (err) {
    out.innerHTML = `<div class="error">${esc(err.message)}</div>`;
  }
}

// ---------- scoring rules ----------
function renderRules() {
  const s = state.config.scoring, max = state.config.max_points;
  const bands = (list, unit, unknown) => {
    const sorted = [...list].sort((a, b) => a[0] - b[0]);
    return sorted.map(([min, pts], i) => {
      const next = sorted[i + 1];
      const range = next ? `${min} – ${next[0] - (unit === "employees" ? 1 : 0)}` : `${min}+`;
      return `<tr><td>${range} ${unit}</td><td class="num"><b>${pts}</b></td></tr>`;
    }).join("") + `<tr><td class="muted">unknown</td><td class="num">${unknown}</td></tr>`;
  };
  const dict = (obj, label = (k) => k) => Object.entries(obj).sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<tr><td>${esc(label(k))}</td><td class="num"><b>${v}</b></td></tr>`).join("");
  const SECTIONS = { J: "IT & Telecom", M: "Professional Services", F: "Construction", G: "Retail & Wholesale", N: "Business Support", I: "Hospitality & Food" };

  $("#rules").innerHTML = `
    <div class="card"><h2>Headcount <span class="max">max ${max.headcount}</span></h2><table>${bands(s.headcount_bands, "employees", s.headcount_unknown)}</table></div>
    <div class="card"><h2>Company age <span class="max">max ${max.age}</span></h2><table>${bands(s.age_bands, "years", s.age_unknown)}</table></div>
    <div class="card"><h2>Sector (NAF section) <span class="max">max ${max.sector}</span></h2><table>${dict(s.sector_points, (k) => `${k} · ${SECTIONS[k] || k}`)}
      <tr><td class="muted">any other sector</td><td class="num">${s.sector_default}</td></tr></table></div>
    <div class="card"><h2>Acquisition channel <span class="max">max ${max.channel}</span></h2><table>${dict(s.channel_points, channelLabel)}</table></div>
    <div class="card"><h2>Routing</h2><table>
      <tr><td>Score ≥ <b>${s.threshold}</b></td><td>Salesforce lead</td></tr>
      <tr><td>Score ≥ <b>${s.hot_rating_threshold}</b></td><td>Rating = Hot</td></tr>
      <tr><td>Accountant partner</td><td>Queue: Partnerships</td></tr>
      <tr><td>≥ ${state.config.routing.midmarket_min_headcount} employees</td><td>Queue: MidMarket_AE</td></tr>
      <tr><td>Otherwise</td><td>Queue: SMB_Outbound</td></tr>
      <tr><td>Score &lt; ${s.threshold}</td><td>Braze nurture</td></tr></table>
      <p class="muted">All values are read live from <code>config.yaml</code>. AI notes model: ${esc(state.config.model)}.</p></div>`;
}

// ---------- boot ----------
(async function init() {
  [state.summary, state.leads, state.config] = await Promise.all([api("/api/summary"), api("/api/leads"), api("/api/config")]);
  renderKpis(state.summary);
  renderFlow(state.summary);
  renderSimulator();
  setupLeadFilters();
  renderLeads();
  renderRules();
  await Promise.all([renderCharts(), setupSql()]);
  const start = location.hash.slice(1);
  if (["leads", "sql", "rules"].includes(start)) showView(start);
  if (start.startsWith("lead=")) { showView("leads"); openLead(start.slice(5)); } // e.g. #lead=331747485
})();
