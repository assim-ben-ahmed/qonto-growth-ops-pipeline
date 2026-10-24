// Growth Ops Console - plain JavaScript, no framework.
// Data comes from the Flask API (web/server.py), which reads the pipeline's SQLite db.
// On GitHub Pages there is no server: web/build_static.py saves every GET response as a
// .json file, and SQL runs in the browser on a copy of the db (sql.js).

const STATIC = window.STATIC_SITE === true;
const SQL_JS_DIR = "https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/";
const state = { leads: [], config: null, summary: null, journeys: {}, outbox: {} };
const ACCENT = "#5B4BDB", MUTED = "#C9C3F2", GRID = "#E6E6EE", OUTCOME = "#1E9E7A";
const CHANNEL_LABELS = {
  partner_accountant: "Accountant partner", referral: "Referral",
  paid_google: "Paid search", seo: "SEO", paid_meta: "Paid social (Meta)",
};

// ---------- helpers ----------
const $ = (sel) => document.querySelector(sel);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, options) => {
  if (STATIC && !options) path = `${path}.json`; // pre-built snapshot of the same endpoint
  const res = await fetch(path, options);
  const body = await res.json();
  if (!res.ok) throw new Error(body.error || res.statusText);
  return body;
};
const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
const channelLabel = (c) => CHANNEL_LABELS[c] || c;
const json = (obj) => `<pre class="json">${esc(JSON.stringify(obj, null, 2))}</pre>`;

function ratingPill(lead) {
  if (lead.routed_to !== "crm") return `<span class="pill cold">${lead.score}</span>`;
  return `<span class="pill ${lead.Rating === "Hot" ? "hot" : "warm"}">${lead.score} · ${esc(lead.Rating)}</span>`;
}

// ---------- tabs ----------
const VIEWS = ["overview", "leads", "integrations", "sql", "rules"];
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
    ["Website visitors", s.visitors, `${pct(s.events, s.visitors)}% signed up`],
    ["Sign-ups", s.events, `${pct(s.enriched, s.events)}% enriched · ${s.partial} partial`],
    ["Leads to Sales", s.crm, `${pct(s.crm, s.events)}% · ${s.hot} rated Hot`],
    ["To nurture", s.braze, "Braze /users/track"],
    ["AI notes flagged", s.notes_flagged, `of ${s.crm} notes (${s.notes_llm} by LLM)`],
    ["Score AUC", s.auc ?? "-", "on simulated outcomes · 0.5 = random"],
  ];
  $("#kpis").innerHTML = kpis.map(([label, value, sub]) =>
    `<div class="card kpi"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub}</div></div>`).join("");
}

