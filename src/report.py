"""Step 6 - Static HTML dashboard.

Runs the SQL files in /sql, turns results into Plotly charts and renders a
single self-contained HTML file (works offline, no server, easy to share).
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from jinja2 import Environment, FileSystemLoader
from plotly.offline import get_plotlyjs

from src.config import ROOT, SQL_DIR
from src.outcomes import auc

log = logging.getLogger(__name__)

ACCENT, MUTED, GRID = "#5B4BDB", "#C9C3F2", "#E8E8EE"
OUTCOME = "#1E9E7A"  # simulated outcomes always use this colour


def run_sql(conn: sqlite3.Connection, filename: str) -> pd.DataFrame:
    """Execute one file from /sql and return the result as a DataFrame."""
    return pd.read_sql((SQL_DIR / filename).read_text(encoding="utf-8"), conn)


def _style(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(title=dict(text=title, x=0, font=dict(size=15)), height=340,
                      margin=dict(l=10, r=10, t=50, b=10), plot_bgcolor="white",
                      paper_bgcolor="white", font=dict(family="Inter, Segoe UI, sans-serif", size=12),
                      legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
    fig.update_xaxes(gridcolor=GRID)
    fig.update_yaxes(gridcolor=GRID)
    return fig


def build_charts(conn: sqlite3.Connection, threshold: int, score_auc: float | None) -> list[go.Figure]:
    """One chart per SQL query."""
    funnel = run_sql(conn, "05_website_funnel.sql").groupby(["step_order", "step"], as_index=False)["visitors"].sum()
    fig0 = go.Figure(go.Funnel(y=funnel["step"], x=funnel["visitors"], marker_color=ACCENT,
                               textinfo="value+percent initial"))
    _style(fig0, "Website funnel (Segment page / track calls)")

    ch = run_sql(conn, "07_channel_outcomes.sql").sort_values("conversion_pct")
    fig1 = go.Figure([
        go.Bar(name="Sent to Sales (score)", x=ch["sent_to_sales_pct"], y=ch["source_channel"],
               orientation="h", marker_color=ACCENT),
        go.Bar(name="Converted (simulated)", x=ch["conversion_pct"], y=ch["source_channel"],
               orientation="h", marker_color=OUTCOME),
    ])
    _style(fig1, "Channels: what the score says vs. what converts").update_layout(
        barmode="group", legend=dict(orientation="h", y=-0.12, x=0, xanchor="left", traceorder="normal"))
    fig1.update_xaxes(ticksuffix="%", range=[0, 100])

    val = run_sql(conn, "06_score_validation.sql")
    fig_val = go.Figure(go.Bar(x=val["score_group"], y=val["conversion_pct"], marker_color=OUTCOME,
                               text=[f"lift {v:.2f}" for v in val["lift"]], textposition="outside",
                               cliponaxis=False, customdata=val[["score_range", "cum_share_of_conversions_pct"]],
                               hovertemplate="Scores %{customdata[0]}: %{y}% converted<br>"
                                             "%{customdata[1]}% of all conversions so far<extra></extra>"))
    _style(fig_val, f"Conversion by score group - AUC {score_auc}")
    fig_val.update_yaxes(ticksuffix="%", range=[0, 100])

    sec = run_sql(conn, "02_top_sectors.sql").sort_values("signups")
    fig2 = go.Figure([
        go.Bar(name="Nurture (Braze)", x=sec["signups"] - sec["hot_leads"], y=sec["sector"],
               orientation="h", marker_color=MUTED),
        go.Bar(name="Hot (CRM)", x=sec["hot_leads"], y=sec["sector"], orientation="h",
               marker_color=ACCENT),
    ])
    _style(fig2, "Top sectors - sign-ups split by routing").update_layout(barmode="stack")

    dist = run_sql(conn, "03_score_distribution.sql")
    colors = [ACCENT if b >= threshold else MUTED for b in dist["score_bucket"]]
    fig3 = go.Figure(go.Bar(x=dist["bucket_label"], y=dist["leads"], marker_color=colors,
                            customdata=dist["leads_at_or_above"],
                            hovertemplate="%{x}: %{y} leads<br>%{customdata} at or above"
                                          "<extra></extra>"))
    _style(fig3, f"Lead score distribution (threshold = {threshold})")

    age = run_sql(conn, "04_signups_by_company_age.sql")
    age["label"] = age["age_bucket"].str[3:]  # drop the "1. " sort prefix
    fig4 = go.Figure([
        go.Bar(name="Hot (CRM)", x=age["label"], y=age["hot_leads"], marker_color=ACCENT),
        go.Bar(name="Nurture (Braze)", x=age["label"], y=age["nurture"], marker_color=MUTED),
    ])
    _style(fig4, "Sign-ups by company age").update_layout(barmode="stack")
    return [fig0, fig1, fig3, fig_val, fig2, fig4]


def kpis(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    signups = one("SELECT COUNT(*) FROM events")
    enriched = one("SELECT COUNT(*) FROM companies WHERE enrichment_status <> 'failed' "
                   "AND siren IN (SELECT siren FROM events)")  # this run only
    hot = one("SELECT COUNT(*) FROM crm_leads")
    flagged = one("SELECT COUNT(*) FROM crm_leads WHERE Note_Flags__c <> ''")
    llm = one("SELECT COUNT(*) FROM crm_leads WHERE Note_Source__c = 'llm'")
    return [
        {"label": "Sign-ups", "value": signups, "sub": "Segment track events"},
        {"label": "Enriched", "value": f"{100 * enriched / max(signups, 1):.0f}%",
         "sub": f"{enriched} SIRENs matched"},
        {"label": "Leads to Sales", "value": hot, "sub": f"{100 * hot / max(signups, 1):.0f}% -> Salesforce"},
        {"label": "To nurture", "value": signups - hot, "sub": "-> Braze import"},
        {"label": "AI notes flagged", "value": flagged, "sub": f"of {hot} ({llm} by LLM)"},
    ]


def run(conn: sqlite3.Connection, cfg: dict[str, Any], out_path: Path) -> Path:
    """Render output/dashboard.html."""
    pairs = conn.execute("SELECT s.score, o.converted FROM scored_leads s "
                         "JOIN outcomes o ON o.siren = s.siren").fetchall()
    figs = build_charts(conn, cfg["scoring"]["threshold"], auc([p[0] for p in pairs], [p[1] for p in pairs]))
    # plotly.js is embedded once in <head> so the file works offline.
    charts = [f.to_html(full_html=False, include_plotlyjs=False, default_width="100%",
                        config={"displayModeBar": False, "responsive": True}) for f in figs]
    leads = pd.read_sql("""SELECT Company, Industry, City, LeadSource, Rating, OwnerQueue,
                                  Lead_Score__c AS Score, Sales_Note__c AS Note,
                                  Note_Source__c AS NoteSource, Note_Flags__c AS Flags
                           FROM crm_leads ORDER BY Lead_Score__c DESC, Company LIMIT 15""", conn)
    flagged = pd.read_sql("""SELECT Company, Sales_Note__c AS Note, Note_Flags__c AS Flags
                             FROM crm_leads WHERE Note_Flags__c <> ''""", conn)

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True)
    html = env.get_template("dashboard.html.j2").render(
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"), kpis=kpis(conn), charts=charts,
        plotly_js=get_plotlyjs(),
        leads=leads.to_dict("records"), flagged=flagged.to_dict("records"),
        threshold=cfg["scoring"]["threshold"])
    out_path.write_text(html, encoding="utf-8")
    log.info("dashboard written to %s", out_path.relative_to(ROOT))
    return out_path
