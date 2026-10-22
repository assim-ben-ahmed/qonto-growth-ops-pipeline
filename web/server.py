"""Local web UI for the pipeline results.

Run:  python -m web.server   ->  http://127.0.0.1:5000
It only *reads* the SQLite db produced by `python run_pipeline.py`.
"""
import re
import sqlite3
import sys
from functools import lru_cache
from typing import Any

from flask import Flask, Response, jsonify, request, send_from_directory
from plotly.offline import get_plotlyjs

from src.config import DB_PATH, ROOT, SQL_DIR, load_config

STATIC_DIR = ROOT / "web" / "static"
MAX_ROWS = 500

app = Flask(__name__, static_folder=None)
app.json.sort_keys = False  # keep SQL column order in results
CFG = load_config()

LEADS_SQL = """
SELECT s.siren, s.score, s.pts_headcount, s.pts_age, s.pts_sector, s.pts_channel, s.routed_to,
       e.message_id, e.anonymous_id, e.event, e.timestamp, e.source_channel,
       e.utm_source, e.utm_medium, e.utm_campaign, e.plan_chosen,
       c.company_name, c.naf_code, c.naf_label, c.sector_section, c.sector_label,
       c.headcount_label, c.headcount_min, c.creation_date, c.company_age_years,
       c.city, c.postal_code, c.legal_form, c.enrichment_status, c.missing_fields,
       l.Rating, l.OwnerQueue, l.LeadSource, l.Sales_Note__c AS note,
       l.Note_Source__c AS note_source, l.Note_Flags__c AS note_flags,
       b.nurture_track
FROM scored_leads s
JOIN events e        ON e.message_id = s.message_id
JOIN companies c     ON c.siren = s.siren
LEFT JOIN crm_leads l     ON l.siren = s.siren
LEFT JOIN braze_nurture b ON b.external_id = s.siren
ORDER BY s.score DESC, c.company_name
"""


def query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Run SQL on a read-only connection: the UI can never modify the data."""
    conn = sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchmany(MAX_ROWS)]
    finally:
        conn.close()


def sql_files() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(SQL_DIR.glob("*.sql"))}


@app.get("/")
def index() -> Response:
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/static/<path:name>")
def static_files(name: str) -> Response:
    return send_from_directory(STATIC_DIR, name)


@lru_cache(maxsize=1)
def _plotly_source() -> str:
    return get_plotlyjs()


@app.get("/plotly.js")
def plotly_js() -> Response:
    """Serve plotly.js from the installed Python package, so the UI works offline."""
    return Response(_plotly_source(), mimetype="application/javascript")


@app.get("/api/summary")
def summary() -> Response:
    one = lambda sql: query(sql)[0]["n"]  # noqa: E731
    return jsonify({
        "events": one("SELECT COUNT(*) n FROM events"),
        "enriched": one("SELECT COUNT(*) n FROM companies WHERE enrichment_status <> 'failed'"),
        "partial": one("SELECT COUNT(*) n FROM companies WHERE enrichment_status = 'partial'"),
        "scored": one("SELECT COUNT(*) n FROM scored_leads"),
        "crm": one("SELECT COUNT(*) n FROM crm_leads"),
        "hot": one("SELECT COUNT(*) n FROM crm_leads WHERE Rating = 'Hot'"),
        "braze": one("SELECT COUNT(*) n FROM braze_nurture"),
        "notes_llm": one("SELECT COUNT(*) n FROM crm_leads WHERE Note_Source__c = 'llm'"),
        "notes_flagged": one("SELECT COUNT(*) n FROM crm_leads WHERE Note_Flags__c <> ''"),
    })


@app.get("/api/leads")
def leads() -> Response:
    return jsonify(query(LEADS_SQL))


@app.get("/api/config")
def config() -> Response:
    s = CFG["scoring"]
    maxes = {
        "headcount": max(p for _, p in s["headcount_bands"]),
        "age": max(p for _, p in s["age_bands"]),
        "sector": max(s["sector_points"].values()),
        "channel": max(s["channel_points"].values()),
    }
    return jsonify({"scoring": s, "max_points": maxes, "routing": CFG["routing"],
                    "channels": CFG["channels"], "model": CFG["ai"]["model"]})


@app.get("/api/sql")
def list_sql() -> Response:
    return jsonify([{"name": k, "sql": v} for k, v in sql_files().items()])


@app.get("/api/sql/<name>")
def run_sql_file(name: str) -> Response:
    files = sql_files()
    if name not in files:
        return jsonify({"error": f"unknown query {name}"}), 404
    return jsonify(query(files[name]))


@app.post("/api/query")
def custom_query() -> Response:
    """Ad-hoc SELECT from the SQL tab. Read-only connection + SELECT/WITH only."""
    sql = (request.get_json(silent=True) or {}).get("sql", "")
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)        # drop /* block */ comments
    sql = re.sub(r"--[^\n]*", " ", sql).strip().rstrip(";")  # drop -- line comments
    if not sql.lower().startswith(("select", "with")) or ";" in sql:
        return jsonify({"error": "Only a single SELECT (or WITH ... SELECT) query is allowed."}), 400
    try:
        return jsonify(query(sql))
    except sqlite3.Error as exc:
        return jsonify({"error": str(exc)}), 400


if __name__ == "__main__":
    if not DB_PATH.exists():
        sys.exit("No database yet - run `python run_pipeline.py` first.")
    app.run(host="127.0.0.1", port=5000, debug=False)