function renderFlow(s) {
  const step = (n, t, d) => `<div class="step"><div class="n">${n}</div><div class="t">${t}</div><div class="d">${d}</div></div>`;
  const arrow = `<div class="arrow">→</div>`;
  $("#flow").innerHTML = [
    step(s.visitors, "Website visitors", "Segment page · track · identify"), arrow,
    step(s.events, "Sign-ups", "Account Signed Up"), arrow,
    step(s.enriched, "Enriched", "api.gouv.fr by SIREN"), arrow,
    step(s.scored, "Scored", "rules: size · age · sector · channel"), arrow,
    `<div class="step split">
       <div class="crm"><b>${s.crm}</b> → Salesforce lead</div>
       <div><b>${s.braze}</b> → Braze nurture</div>
     </div>`, arrow,
    step(s.notes_llm, "AI sales notes", `${s.notes_flagged} held for review`), arrow,
    step(s.crm + s.braze, "Outbox", "Salesforce · Braze · Meta CAPI payloads"),
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
    const won = state.leads.filter((l) => l.converted).length;
    const wonBySales = toSales.filter((l) => l.converted).length;
    $("#sim-t").textContent = t;
    $("#sim-result").innerHTML =
      `Sales would receive <b>${toSales.length}</b> of ${total} sign-ups (<b>${pct(toSales.length, total)}%</b>) ` +
      `and reach <b>${pct(wonBySales, won)}%</b> of future customers` +
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
  const [funnel, ch, sec, dist, val, age] = await Promise.all([
    api("api/sql/05_website_funnel"), api("api/sql/07_channel_outcomes"), api("api/sql/02_top_sectors"),
    api("api/sql/03_score_distribution"), api("api/sql/06_score_validation"), api("api/sql/04_signups_by_company_age"),
  ]);
  const t = state.config.scoring.threshold;

  const steps = {}; // all channels together
  funnel.forEach((r) => { steps[r.step_order] ||= { step: r.step, visitors: 0 }; steps[r.step_order].visitors += r.visitors; });
  const fs = Object.values(steps);
  plot("chart-funnel", [{
    type: "funnel", y: fs.map((s) => s.step), x: fs.map((s) => s.visitors),
    marker: { color: ACCENT }, textinfo: "value+percent initial",
  }], layout("Website funnel (Segment page / track calls)", { margin: { l: 110, r: 30, t: 44, b: 10 } }));

  ch.sort((a, b) => a.conversion_pct - b.conversion_pct);
  const chY = ch.map((r) => channelLabel(r.source_channel));
  plot("chart-channel", [
    { type: "bar", orientation: "h", name: "Sent to Sales (score)", x: ch.map((r) => r.sent_to_sales_pct), y: chY, marker: { color: ACCENT },
      hovertemplate: "%{y}: %{x}% sent to Sales<extra></extra>" },
    { type: "bar", orientation: "h", name: "Converted (simulated)", x: ch.map((r) => r.conversion_pct), y: chY, marker: { color: OUTCOME },
      hovertemplate: "%{y}: %{x}% converted<extra></extra>" },
  ], layout("Channels: what the score says vs. what converts",
    { barmode: "group", xaxis: { gridcolor: GRID, ticksuffix: "%", range: [0, 100], automargin: true },
      legend: { orientation: "h", y: -0.12, x: 0, traceorder: "normal" } })); // long title: legend below

  plot("chart-score", [{
    type: "bar", x: dist.map((r) => r.bucket_label), y: dist.map((r) => r.leads),
    marker: { color: dist.map((r) => (r.score_bucket >= t ? ACCENT : MUTED)) },
    customdata: dist.map((r) => r.leads_at_or_above),
    hovertemplate: "Score %{x}: %{y} leads<br>%{customdata} at or above<extra></extra>",
  }], layout(`Lead score distribution (threshold ${t})`));

  plot("chart-validation", [{
    type: "bar", x: val.map((r) => r.score_group), y: val.map((r) => r.conversion_pct), marker: { color: OUTCOME },
    text: val.map((r) => `lift ${r.lift.toFixed(2)}`), textposition: "outside", cliponaxis: false,
    customdata: val.map((r) => [r.score_range, r.cum_share_of_conversions_pct]),
    hovertemplate: "Scores %{customdata[0]}: %{y}% converted<br>%{customdata[1]}% of all conversions so far<extra></extra>",
  }], layout(`Does the score predict conversion? AUC ${state.summary.auc}`,
    { yaxis: { gridcolor: GRID, ticksuffix: "%", range: [0, 100], automargin: true } }));

  sec.sort((a, b) => a.signups - b.signups);
  plot("chart-sector", [
    { type: "bar", orientation: "h", name: "Nurture (Braze)", x: sec.map((r) => r.signups - r.hot_leads), y: sec.map((r) => r.sector), marker: { color: MUTED } },
    { type: "bar", orientation: "h", name: "Sales (CRM)", x: sec.map((r) => r.hot_leads), y: sec.map((r) => r.sector), marker: { color: ACCENT } },
  ], layout("Top sectors - sign-ups by route", { barmode: "stack" }));

  const ageX = age.map((r) => r.age_bucket.slice(3));
  plot("chart-age", [
    { type: "bar", name: "Sales (CRM)", x: ageX, y: age.map((r) => r.hot_leads), marker: { color: ACCENT } },
    { type: "bar", name: "Nurture (Braze)", x: ageX, y: age.map((r) => r.nurture), marker: { color: MUTED } },
    { type: "scatter", mode: "lines+markers", name: "Converted %", x: ageX, y: age.map((r) => r.conversion_pct),
      yaxis: "y2", line: { color: OUTCOME }, hovertemplate: "%{x}: %{y}% converted<extra></extra>" },
  ], layout("Sign-ups by company age", { barmode: "stack",
    yaxis2: { overlaying: "y", side: "right", ticksuffix: "%", range: [0, 100], showgrid: false } }));
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
function ago(fromIso, toIso) {
  const min = Math.round((new Date(toIso) - new Date(fromIso)) / 60000);
  if (min <= 0) return "at sign-up";
  if (min < 60) return `${min} min before`;
  if (min < 48 * 60) return `${Math.round(min / 60)} h before`;
  return `${Math.round(min / 1440)} days before`;
}

function journeyHtml(l) {
  const calls = state.journeys[l.anonymous_id] || [];
  const label = (c) => {
    if (c.type === "page") return `<b>page</b> ${esc(c.name)} <span class="muted">${esc(c.path)}</span>` +
      (c.name === "Landing" ? `<br><span class="muted">utm ${esc(c.utm_source)} / ${esc(c.utm_medium)}${c.click_id ? ` · click id ${esc(c.click_id)}` : ""}</span>` : "");
    if (c.type === "identify") return `<b>identify</b> anonymousId → userId <code>${esc(c.user_id)}</code>`;
    return `<b>track</b> ${esc(c.name)}`;
  };
  return `<ol class="timeline">${calls.map((c) =>
    `<li class="${c.type}"><span class="when">${ago(c.timestamp, l.timestamp)}</span>${label(c)}</li>`).join("")}</ol>`;
}

function payloadsHtml(l) {
  const records = (name, key) => (state.outbox[name] || []).flatMap((req) => key(req.body));
  const sf = records("salesforce_leads_upsert", (b) => b.records).find((r) => r.SIREN__c === l.siren);
  const brazeAttr = records("braze_users_track", (b) => b.attributes).find((r) => r.external_id === l.siren);
  const brazeEvent = records("braze_users_track", (b) => b.events).find((r) => r.external_id === l.siren);
  const meta = records("meta_conversions_api", (b) => b.data).find((r) => r.event_id === `qualified_${l.siren}`);
  if (sf) return `<p class="muted">Salesforce · upsert on External ID <code>SIREN__c</code></p>${json(sf)}
    <p class="muted">Meta Conversions API · ${meta.user_data.fbc ? "with the ad click id (fbc)" : "no Meta click id: matched on hashed external_id only"}</p>${json(meta)}`;
  if (brazeAttr) return `<p class="muted">Braze /users/track · attributes + event that starts the Canvas</p>${json({ attributes: brazeAttr, event: brazeEvent })}`;
  return `<p class="muted">Run the outbox stage to generate payloads.</p>`;
}

function openLead(siren) {
  const l = state.leads.find((x) => x.siren === siren);
  if (!l) return;
  const max = state.config.max_points;
  const bar = (label, pts, m) => `<div class="bd-row"><span>${label}</span>
    <div class="sim-bar"><span style="width:${pct(pts, m)}%"></span></div><span class="pts">${pts} / ${m}</span></div>`;

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
         ${l.note_flags ? `<p class="flag">⚠ Held for review (not sent to Salesforce): ${esc(l.note_flags)}</p>`
                        : `<p class="ok">✓ Validated: only uses facts from the enriched data</p>`}
       </section>`
    : "";

  const outcome = l.converted == null ? "" : `
    <section><h4>Outcome <span class="tag">simulated</span></h4>
      <p>${l.converted ? `<span class="ok">● Became a paying customer</span>` : `<span class="muted">○ Did not convert</span>`}
      <span class="muted">· hidden probability ${Math.round(100 * l.true_probability)}%, which the score never sees</span></p>
    </section>`;

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
    ${outcome}

    <section><h4>Routing</h4>${routing}</section>

    <section><h4>Website journey (Segment)</h4>${journeyHtml(l)}</section>

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

    <section><h4>Integration payloads (dry run)</h4>${payloadsHtml(l)}</section>`;

  $("#drawer").classList.add("open");
  $("#scrim").classList.add("open");
  $("#drawer").scrollTop = 0;
  $("#drawer .close").addEventListener("click", closeLead);
}

function closeLead() {
  $("#drawer").classList.remove("open");
  $("#scrim").classList.remove("open");
}
$("#scrim").addEventListener("click", closeLead);
document.addEventListener("keydown", (e) => e.key === "Escape" && closeLead());

// ---------- integrations ----------
const DESTINATIONS = {
  salesforce_leads_upsert: {
    title: "Salesforce · Lead upsert", records: (b) => b.records,
    why: "Hot leads become Salesforce Leads. Upsert on the External ID <code>SIREN__c</code>: replaying the file updates records instead of duplicating them. A flagged AI note is sent empty with <code>Note_Needs_Review__c = true</code>.",
  },
  braze_users_track: {
    title: "Braze · /users/track", records: (b) => b.attributes,
    why: "Everyone else gets Braze custom attributes plus a <code>nurture_enrolled</code> event. That event is what triggers the Canvas for their <code>nurture_track</code>.",
  },
  meta_conversions_api: {
    title: "Meta · Conversions API", records: (b) => b.data,
    why: "A <code>QualifiedLead</code> event per Sales-ready lead, so Meta optimises ads for leads Sales wants, not for raw sign-ups. IDs are SHA-256 hashed. Leads that clicked a Meta ad also carry <code>fbc</code> (built from the fbclid on the landing page).",
  },
};

function renderIntegrations() {
  const names = Object.keys(DESTINATIONS).filter((n) => state.outbox[n]);
  if (!names.length) { $("#int-detail").innerHTML = `<div class="card muted">No outbox yet: run <code>python run_pipeline.py</code>.</div>`; return; }
  $("#int-list").innerHTML = names.map((n) => {
    const reqs = state.outbox[n];
    const count = reqs.reduce((sum, r) => sum + DESTINATIONS[n].records(r.body).length, 0);
    return `<button data-name="${n}"><b>${DESTINATIONS[n].title}</b><br><span class="muted">${count} records · ${reqs.length} request${reqs.length > 1 ? "s" : ""}</span></button>`;
  }).join("");

  const select = (name) => {
    document.querySelectorAll("#int-list button").forEach((b) => b.classList.toggle("active", b.dataset.name === name));
    const d = DESTINATIONS[name], req = state.outbox[name][0];
    const items = d.records(req.body);
    const preview = JSON.parse(JSON.stringify(req)); // show 2 records, not all of them
    Object.keys(preview.body).forEach((k) => {
      if (Array.isArray(preview.body[k]) && preview.body[k].length > 2)
        preview.body[k] = [...preview.body[k].slice(0, 2), `… ${preview.body[k].length - 2} more`];
    });
    $("#int-detail").innerHTML = `<div class="card">
        <h2>${d.title}</h2><p>${d.why}</p>
        <p><span class="tag">${esc(req.method)}</span> <code>${esc(req.url)}</code></p>
        <p class="muted">Dry run: tokens are {PLACEHOLDERS} and nothing is sent. File: <code>output/outbox/${name}.json</code> · ${items.length} records in the first request.</p>
        ${json(preview)}
      </div>`;
  };
  $("#int-list").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-name]");
    if (b) select(b.dataset.name);
  });
  select(names[0]);
}

// ---------- SQL ----------
let browserDb = null; // static site only: the SQLite file loaded into sql.js

function checkSelectOnly(text) {
  const sql = text.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/--[^\n]*/g, " ").trim().replace(/;$/, "");
  if (!/^(select|with)\b/i.test(sql) || sql.includes(";"))
    throw new Error("Only a single SELECT (or WITH ... SELECT) query is allowed.");
  return sql;
}

async function runQuery(text) {
  if (!STATIC) return api("api/query", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sql: text }),
  });
  const sql = checkSelectOnly(text);
  if (!browserDb) {
    const SQL = await initSqlJs({ locateFile: (f) => SQL_JS_DIR + f });
    browserDb = new SQL.Database(new Uint8Array(await (await fetch("growth_ops.db")).arrayBuffer()));
  }
  const res = browserDb.exec(sql);
  if (!res.length) return [];
  const { columns, values } = res[0];
  return values.slice(0, 500).map((v) => Object.fromEntries(columns.map((c, i) => [c, v[i]])));
}

async function setupSql() {
  const files = await api("api/sql");
  const pretty = (name) => name.replace(/^\d+_/, "").replaceAll("_", " ");
  $("#sql-list").innerHTML =
    files.map((f) => `<button data-name="${f.name}">${esc(pretty(f.name))}</button>`).join("") +
    `<div class="sep"></div><button data-name="__custom">✎ Write your own</button>`;
  if (STATIC) $("#sql-mode").textContent = "Runs in your browser on a copy of the SQLite db (sql.js). SELECT queries only.";

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
    const rows = await runQuery($("#sql-text").value);
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
  if (STATIC) $("#demo-banner").hidden = false;
  [state.summary, state.leads, state.config, state.journeys, state.outbox] = await Promise.all([
    api("api/summary"), api("api/leads"), api("api/config"), api("api/journeys"), api("api/outbox")]);
  renderKpis(state.summary);
  renderFlow(state.summary);
  renderSimulator();
  setupLeadFilters();
  renderLeads();
  renderRules();
  renderIntegrations();
  await Promise.all([renderCharts(), setupSql()]);
  const start = location.hash.slice(1);
  if (VIEWS.includes(start)) showView(start);
  if (start.startsWith("lead=")) { showView("leads"); openLead(start.slice(5)); } // e.g. #lead=331747485
})();
